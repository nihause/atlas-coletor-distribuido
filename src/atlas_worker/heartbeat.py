"""Sinal de vida periódico: informa carga, tarefa atual e erros; recebe o comando do servidor (continuar, pausar, parar)."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from . import __version__
from .client import ClientError, RadarClient, Unauthorized
from .metrics import Metrics

log = logging.getLogger("atlas_worker.heartbeat")


class Heartbeat:
    def __init__(self, client: RadarClient, metrics: Metrics, intervalo: int, tarefa_atual: Callable[[], int | None], ao_receber: Callable[[dict], None], ao_perder_acesso: Callable[[], None], progresso: Callable[[], list] | None = None, atualizacao: Callable[[], dict] | None = None):
        self.client, self.metrics, self.intervalo = client, metrics, intervalo
        self.atualizacao = atualizacao
        self.progresso = progresso
        self.tarefa_atual, self.ao_receber, self.ao_perder_acesso = tarefa_atual, ao_receber, ao_perder_acesso

    async def uma_vez(self) -> None:
        try:
            dados = {**self.metrics.snapshot(self.tarefa_atual()), "versao": __version__}
            if self.progresso:
                dados["progresso_tarefas"] = self.progresso()
            if self.atualizacao:
                dados["atualizacao"] = self.atualizacao()
            cfg = await self.client.heartbeat(dados)
            self.ao_receber(cfg)
        except Unauthorized:
            log.error("a chave deste coletor não é mais aceita pelo servidor (revogada ou trocada)")
            self.ao_perder_acesso()
        except ClientError as e:   # nunca derruba o coletor: tenta no próximo ciclo
            log.warning("heartbeat falhou: %s", e)

    async def rodar(self, parar: asyncio.Event) -> None:
        while not parar.is_set():
            await self.uma_vez()
            try:
                await asyncio.wait_for(parar.wait(), self.intervalo)
            except asyncio.TimeoutError:
                pass
