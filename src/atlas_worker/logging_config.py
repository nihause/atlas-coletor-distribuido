"""Logs estruturados rotativos e sanitizados, inclusive exceções."""
from __future__ import annotations

import json
import logging
import logging.handlers
import re
from datetime import datetime, timezone
from pathlib import Path


def sanitize(text: str, secrets=()) -> str:
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, "***")
    text = re.sub(r"(?i)(Bearer\s+)[^\s\"']+", r"\1***", text)
    text = re.sub(r"radar_[A-Za-z0-9_-]+", "***", text)
    text = re.sub(r"(?i)((?:WORKER_TOKEN|DATAJUD_API_KEY|token|senha|password|api_key)[\"']?\s*[:=]\s*)[^\s,}]+", r"\1***", text)
    return text


class RedactFilter(logging.Filter):
    def __init__(self, secrets: list[str]):
        super().__init__()
        self.secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg, record.args = sanitize(record.getMessage(), self.secrets), ()
        if record.exc_info:
            record.exc_text = sanitize(logging.Formatter().formatException(record.exc_info), self.secrets)
            record.exc_info = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        task = re.search(r"tarefa\s+(\d+)", message)
        return json.dumps({"time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(), "level": record.levelname,
                           "event": record.name, "message": message, "task_id": int(task[1]) if task else None,
                           "detail": record.exc_text or ""}, ensure_ascii=False)


def setup(level: str, state_dir: Path, secrets: list[str]) -> None:
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(level)
    red = RedactFilter(secrets)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    sh.addFilter(red)
    root.addHandler(sh)
    try:
        logdir = state_dir / "logs"
        logdir.mkdir(parents=True, exist_ok=True, mode=0o700)
        fh = logging.handlers.RotatingFileHandler(logdir / "worker.log", maxBytes=10 * 2**20, backupCount=5, encoding="utf-8")
        fh.setFormatter(JsonFormatter())
        fh.addFilter(red)
        root.addHandler(fh)
    except OSError:
        root.warning("sem log em arquivo; usando só a saída padrão")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
