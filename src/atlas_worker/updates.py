"""GitHub Releases: consulta separada do Radar e pacotes verificados antes de abrir."""
from __future__ import annotations

import hashlib
import os
import platform
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from packaging.version import InvalidVersion, Version

REPO = "nihause/atlas-coletor-distribuido"
API = f"https://api.github.com/repos/{REPO}"
ALLOWED_HOSTS = {"api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


@dataclass
class Release:
    version: str
    name: str
    asset_url: str
    sha256: str
    page_url: str


class ReleaseClient:
    def __init__(self, github_token: str = "", transport=None):
        # Este token é exclusivo do GitHub. Nunca use o WORKER_TOKEN aqui.
        self.token = github_token
        self.http = httpx.AsyncClient(timeout=30, follow_redirects=False, transport=transport)

    async def close(self):
        await self.http.aclose()

    async def request(self, url: str, accept="application/vnd.github+json", *, stream=False):
        for _ in range(6):
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
                raise ValueError("Endereço de atualização fora do GitHub.")
            headers = {"Accept": accept, "User-Agent": "atlas-coletor-updater"}
            if self.token and parsed.hostname == "api.github.com":
                headers["Authorization"] = "Bearer " + self.token
            response = await self.http.send(self.http.build_request("GET", url, headers=headers), stream=stream)
            if response.is_redirect:
                url = str(response.url.join(response.headers.get("Location", "")))
                await response.aclose()
                continue
            if response.status_code in (401, 403, 404):
                await response.aclose()
                raise ValueError("Não foi possível acessar os Releases. O repositório é privado: informe um token GitHub com leitura de conteúdo e confira se há uma versão publicada.")
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                await response.aclose()
                raise
            return response
        raise ValueError("Redirecionamentos excessivos ao buscar atualização.")

    async def latest(self, current: str, *, machine=None, os_release=None) -> Release | None:
        arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(machine or platform.machine())
        distro = os_release if os_release is not None else platform.freedesktop_os_release()
        if distro.get("ID") != "ubuntu" or distro.get("VERSION_ID") != "24.04" or not arch:
            raise ValueError("A atualização por pacote requer Ubuntu 24.04 e uma arquitetura publicada no Release.")
        payload = (await self.request(API + "/releases/latest")).json()
        try:
            version = Version(str(payload["tag_name"]).removeprefix("v"))
        except (KeyError, InvalidVersion):
            raise ValueError("Release sem versão válida.") from None
        if version <= Version(current):
            return None
        name = f"atlas-coletor_{version}_ubuntu24.04_{arch}.deb"
        assets = payload.get("assets", [])
        asset = next((a for a in assets if a.get("name") == name), None)
        if not asset:
            raise ValueError(f"Versão {version} publicada, mas sem pacote compatível {arch}.")
        digest = str(asset.get("digest", ""))
        sha = digest.removeprefix("sha256:") if digest.startswith("sha256:") else ""
        if not re.fullmatch(r"[a-fA-F0-9]{64}", sha):
            checksum = next((a for a in assets if a.get("name") == name + ".sha256"), None)
            if not checksum:
                raise ValueError("Release sem checksum SHA-256. Atualização bloqueada.")
            content = (await self.request(str(checksum["url"]), "application/octet-stream")).text
            match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?" + re.escape(name) + r"\s*", content)
            if not match:
                raise ValueError("Checksum inválido para este pacote.")
            sha = match[1]
        return Release(str(version), name, str(asset["url"]), sha.lower(), f"https://github.com/{REPO}/releases/tag/v{version}")

    async def download(self, release: Release, directory: Path) -> Path:
        if not re.fullmatch(r"atlas-coletor_[0-9A-Za-z.+-]+_ubuntu24\.04_(amd64|arm64)\.deb", release.name):
            raise ValueError("Nome de pacote inválido.")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Download limitado e incremental; nenhum script remoto é executado.
        response = await self.request(release.asset_url, "application/octet-stream", stream=True)
        fd, tmp = tempfile.mkstemp(prefix="atlas-release-", dir=directory)
        try:
            digest = hashlib.sha256()
            size = 0
            with os.fdopen(fd, "wb") as out:
                async for block in response.aiter_bytes():
                    size += len(block)
                    if size > 1024 ** 3:
                        raise ValueError("O pacote excede o limite de 1 GB.")
                    digest.update(block)
                    out.write(block)
            if digest.hexdigest() != release.sha256:
                raise ValueError("Integridade inválida: SHA-256 diferente. O pacote não será instalado.")
            target = directory / release.name
            os.replace(tmp, target)
            return target
        finally:
            await response.aclose()
            Path(tmp).unlink(missing_ok=True)
