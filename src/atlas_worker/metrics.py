"""Contadores locais, enviados ao servidor no heartbeat (CPU, memória, erros, produtividade)."""
from __future__ import annotations

import platform
import socket
import time

import psutil


class Metrics:
    def __init__(self) -> None:
        self.inicio = time.time()
        self.erros = 0
        self.tarefas_recebidas = 0
        self.itens_enviados = 0
        self.tarefas_concluidas = 0
        self.requisicoes = {"djen": 0, "datajud": 0}

    def snapshot(self, tarefa_id: int | None) -> dict:
        return {"cpu_pct": psutil.cpu_percent(interval=None), "mem_pct": psutil.virtual_memory().percent, "tarefa_id": tarefa_id, "erros": self.erros}


def identidade_maquina() -> dict:
    return {"sistema": f"{platform.system()} {platform.release()}"[:80], "hostname": socket.gethostname()[:120], "cpus": psutil.cpu_count() or 1, "ram_mb": int(psutil.virtual_memory().total / 2**20)}
