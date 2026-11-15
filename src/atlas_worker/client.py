"""Cliente HTTPS do servidor central (Radar). Contrato v1. Tudo é idempotente no servidor, então repetir uma chamada é seguro."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from . import CONTRATO, __version__
from .config import Settings

log = logging.getLogger("atlas_worker.client")


class ClientError(Exception):
    def __init__(self, msg: str, *, status: int | None = None, error_code: str | None = None):
        super().__init__(msg)
        self.status, self.error_code = status, error_code


class EndpointError(ClientError):
    """Resposta fora do contrato, incluindo redirecionamento e HTML."""


class Unauthorized(ClientError):
    """401/403: chave inválida, revogada ou de outro coletor. Não adianta repetir."""


class LeaseLost(ClientError):
    """409: a reserva da tarefa foi perdida (expirou, foi reatribuída ou já concluída). Abandonar a tarefa."""


class NotFound(ClientError):
    pass


class Rejected(ClientError):
    """422/400: o servidor recusou o conteúdo. Repetir não ajuda."""


class ServerUnavailable(ClientError):
    """Rede caiu, tempo esgotado ou 5xx/429: repetir com espera."""

    def __init__(self, msg: str, retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


class RadarClient:
    def __init__(self, cfg: Settings, transport: httpx.AsyncBaseTransport | None = None, sleep=asyncio.sleep, observer=None):
        self.cfg = cfg
        self.observer = observer
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            base_url=cfg.base_url, timeout=cfg.request_timeout, transport=transport, verify=True,   # TLS sempre validado
            headers={"Authorization": f"Bearer {cfg.worker_token.get_secret_value()}", "X-Contrato": str(CONTRATO), "User-Agent": f"atlas-worker/{__version__}",
                     "Accept": "application/json"})

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, path: str, body: dict | None = None, *, tentativas: int = 4) -> dict[str, Any]:
        """Chamada com repetição para falhas de rede/5xx/429 (espera crescente com variação). 4xx de negócio sobem como exceção tipada."""
        ultimo: Exception | None = None
        for i in range(tentativas):
            try:
                r = await self._http.request(method, "/coletores.php/" + path, json=body if method == "POST" else None, params=None if method == "POST" else body)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                ultimo = ServerUnavailable(f"{type(e).__name__} em {path}")
                ultimo.__cause__ = e
                if self.observer:
                    self.observer(False)
            else:
                if r.status_code == 200:
                    try:
                        payload = r.json()
                        data = payload["dados"]
                        if not isinstance(data, dict):
                            raise ValueError("dados inválidos")
                    except (ValueError, KeyError, TypeError):
                        raise EndpointError("Resposta fora do contrato JSON.", status=200) from None
                    if self.observer:
                        self.observer(True)
                    return data
                if self.observer:
                    self.observer(False)
                if 300 <= r.status_code < 400:
                    raise EndpointError("Redirecionamento recusado; confira a URL da API.", status=r.status_code)
                msg = self._msg(r)
                try:
                    code = r.json().get("erro", {}).get("codigo")
                except (ValueError, AttributeError):
                    code = None
                if r.status_code in (401, 403):
                    raise Unauthorized(msg, status=r.status_code, error_code=code)
                if r.status_code == 404:
                    raise NotFound(msg, status=r.status_code, error_code=code)
                if r.status_code == 409:
                    raise LeaseLost(msg)
                if r.status_code in (400, 413, 422):
                    raise Rejected(msg, status=r.status_code, error_code=code)
                ra = r.headers.get("Retry-After")
                ultimo = ServerUnavailable(f"HTTP {r.status_code} em {path}: {msg}", float(ra) if ra and ra.isdigit() else None)
                ultimo.status = r.status_code
            if i < tentativas - 1:
                espera = ultimo.retry_after if isinstance(ultimo, ServerUnavailable) and ultimo.retry_after else min(30.0, 2.0 * 2**i)
                await self._sleep(espera * random.uniform(0.75, 1.25))
        assert ultimo is not None
        raise ultimo

    @staticmethod
    def _msg(r: httpx.Response) -> str:
        try:
            return str(r.json().get("erro", {}).get("mensagem", r.text[:200]))
        except (ValueError, AttributeError):
            return "Resposta fora do contrato JSON."

    # ---- contrato v1 -------------------------------------------------------------------------------------------------
    async def registrar(self, info: dict) -> dict:
        return await self._call("POST", "registrar", {"coletor": self.cfg.worker_name, **info})

    async def heartbeat(self, info: dict) -> dict:
        return await self._call("POST", "heartbeat", {"coletor": self.cfg.worker_name, **info})

    async def configuracao(self) -> dict:
        return await self._call("GET", "configuracao", {"coletor": self.cfg.worker_name})

    async def reservar(self, tipos: list[str]) -> dict:
        return await self._call("POST", "tarefas/reservar", {"coletor": self.cfg.worker_name, "tipos": tipos})

    async def renovar(self, tarefa_id: int, token: str, progresso: str | None = None) -> dict:
        return await self._call("POST", "tarefas/renovar", {"coletor": self.cfg.worker_name, "tarefa_id": tarefa_id, "lease_token": token, "progresso": progresso})

    async def resultados(self, tarefa_id: int, token: str, chave: str, itens: list) -> dict:
        """Só é considerado entregue se o servidor responder persistido=true."""
        r = await self._call("POST", "resultados", {"coletor": self.cfg.worker_name, "tarefa_id": tarefa_id, "lease_token": token, "chave": chave, "itens": itens})
        if not r.get("persistido"):
            raise ServerUnavailable("servidor não confirmou a gravação do lote")
        return r

    async def concluir(self, tarefa_id: int, token: str, resumo: dict) -> dict:
        return await self._call("POST", "tarefas/concluir", {"coletor": self.cfg.worker_name, "tarefa_id": tarefa_id, "lease_token": token, "resumo": resumo})

    async def falhar(self, tarefa_id: int, token: str, erro: str, *, retentavel: bool = True, sem_penalidade: bool = False) -> dict:
        return await self._call("POST", "tarefas/falhar", {"coletor": self.cfg.worker_name, "tarefa_id": tarefa_id, "lease_token": token, "erro": erro[:480],
                                                            "retentavel": retentavel, "sem_penalidade": sem_penalidade}, tentativas=3)

    async def vaga(self, fonte: str) -> dict:
        return await self._call("POST", "limites/vaga", {"coletor": self.cfg.worker_name, "fonte": fonte})

    async def resultado_fonte(self, fonte: str, http: int, ms: float, retry_after: int | None = None) -> dict:
        return await self._call("POST", "limites/resultado", {"coletor": self.cfg.worker_name, "fonte": fonte, "http": http, "ms": ms, "retry_after": retry_after}, tentativas=2)
