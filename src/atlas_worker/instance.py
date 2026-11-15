"""Travas entre CLI e GUI; não inicia um segundo motor na mesma identidade/estado."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .config import Settings, default_state_dir


class AlreadyRunning(RuntimeError):
    pass


class FileLock:
    def __init__(self, key: str):
        root = default_state_dir() / "locks"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / (hashlib.sha256(key.encode()).hexdigest() + ".lock")
        self.file = None

    def acquire(self):
        import sys
        self.file = self.path.open("a+b")
        os.chmod(self.path, 0o600)
        try:
            if sys.platform == "win32":
                import msvcrt
                if self.path.stat().st_size == 0:
                    self.file.write(b"0"); self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close(); self.file = None
            raise AlreadyRunning("Já existe uma instância usando este coletor ou estado local.") from None
        return self

    def close(self):
        if self.file:
            self.file.close(); self.file = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.close()


class RunLock:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.locks = [FileLock("worker:" + cfg.base_url.lower() + ":" + cfg.worker_name), FileLock("state:" + str(cfg.state_dir.resolve()))]

    def __enter__(self):
        try:
            for lock in self.locks:
                lock.acquire()
            self._legacy_running()
        except Exception:
            self.__exit__(); raise
        return self

    def __exit__(self, *_):
        for lock in self.locks:
            lock.close()

    def _legacy_running(self):
        """Instalações antigas ainda não usam a trava: confira processos sem pará-los."""
        import psutil
        for proc in psutil.process_iter(["pid", "cmdline"]):
            args = proc.info.get("cmdline") or []
            if proc.pid == os.getpid() or "run" not in args:
                continue
            if not any("atlas-worker" in arg or "atlas_worker" in arg for arg in args[:3]):
                continue
            try:
                env = Path(args[args.index("--env") + 1]) if "--env" in args else Path(".env")
                if not env.is_absolute():
                    env = Path(proc.cwd()) / env
                other = Settings(_env_file=env)
                if (other.worker_name == self.cfg.worker_name and other.base_url.lower() == self.cfg.base_url.lower()) or other.state_dir.resolve() == self.cfg.state_dir.resolve():
                    raise AlreadyRunning("Um coletor de terminal/serviço já está em execução. Pare-o antes de iniciar pela interface.")
            except (psutil.Error, OSError, ValueError):
                continue
