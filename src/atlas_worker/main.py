"""Linha de comando: atlas-worker run | verificar | version."""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from pydantic import ValidationError

from . import CONTRATO, __version__
from .client import ClientError, RadarClient, Unauthorized
from .config import Settings
from .logging_config import setup
from .metrics import identidade_maquina
from .worker import Worker

log = logging.getLogger("atlas_worker")


def carregar(env_file: str | None) -> Settings:
    try:
        return Settings(_env_file=env_file) if env_file else Settings()
    except ValidationError as e:
        print("Configuração inválida:", file=sys.stderr)
        for err in e.errors():
            print(f"  - {'.'.join(str(x) for x in err['loc']) or 'configuração'}: {err['msg']}", file=sys.stderr)
        raise SystemExit(2)


async def verificar(cfg: Settings) -> int:
    """Confere URL, TLS, chave e contrato, sem pedir nem executar tarefa. Saída 0 = pronto."""
    from .verification import check_connection
    result = await check_connection(cfg, RadarClient)
    print(f"Servidor: {cfg.base_url}")
    print(result.message, file=sys.stdout if result.code == 0 else sys.stderr)
    print(result.detail, file=sys.stdout if result.code == 0 else sys.stderr)
    if result.code == 0:
        r = result.data
        print(f"Autenticação: ok   Coletor: {cfg.worker_name}   Contrato: {CONTRATO}   Comando atual: {r.get('comando')}")
        lim = r.get("limites", {})
        print(f"Limites globais: DataJud {lim.get('datajud_min', '?')}/min, DJEN remoto {lim.get('djen_min', '?')}/min")
        if "datajud_lote" in cfg.types and not cfg.datajud_api_key.get_secret_value():
            print("Aviso: DATAJUD_API_KEY vazia; tarefas datajud_lote serão recusadas neste computador.")
    return result.code


async def rodar(cfg: Settings, uma_rodada: bool) -> None:
    client = RadarClient(cfg)
    w = Worker(cfg, client)
    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for s in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(s, w.parar.set)
    try:
        await w.rodar(uma_rodada)
    finally:
        await client.aclose()
        if w._http_proprio:
            await w.http.aclose()


def cli(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="atlas-worker", description="Coletor distribuído do Atlas/Radar")
    ap.add_argument("--env", help="arquivo de configuração (padrão: .env na pasta atual)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="executa o coletor")
    r.add_argument("--uma-rodada", action="store_true", help="sai quando não houver mais tarefas (testes)")
    sub.add_parser("verificar", help="confere conexão, chave e contrato")
    sub.add_parser("version")
    a = ap.parse_args(argv)
    if a.cmd == "version":
        print(f"atlas-worker {__version__} (contrato {CONTRATO})")
        return
    cfg = carregar(a.env)
    setup(cfg.log_level, cfg.state_dir, [cfg.worker_token.get_secret_value(), cfg.datajud_api_key.get_secret_value()])
    if a.cmd == "verificar":
        raise SystemExit(asyncio.run(verificar(cfg)))
    from .instance import AlreadyRunning, RunLock
    try:
        with RunLock(cfg):
            asyncio.run(rodar(cfg, a.uma_rodada))
    except AlreadyRunning as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(6)


if __name__ == "__main__":
    cli()
