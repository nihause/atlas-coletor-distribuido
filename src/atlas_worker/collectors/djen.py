"""Consulta de publicações do DJEN por período, no ritmo global. Mesmas garantias do coletor PHP: página de 100, sem repetição de
itens, divisão do período quando a fonte acusa 10 mil ou mais, prova de completude (página curta no fim)."""
from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import AsyncIterator
from datetime import date, timedelta

import httpx

from ..tasks import ParamsDjenJanela, normalizar
from .limite import FonteIndisponivel, Limitador, Resposta

log = logging.getLogger("atlas_worker.djen")
DJEN_URL = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
POR_PAGINA = 100
MAX_PAGINAS = 2000
LIMITE_COUNT = 10_000


class ErroDjen(Exception):
    """Resposta incoerente da fonte (paginação repetiu, total incompleto...): refazer a janela, não avançar."""


def dividir(de: date, ate: date) -> list[tuple[date, date]]:
    dias = (ate - de).days
    if dias <= 0:
        return []
    meio = de + timedelta(days=dias // 2)
    return [(de, meio), (meio + timedelta(days=1), ate)]


def cita_advogado(item: dict, oab: str, uf: str, nome_norm: str) -> bool:
    so_digitos = lambda s: "".join(c for c in str(s or "") if c.isdigit())  # noqa: E731
    for d in item.get("destinatarioadvogados") or []:
        a = d.get("advogado") or {}
        n = so_digitos(a.get("numero_oab"))
        if n:
            if n == so_digitos(oab) and str(a.get("uf_oab") or "").upper() == uf.upper():
                return True
        elif normalizar(str(a.get("nome") or "")) == nome_norm:
            return True
    return False


def aceita(filtro, item: dict) -> bool:
    """Mesmo filtro que o servidor reaplica ao receber: homônimos não passam."""
    if filtro is None:
        return True
    if filtro.tipo == "parte":
        t = filtro.termo_norm or ""
        return bool(t) and any(t in normalizar(str(d.get("nome") or "")) for d in item.get("destinatarios") or [])
    if filtro.tipo == "advogado_nome":
        return cita_advogado(item, filtro.oab or "", filtro.uf or "", filtro.nome_norm or "")
    return False


class Djen:
    def __init__(self, limitador: Limitador, http: httpx.AsyncClient, batch: int = 100, progresso=None):
        self.lim, self.http, self.batch = limitador, http, batch
        self.progresso = progresso
        self.paginas = 0
        self.dividida = False
        self.total_itens = 0

    async def _pagina(self, params: dict) -> dict:
        async def fazer() -> Resposta:
            try:
                r = await self.http.get(DJEN_URL, params=params, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0 (atlas-worker)"})
            except httpx.TimeoutException:
                return Resposta(0, None)
            except httpx.TransportError:
                return Resposta(0, None)
            ra = r.headers.get("Retry-After")
            try:
                corpo = r.json() if r.status_code == 200 else None
            except ValueError:
                corpo = None
            return Resposta(r.status_code if (r.status_code != 200 or corpo is not None) else 502, corpo, int(ra) if ra and ra.isdigit() else None)

        r = await self.lim.requisitar(fazer)
        self.paginas += 1
        if not isinstance(r.corpo, dict) or not isinstance(r.corpo.get("items"), list):
            raise ErroDjen("resposta do DJEN sem lista de itens")
        return r.corpo

    async def _tribunais(self) -> list[str]:
        # A lista oficial pode ser agrupada por UF e repetir tribunais federais.
        async def fazer():
            try:
                r = await self.http.get(DJEN_URL + "/tribunal", headers={"Accept": "application/json"})
                return Resposta(r.status_code, r.json() if r.status_code == 200 else None)
            except (httpx.TransportError, ValueError):
                return Resposta(0, None)
        r = await self.lim.requisitar(fazer)
        siglas = set()
        def visitar(n):
            if isinstance(n, dict):
                if "sigla" in n:
                    sigla = str(n["sigla"])
                    if not re.fullmatch(r"[A-Za-z0-9-]{2,12}", sigla):
                        raise ErroDjen("sigla inválida no catálogo oficial")
                    siglas.add(sigla)
                for v in n.values():
                    visitar(v)
            elif isinstance(n, list):
                for v in n:
                    visitar(v)
        visitar(r.corpo)
        if not siglas:
            raise ErroDjen("lista oficial de tribunais vazia; consulta não concluída")
        return sorted(siglas)

    async def _repartir(self, base: dict, dia: date) -> AsyncIterator[dict]:
        self.dividida = True
        if not base.get("siglaTribunal"):
            partes = [{**base, "siglaTribunal": t} for t in await self._tribunais()]
        elif not base.get("meio"):
            partes = [{**base, "meio": m} for m in ("D", "E")]
        else:
            raise ErroDjen("dia atingiu 10 mil resultados após divisão por tribunal e meio; não concluir parcialmente")
        for p in partes:
            async for it in self._paginar_dia(p, dia):
                yield it

    async def _paginar_dia(self, base: dict, dia: date) -> AsyncIterator[dict]:
        itens: list[dict] = []
        vistos: set[int] = set()
        total = None
        for pagina in range(1, MAX_PAGINAS + 1):
            j = await self._pagina({**base, "dataDisponibilizacaoInicio": dia.isoformat(), "dataDisponibilizacaoFim": dia.isoformat(), "itensPorPagina": POR_PAGINA, "pagina": pagina})
            lote = j["items"]
            if total is None and j.get("count") is not None:
                total = int(j["count"])
            if self.progresso:
                self.progresso(fase="Lendo publicações do DJEN", paginas=self.paginas, lidos=len(lote))
            if (pagina == 1 and total is not None and total >= LIMITE_COUNT) or len(itens) + len(lote) >= LIMITE_COUNT:
                # Descarta a amostra antes de repartir: não a envia como se fosse o dia completo.
                async for it in self._repartir(base, dia):
                    yield it
                return
            novos = []
            for it in lote:
                iid = int(it.get("id") or 0)
                if iid <= 0:
                    raise ErroDjen("publicação sem identificador válido")
                if iid not in vistos:
                    vistos.add(iid)
                    novos.append(it)
            if lote and not novos:
                raise ErroDjen(f"paginação repetiu itens na página {pagina}")
            itens += novos
            if len(lote) < POR_PAGINA:
                if total is not None and len(itens) < total:
                    raise ErroDjen(f"resposta incompleta do DJEN: recebidos {len(itens)} de {total}")
                for it in itens:
                    yield it
                return
        raise ErroDjen("consulta excedeu o limite de páginas")

    async def _paginar(self, base: dict, de: date, ate: date) -> AsyncIterator[dict]:
        # Inclui tarefas antigas já reservadas: nenhuma chamada mistura dias.
        dia = de
        while dia <= ate:
            async for it in self._paginar_dia(base, dia):
                yield it
            dia += timedelta(days=1)

    async def janela(self, p: ParamsDjenJanela) -> AsyncIterator[tuple[str, list[dict]]]:
        """Entrega (chave_do_lote, itens[{q, item}]) já filtrados e sem repetição. A chave inclui o hash do conteúdo: se o DJEN devolver algo
        diferente numa repetição, é outro lote (a gravação no servidor é idempotente por item), e nunca um lote antigo mascara um novo."""
        vistos: set[int] = set()
        pronto: list[dict] = []
        idx = 0
        for q, consulta in enumerate(p.consultas):
            base = {k: v for k, v in consulta.params.items()}
            async for it in self._paginar(base, p.de, p.ate):
                iid = int(it.get("id") or 0)
                self.total_itens += 1
                if iid <= 0 or iid in vistos or not aceita(consulta.filtro, it):
                    continue
                vistos.add(iid)
                pronto.append({"q": q, "item": it})
                if self.progresso:
                    self.progresso(fase="Selecionando publicações do favorito", encontrados=1)
                if len(pronto) >= self.batch:
                    yield self._chave(idx, pronto), pronto
                    idx, pronto = idx + 1, []
        if pronto:
            yield self._chave(idx, pronto), pronto

    @staticmethod
    def _chave(idx: int, lote: list[dict]) -> str:
        h = hashlib.sha1(",".join(str(x["item"]["id"]) for x in lote).encode()).hexdigest()[:10]
        return f"{idx}-{h}"
