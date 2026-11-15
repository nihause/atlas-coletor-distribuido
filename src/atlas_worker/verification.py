"""Uma validação para CLI e interface, com diagnóstico baseado em evidências."""
from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass, field

import httpx

from . import CONTRATO, __version__
from .client import ClientError, EndpointError, RadarClient, Unauthorized
from .config import Settings
from .metrics import identidade_maquina


@dataclass
class Verification:
    code: int
    message: str
    detail: str = ""
    data: dict = field(default_factory=dict)


def classify(exc: Exception) -> Verification:
    status = getattr(exc, "status", None)
    if isinstance(exc, Unauthorized):
        if status == 401:
            return Verification(4, "Chave de API recusada pelo Radar.", "Confira a chave: ela pode estar inválida, expirada ou revogada.")
        if getattr(exc, "error_code", None) == "sem_permissao":
            return Verification(4, "Chave sem permissão de ingestão.", "No Radar, confira a permissão Ingestão desta integração.")
        return Verification(4, "Acesso recusado pelo Radar.", "A chave pode pertencer a outro coletor. Confira o identificador e as permissões no Radar.")
    if getattr(exc, "error_code", None) == "contrato_incompativel":
        return Verification(3, "Versão incompatível da API.", "Atualize o aplicativo e confira a versão do servidor.")
    if isinstance(exc, EndpointError) or status == 404:
        return Verification(5, "Endereço da API incorreto ou resposta inesperada.", f"HTTP {status or '200'}: confira a URL base /radar/api/v1. Redirecionamentos não são seguidos.")
    causes = []
    current: BaseException | None = exc
    while current and current not in causes:
        causes.append(current)
        current = current.__cause__ or current.__context__
    if any(isinstance(e, ssl.SSLCertVerificationError) for e in causes):
        return Verification(5, "Erro de certificado SSL.", "Confira o certificado do Radar e o relógio do computador. A validação TLS permanece obrigatória.")
    if any(isinstance(e, socket.gaierror) for e in causes):
        return Verification(5, "Falha de DNS.", "O nome do servidor não foi resolvido. Confira o endereço e a conexão de rede.")
    if any(isinstance(e, httpx.TimeoutException) for e in causes):
        return Verification(5, "Tempo de conexão esgotado.", "O Radar não respondeu dentro do prazo. Confira a rede e tente novamente.")
    return Verification(5, "Servidor indisponível.", f"{type(exc).__name__}" + (f" · HTTP {status}" if status else " · Não foi possível concluir a comunicação com o Radar."))


async def check_connection(cfg: Settings, client_factory=RadarClient) -> Verification:
    client = client_factory(cfg)
    try:
        data = await client.registrar({**identidade_maquina(), "nome": cfg.worker_name, "versao": __version__})
        if data.get("contrato") != CONTRATO:
            return Verification(3, "Versão incompatível da API.", f"Servidor: {data.get('contrato')}; aplicativo: {CONTRATO}.")
        return Verification(0, "Conectado com sucesso.", f"Contrato {CONTRATO}; comando do servidor: {data.get('comando', 'não informado')}.", data)
    except ClientError as exc:
        return classify(exc)
    finally:
        await client.aclose()
