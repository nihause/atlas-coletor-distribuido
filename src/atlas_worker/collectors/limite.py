"""Limite GLOBAL de requisições: antes de cada chamada a uma fonte, pergunta ao servidor quanto esperar. O limite vale para todos os
computadores somados (o servidor mantém um único ritmo por fonte), não por trabalhador. Depois da chamada, informa o resultado
(429, Retry-After, 5xx): o servidor aplica espera crescente com variação aleatória e abre o disjuntor se a fonte cair."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..client import ClientError, RadarClient

log = logging.getLogger("atlas_worker.limite")


class FonteIndisponivel(Exception):
    """A fonte externa não respondeu bem (429, 5xx, tempo esgotado). Não é falha do favorito nem do lote."""


@dataclass
class Resposta:
    http: int
    corpo: dict | None
    retry_after: int | None = None
    ms: float = 0.0


class Limitador:
    def __init__(self, client: RadarClient, fonte: str, sleep: Callable[[float], Awaitable] = asyncio.sleep, max_espera: float = 300.0, progresso=None):
        self.client, self.fonte, self._sleep, self.max_espera = client, fonte, sleep, max_espera
        self.progresso = progresso
        self._ok_sem_relato = 0
        self.requisicoes = 0

    async def _aguardar_vaga(self) -> None:
        total = 0.0
        while True:
            v = await self.client.vaga(self.fonte)
            espera = float(v.get("espera_s", 0))
            if espera <= 0:
                return
            total += espera
            if total > self.max_espera:
                raise FonteIndisponivel(f"{self.fonte}: espera acumulada acima de {self.max_espera:.0f}s ({v.get('motivo', 'limite')})")
            if self.progresso:
                self.progresso(fase=f"Aguardando limite global de {self.fonte} ({espera:.0f} s)")
            await self._sleep(min(espera, 60.0))
            if not v.get("pausa"):
                return   # a vaga foi reservada para este instante: pode ir

    async def requisitar(self, fazer: Callable[[], Awaitable[Resposta]]) -> Resposta:
        await self._aguardar_vaga()
        if self.progresso:
            self.progresso(fase=f"Consultando {self.fonte.upper()}")
        self.requisicoes += 1
        t0 = time.monotonic()
        try:
            r = await fazer()
        except (TimeoutError, OSError) as e:   # httpx.TimeoutException herda de Exception; o chamador converte para Resposta(0)
            r = Resposta(0, None, None, (time.monotonic() - t0) * 1000)
            log.warning("%s: %s", self.fonte, type(e).__name__)
        r.ms = r.ms or (time.monotonic() - t0) * 1000
        # Relata sempre o que não é 200 (para a espera crescente); os 200 em amostra (1 a cada 20) só para zerar a sequência.
        if r.http != 200 or self._ok_sem_relato >= 19:
            self._ok_sem_relato = 0
            try:
                await self.client.resultado_fonte(self.fonte, r.http, r.ms, r.retry_after)
            except ClientError as e:
                log.warning("não foi possível relatar o resultado de %s: %s", self.fonte, e)
        else:
            self._ok_sem_relato += 1
        if r.http == 429 or r.http >= 500 or r.http == 0:
            raise FonteIndisponivel(f"{self.fonte}: HTTP {r.http}")
        return r
