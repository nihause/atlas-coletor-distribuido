"""Motor real em uma thread com asyncio; sinais Qt são a única ponte para a UI."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import datetime, timezone

from PySide6.QtCore import QThread, Signal

from ..client import RadarClient
from ..config import Settings
from ..instance import RunLock
from ..verification import classify
from ..worker import Worker


class AsyncJob(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, operation: Callable, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.done.emit(asyncio.run(self.operation()))
        except Exception as exc:
            # Mensagens de exceção arbitrárias podem conter uma chave: exponha o tipo.
            self.failed.emit(str(exc) if isinstance(exc, ValueError) else f"Não foi possível concluir: {type(exc).__name__}.")


class EngineThread(QThread):
    snapshot = Signal(dict)
    problem = Signal(object)

    def __init__(self, cfg: Settings, *, client_factory=RadarClient, worker_factory=Worker, parent=None):
        super().__init__(parent)
        self.cfg, self.client_factory, self.worker_factory = cfg, client_factory, worker_factory
        self.loop = None
        self.worker = None
        self.stop_requested = False
        self.connected = False
        self.last_contact = "—"
        self.last_ok = 0.0

    def contact(self, ok: bool):
        self.connected = ok
        if ok:
            self.last_ok = time.monotonic()
            self.last_contact = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M:%S")

    def stop(self):
        self.stop_requested = True
        if self.loop and self.worker:
            self.loop.call_soon_threadsafe(self.worker.parar.set)

    async def _publish(self, once=False):
        while True:
            w = self.worker
            self.snapshot.emit({"connected": self.connected and time.monotonic() - self.last_ok <= max(120, self.cfg.heartbeat_interval * 3), "last_contact": self.last_contact,
                                "received": w.metrics.tarefas_recebidas, "completed": w.metrics.tarefas_concluidas,
                                "errors": w.metrics.erros, "active": len(w.ativas), "uptime": int(time.time() - w.metrics.inicio),
                                "read": w.metrics.itens_lidos, "found": w.metrics.itens_encontrados, "sent": w.metrics.itens_enviados,
                                "tasks": [ctx.snapshot() for ctx in w.contextos.values()], "recent": list(w.recentes), "waiting": w.espera,
                                "service": "Encerrando com segurança" if w.parar.is_set() else ("Pausado pelo Radar" if w.pausado else ("Coletando" if w.ativas else "Aguardando tarefas"))})
            if once:
                return
            await asyncio.sleep(1)

    async def execute(self):
        client = self.client_factory(self.cfg, observer=self.contact)
        self.loop = asyncio.get_running_loop()
        self.worker = self.worker_factory(self.cfg, client)
        publisher = asyncio.create_task(self._publish())
        if self.stop_requested:
            self.worker.parar.set()
        try:
            if not self.stop_requested:
                await self.worker.rodar()
                if self.worker.erro_fatal:
                    self.problem.emit(classify(self.worker.erro_fatal))
        finally:
            self.connected = False
            await self._publish(once=True)
            publisher.cancel()
            await asyncio.gather(publisher, return_exceptions=True)
            await client.aclose()
            if self.worker._http_proprio:
                await self.worker.http.aclose()
            self.loop = None

    def run(self):
        try:
            with RunLock(self.cfg):
                asyncio.run(self.execute())
        except Exception as exc:
            self.problem.emit(classify(exc) if not isinstance(exc, RuntimeError) else str(exc))
