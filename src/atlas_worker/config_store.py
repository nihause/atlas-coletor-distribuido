"""Persistência atômica privada; mantém opções de instalações anteriores."""
from __future__ import annotations

import json
import os
import socket
import platform
import tempfile
from pathlib import Path

from dotenv import dotenv_values

from .config import Settings
from .datajud_public import DATAJUD_PUBLIC_KEY

DEFAULT_API = "https://justisoft.com.br/radar/api/v1"


def config_path() -> Path:
    if platform.system() == 'Windows' and 'XDG_CONFIG_HOME' not in os.environ:
        legacy=Path.home()/'.config'/'atlas-worker'/'.env'
        if legacy.is_file(): return legacy
        return Path(os.environ.get('APPDATA',str(Path.home()/'AppData'/'Roaming')))/'atlas-worker'/'.env'
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "atlas-worker" / ".env"


def atomic_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("O arquivo de configuração não pode ser um link simbólico.")
    fd, name = tempfile.mkstemp(prefix=".atlas-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            if os.name != 'nt': os.fchmod(out.fileno(), 0o600)
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path.expanduser().resolve() if not path.is_symlink() else path

    def load(self) -> dict[str, str]:
        return {k: v or "" for k, v in dotenv_values(self.path, interpolate=False).items()}

    def settings(self, values: dict[str, str]) -> Settings:
        # Argumentos explícitos prevalecem sobre o ambiente do processo.
        return Settings(_env_file=None, **{k.lower(): v for k, v in values.items()})

    def save(self, changes: dict[str, str]) -> Settings:
        values = {**self.load(), **changes}
        cfg = self.settings(values)
        # Aspas simples do dotenv: não expandir ${VAR}, $, # ou quebras de linha.
        def quoted(value: str) -> str:
            return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
        text = "# Configuração local do Atlas. Não compartilhar este arquivo.\n"
        text += "".join(f"{key}={quoted(value)}\n" for key, value in values.items())
        atomic_private(self.path, text)
        return cfg


def defaults() -> dict[str, str]:
    import re
    name = re.sub(r"[^A-Za-z0-9_.:-]", "-", socket.gethostname())[:50]
    return {"RADAR_API_URL": DEFAULT_API, "WORKER_NAME": "coletor-" + name, "WORKER_TOKEN": "", "MAX_CONCURRENCY": "4", "HEARTBEAT_INTERVAL": "30", "LOG_LEVEL": "INFO", "DATAJUD_API_KEY": DATAJUD_PUBLIC_KEY}


def save_preferences(path: Path, values: dict) -> None:
    atomic_private(path, json.dumps(values, ensure_ascii=False))
