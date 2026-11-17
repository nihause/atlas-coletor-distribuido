"""Contratos das tarefas (versão 1), validados com Pydantic: o coletor não executa nada que o servidor não tenha declarado."""
from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class Favorito(_Estrito):
    tipo: Literal["parte", "advogado", "comarca", "vara"]
    ref_id: int


class Filtro(_Estrito):
    tipo: Literal["parte", "advogado_nome"]
    termo_norm: str | None = None
    oab: str | None = None
    uf: str | None = None
    nome_norm: str | None = None


# Só estes parâmetros de consulta ao DJEN são aceitos; o resto é descartado.
_PARAMS_DJEN = {"siglaTribunal", "orgaoId", "numeroOab", "ufOab", "nomeAdvogado", "nomeParte", "meio"}


class Consulta(_Estrito):
    params: dict[str, str | int]
    filtro: Filtro | None = None

    @field_validator("params")
    @classmethod
    def _p(cls, v: dict) -> dict:
        ruim = set(v) - _PARAMS_DJEN
        if ruim:
            raise ValueError(f"parâmetros de consulta não permitidos: {sorted(ruim)}")
        if not v:
            raise ValueError("consulta sem parâmetros")
        return v


class ParamsDjenJanela(_Estrito):
    favorito: Favorito
    de: date
    ate: date
    consultas: list[Consulta] = Field(min_length=1, max_length=50)
    janela_dias: int = 7
    base_dias: int = 7

    @field_validator("ate")
    @classmethod
    def _ordem(cls, v: date, info) -> date:
        if "de" in info.data and v < info.data["de"]:
            raise ValueError("período invertido")
        return v


Cnj = Annotated[str, StringConstraints(pattern=r"^\d{20}$")]


class ParamsDatajudLote(_Estrito):
    tribunal: str
    alias: Annotated[str, StringConstraints(pattern=r"^api_publica_[a-z0-9]+$")]
    cnjs: list[Cnj] = Field(min_length=1, max_length=50)
    ids: list[int] = []


class Tarefa(_Estrito):
    id: int
    tipo: Literal["djen_janela", "datajud_lote"]
    lease_token: str
    lease_ate: str | None = None
    params: dict

    def djen(self) -> ParamsDjenJanela:
        return ParamsDjenJanela.model_validate(self.params)

    def datajud(self) -> ParamsDatajudLote:
        return ParamsDatajudLote.model_validate(self.params)


def normalizar(texto: str) -> str:
    """Mesma regra do servidor (djen_normalizar): sem acento, maiúsculas, só letras e espaços."""
    import unicodedata
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", "", s).upper()).strip()
