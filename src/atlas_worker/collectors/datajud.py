"""Consulta em lote ao DataJud (até 50 processos por requisição), no ritmo global. Resposta incompleta divide o lote; 429, 5xx e tempo
esgotado NÃO reduzem o lote (a lentidão é do servidor do CNJ, não do tamanho do pedido)."""
from __future__ import annotations

import logging

import httpx

from ..tasks import ParamsDatajudLote
from .limite import Limitador, Resposta
from .normalize import record

log = logging.getLogger("atlas_worker.datajud")
BASE = "https://api-publica.datajud.cnj.jus.br"


class LoteIncompleto(Exception):
    """A fonte respondeu, mas a resposta não cobre o pedido (timed_out, shards com falha, total maior que o recebido)."""


class DataJud:
    def __init__(self, limitador: Limitador, http: httpx.AsyncClient, api_key: str, progresso=None):
        self.lim, self.http, self.api_key = limitador, http, api_key
        self.progresso = progresso
        self.consultas = 0

    async def _buscar(self, alias: str, cnjs: list[str]) -> list[dict]:
        body = {"size": 3000, "track_total_hits": True, "query": {"terms": {"numeroProcesso": cnjs}}}

        async def fazer() -> Resposta:
            try:
                r = await self.http.post(f"{BASE}/{alias}/_search", json=body, headers={"Authorization": f"APIKey {self.api_key}", "Accept": "application/json"})
            except (httpx.TimeoutException, httpx.TransportError):
                return Resposta(0, None)
            ra = r.headers.get("Retry-After")
            try:
                corpo = r.json() if r.status_code == 200 else None
            except ValueError:
                corpo = None
            return Resposta(r.status_code if (r.status_code != 200 or corpo is not None) else 502, corpo, int(ra) if ra and ra.isdigit() else None)

        r = await self.lim.requisitar(fazer)
        self.consultas += 1
        j = r.corpo or {}
        hits = (j.get("hits") or {}).get("hits")
        total = (j.get("hits") or {}).get("total")
        if hits is None or total is None or j.get("timed_out") or (j.get("_shards") or {}).get("failed"):
            raise LoteIncompleto("resposta do DataJud incompleta")
        if self.progresso:
            self.progresso(fase="Lendo registros do DataJud", paginas=self.consultas, lidos=len(hits))
        esperado = total.get("value") if isinstance(total, dict) else total
        incompleto = (esperado is not None and esperado > len(hits)) or (isinstance(total, dict) and total.get("relation", "eq") != "eq")
        if incompleto:
            if len(cnjs) < 2:
                raise LoteIncompleto("resposta incompleta para um único processo")
            m = (len(cnjs) + 1) // 2
            return await self._buscar(alias, cnjs[:m]) + await self._buscar(alias, cnjs[m:])
        return hits

    async def lote(self, p: ParamsDatajudLote) -> tuple[list[dict], list[str]]:
        """@return (registros normalizados, CNJs não localizados). Só aceita documentos dos processos pedidos."""
        pedidos = set(p.cnjs)
        regs: list[dict] = []
        achados: set[str] = set()
        for h in await self._buscar(p.alias, list(p.cnjs)):
            rec = record(h)
            if rec and rec["numero_cnj"] in pedidos and rec["nivel_sigilo"] == 0:
                regs.append(rec)
                achados.add(rec["numero_cnj"])
            elif rec and rec["numero_cnj"] in pedidos:
                achados.add(rec["numero_cnj"])   # sigiloso: existe, mas não sai da máquina e não conta como "não localizado"
        if self.progresso:
            self.progresso(fase="Selecionando registros públicos", encontrados=len(regs))
        return regs, [c for c in p.cnjs if c not in achados]
