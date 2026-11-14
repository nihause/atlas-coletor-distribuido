"""Converte um documento do DataJud no registro enviado ao servidor (só campos públicos, tamanhos limitados).
Baseado em collector/processors/normalize.py do Atlas, mantido igual para que o Radar receba o mesmo formato."""
from __future__ import annotations


import re
from datetime import datetime, timezone


def _dt(v) -> str | None:
    if v in (None, ""):
        return None
    s = str(v)
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", s)
    try:
        if m:
            parts = [int(x) if x else 0 for x in m.groups()]
            return datetime(*parts, tzinfo=timezone.utc).isoformat()
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat()
    except ValueError:
        return None


def _s(v, n: int) -> str | None:
    return str(v)[:n] if v not in (None, "") else None


def _flat(v) -> list[dict]:
    """assuntos às vezes vem aninhado ([[{...}]]) no DataJud."""
    out = []
    for a in v or []:
        out += _flat(a) if isinstance(a, list) else [a] if isinstance(a, dict) else []
    return out


def record(hit: dict) -> dict | None:
    src = hit.get("_source", {})
    cnj = re.sub(r"\D", "", str(src.get("numeroProcesso", "")))
    if len(cnj) != 20:
        return None
    sig = int(src.get("nivelSigilo") or 0)
    org = src.get("orgaoJulgador") or {}
    classe = src.get("classe") or {}
    movs = []
    for m in (src.get("movimentos") or [])[:10_000]:
        movs.append({"codigo": m.get("codigo") if isinstance(m.get("codigo"), int) else None, "nome": _s(m.get("nome"), 255) or "(sem nome)",
                     "data_hora": _dt(m.get("dataHora")),
                     "complementos": [x for x in (_s(c.get("nome") or c.get("descricao"), 255) for c in (m.get("complementosTabelados") or [])[:50]) if x]})
    return {
        "source_record_id": re.sub(r"[^A-Za-z0-9_.:-]", "_", str(hit.get("_id") or src.get("id")))[:120],
        "numero_cnj": cnj, "grau": _s(src.get("grau"), 10),
        "orgao_codigo": str(org["codigo"]) if str(org.get("codigo", "")).isdigit() else None, "orgao_nome": _s(org.get("nome"), 255),
        "municipio_ibge": org.get("codigoMunicipioIBGE") if isinstance(org.get("codigoMunicipioIBGE"), int) else None,
        "classe_codigo": classe.get("codigo") if isinstance(classe.get("codigo"), int) else None, "classe_nome": _s(classe.get("nome"), 255),
        "assuntos": [{"codigo": a.get("codigo") if isinstance(a.get("codigo"), int) else None, "nome": _s(a.get("nome"), 255) or ""}
                     for a in _flat(src.get("assuntos"))[:100]],
        "data_ajuizamento": _dt(src.get("dataAjuizamento")), "sistema": _s((src.get("sistema") or {}).get("nome"), 60),
        "formato": _s((src.get("formato") or {}).get("nome"), 30), "nivel_sigilo": sig,
        "source_updated_at": _dt(src.get("dataHoraUltimaAtualizacao")), "movimentos": movs,
    }
