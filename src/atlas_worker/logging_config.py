"""Logs em stdout e arquivo rotativo. O token nunca entra no log (filtro garante, mesmo por engano)."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


class RedactFilter(logging.Filter):
    def __init__(self, secrets: list[str]):
        super().__init__()
        self.secrets = [s for s in secrets if s and len(s) >= 8]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for s in self.secrets:
            msg = msg.replace(s, "***")
        record.msg, record.args = msg, ()
        return True


def setup(level: str, state_dir: Path, secrets: list[str]) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    red = RedactFilter(secrets)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.addFilter(red)
    root.addHandler(sh)
    try:
        logdir = state_dir / "logs"
        logdir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(logdir / "worker.log", maxBytes=10 * 2**20, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.addFilter(red)
        root.addHandler(fh)
    except OSError:
        root.warning("sem log em arquivo; usando só a saída padrão")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
