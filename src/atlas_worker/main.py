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
    c = RadarClient(cfg)
    try:
        print(f"Servidor: {cfg.base_url}  ({'HTTPS' if cfg.base_url.startswith('https') else 'HTTP local de teste'})")
        r = await c.registrar({**identidade_maquina(), "nome": cfg.worker_name, "versao": __version__})
        print(f"Autenticação: ok   Coletor: {cfg.worker_name}   Contrato: {r.get('contrato')} (este coletor: {CONTRATO})   Comando atual: {r.get('comando')}")
        lim = r.get("limites", {})
        print(f"Limites globais: DataJud {lim.get('datajud_min', '?')}/min, DJEN remoto {lim.get('djen_min', '?')}/min   Tarefas simultâneas: {r.get('max_concorrencia')}")
        if r.get("contrato") != CONTRATO:
            print("ATENÇÃO: contrato diferente; atualize o coletor (scripts/atualizar-linux.sh)", file=sys.stderr)
            return 3
        if "datajud_lote" in cfg.types and not cfg.datajud_api_key.get_secret_value():
            print("Aviso: DATAJUD_API_KEY vazia; tarefas datajud_lote serão recusadas neste computador.")
        return 0
    except Unauthorized as e:
        print(f"Chave recusada pelo servidor: {e}", file=sys.stderr)
        return 4
    except ClientError as e:
        print(f"Não foi possível falar com o servidor: {e}", file=sys.stderr)
        return 5
    finally:
        await c.aclose()


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
    asyncio.run(rodar(cfg, a.uma_rodada))


if __name__ == "__main__":
    cli()
