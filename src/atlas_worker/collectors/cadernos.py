"""Leitura de cadernos do DJEN no coletor: baixa, confere o SHA-256 informado pela fonte, lê e filtra pelo que interessa.
NOTA: o contrato v1 do servidor ainda NÃO distribui tarefas de caderno (o Radar processa os cadernos localmente, em PHP). Este módulo está
pronto e testado para quando o servidor passar a oferecê-las; não é usado pelo worker na versão 0.1."""
from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path

import httpx

URL = "https://comunicaapi.pje.jus.br/api/v1/caderno/{tribunal}/{data}/{meio}"


class CadernoCorrompido(Exception):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


async def metadados(http: httpx.AsyncClient, tribunal: str, data: str, meio: str = "D") -> dict | None:
    """None = não há caderno para o dia (feriado, fim de semana). Falha da fonte levanta exceção."""
    r = await http.get(URL.format(tribunal=tribunal, data=data, meio=meio), headers={"Accept": "application/json"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    j = r.json()
    return j if j.get("url") and j.get("hash") and j.get("status") == "Processado" else None


async def baixar(http: httpx.AsyncClient, meta: dict, pasta: Path) -> Path:
    """Baixa só se ainda não houver arquivo íntegro; confere o hash; troca atômica."""
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{meta['sigla_tribunal']}-{meta.get('meio', 'D')}-{meta['data']}_v{meta.get('versao', 1)}.zip"
    esperado = str(meta["hash"]).lower()
    if destino.exists() and sha256(destino) == esperado:
        return destino
    tmp = destino.with_suffix(".tmp")
    async with http.stream("GET", meta["url"]) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            async for bloco in r.aiter_bytes(1 << 20):
                f.write(bloco)
    if sha256(tmp) != esperado:
        tmp.unlink(missing_ok=True)
        raise CadernoCorrompido("o SHA-256 do arquivo não confere com o informado pela fonte")
    tmp.replace(destino)
    return destino


def itens(zip_path: Path) -> Iterator[dict]:
    with zipfile.ZipFile(zip_path) as z:
        for nome in sorted(n for n in z.namelist() if n.lower().endswith(".json")):
            for it in json.loads(z.read(nome)).get("items", []):
                yield it


def filtrar(zip_path: Path, orgaos: set[str], termos: set[str], oabs: set[str]) -> Iterator[dict]:
    """Só as comunicações de interesse (órgão favorito, parte favorita ou OAB favorita) — o resto nem sai do computador.
    orgaos: nomes normalizados; termos: nomes normalizados de partes; oabs: 'UF|numero' sem zeros à esquerda."""
    from ..tasks import normalizar
    for it in itens(zip_path):
        if normalizar(str(it.get("nomeOrgao") or "")) in orgaos:
            yield it
            continue
        if any(t in normalizar(str(d.get("nome") or "")) for d in it.get("destinatarios") or [] for t in termos):
            yield it
            continue
        for d in it.get("destinatarioadvogados") or []:
            a = d.get("advogado") or {}
            if f"{str(a.get('uf_oab') or '').upper()}|{str(a.get('numero_oab') or '').lstrip('0')}" in oabs:
                yield it
                break
