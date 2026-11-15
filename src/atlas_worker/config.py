"""Configuração por variáveis de ambiente / arquivo .env. Nada de segredo no código."""
from __future__ import annotations

import os
import platform
import re
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_state_dir() -> Path:
    if platform.system() == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "atlas-worker"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "atlas-worker"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    radar_api_url: str
    worker_name: str
    worker_token: SecretStr
    max_concurrency: int = Field(2, ge=1, le=8)
    heartbeat_interval: int = Field(30, ge=5, le=300)
    log_level: str = "INFO"
    task_types: str = "djen_janela,datajud_lote"
    datajud_api_key: SecretStr = SecretStr("")
    state_dir: Path = Field(default_factory=default_state_dir)
    request_timeout: float = Field(60.0, ge=5, le=300)
    datajud_timeout: float = Field(120.0, ge=10, le=300)
    allow_insecure_http: bool = False
    batch_items: int = Field(100, ge=10, le=500)

    @field_validator("worker_name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{3,64}", v):
            raise ValueError("WORKER_NAME deve ter 3 a 64 caracteres (letras, números e _.:-)")
        return v

    @field_validator("log_level")
    @classmethod
    def _level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("LOG_LEVEL inválido")
        return v

    @model_validator(mode="after")
    def _url(self) -> "Settings":
        u = urlparse(self.radar_api_url)
        if u.scheme not in ("https", "http") or not u.netloc:
            raise ValueError("RADAR_API_URL inválida")
        if u.username or u.password or u.query or u.fragment:
            raise ValueError("RADAR_API_URL não pode conter credenciais, parâmetros ou fragmentos")
        loopback = (u.hostname or "") in ("127.0.0.1", "localhost", "::1")
        if u.scheme == "http" and not (self.allow_insecure_http and loopback):
            raise ValueError("RADAR_API_URL deve usar HTTPS (http só com ALLOW_INSECURE_HTTP=1 e endereço local, para testes)")
        if not self.worker_token.get_secret_value():
            raise ValueError("WORKER_TOKEN vazio: crie a chave deste computador no Radar (Administração > API, permissão Ingestão)")
        return self

    @property
    def types(self) -> list[str]:
        return [t.strip() for t in self.task_types.split(",") if t.strip()]

    @property
    def base_url(self) -> str:
        return self.radar_api_url.rstrip("/")
