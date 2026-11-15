"""Integração de sessão sem sudo e sem alterar serviços de instalações anteriores."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from ..config_store import atomic_private


def executable_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "atlas_worker.gui.app"]


def desktop_quote(arg: str) -> str:
    # Exec não é shell; escape reservado pelo Desktop Entry Specification.
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%") + '"'


def autostart_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "autostart" / "atlas-coletor.desktop"


def set_autostart(enabled: bool, env_path: Path):
    path = autostart_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    command = executable_command() + ["--env", str(env_path), "--start"]
    atomic_private(path, "[Desktop Entry]\nType=Application\nName=Atlas Coletor\nExec=" + " ".join(desktop_quote(a) for a in command) + "\nIcon=atlas-coletor\nTerminal=false\nX-GNOME-Autostart-enabled=true\n")
