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
from .release_manifest import verify_manifest, verify_package, platform_arch
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
    notes: str = ""
    manifest: bytes = b""
    signature: bytes = b""
    current: str = "0"
    size: int = 0


class ReleaseClient:
    def __init__(self, github_token: str = "", transport=None):
        # Este token é exclusivo do GitHub. Nunca use o WORKER_TOKEN aqui.
        self.available_version = ""
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
            if response.status_code in (403, 429):
                await response.aclose()
                raise ValueError("GitHub limitou a consulta ou recusou o acesso. Tente novamente mais tarde; confira a permissão se o repositório for privado.")
            if response.status_code == 404:
                await response.aclose()
                raise ValueError("Ainda não há Release disponível ou o repositório é privado sem acesso.")
            if response.status_code == 401:
                await response.aclose()
                raise ValueError("Credencial GitHub recusada. Repositórios públicos dispensam token.")
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                await response.aclose()
                raise
            return response
        raise ValueError("Redirecionamentos excessivos ao buscar atualização.")

    async def latest(self, current: str, *, machine=None, os_release=None) -> Release | None:
        arch = platform_arch(machine, os_release)
        payload = (await self.request(API + "/releases/latest")).json()
        try:
            version = Version(str(payload["tag_name"]).removeprefix("v"))
        except (KeyError, InvalidVersion):
            raise ValueError("Release sem versão válida.") from None
        self.available_version = str(version)
        if version <= Version(current):
            return None
        assets = payload.get("assets", [])
        def asset(name):
            result = next((a for a in assets if a.get("name") == name), None)
            if not result or not re.fullmatch(re.escape(API) + r"/releases/assets/[0-9]+", str(result.get("url", ""))):
                raise ValueError("Release sem manifesto assinado ou pacote oficial compatível.")
            return result
        raw = (await self.request(str(asset("manifest.json")["url"]), "application/octet-stream")).content
        signature = (await self.request(str(asset("manifest.sig")["url"]), "application/octet-stream")).content
        manifest = verify_manifest(raw, signature)
        if Version(manifest['version']) != version:
            raise ValueError("Versão do manifesto diverge da tag oficial.")
        package = next((p for p in manifest['packages'] if p['arch'] == arch), None)
        if not package:
            raise ValueError("Release sem pacote compatível com esta arquitetura.")
        entry = asset(package['name'])
        return Release(str(version), package['name'], str(entry['url']), package['sha256'],
                       f"https://github.com/{REPO}/releases/tag/v{version}", str(payload.get('body') or '')[:16000],
                       raw, signature, current, package['size'])

    async def download(self, release: Release, directory: Path, progress=None) -> Path:
        if not re.fullmatch(r"atlas-coletor_[0-9A-Za-z.+-]+_ubuntu24\.04_(amd64|arm64)\.deb", release.name):
            raise ValueError("Nome de pacote inválido.")
        manifest = verify_manifest(release.manifest, release.signature)
        package = next((p for p in manifest['packages'] if p['name'] == release.name), None)
        if not package or package['sha256'] != release.sha256 or Version(manifest['version']) <= Version(release.current):
            raise ValueError("Manifesto incompatível ou downgrade não autorizado.")
        if not re.fullmatch(re.escape(API) + r"/releases/assets/[0-9]+", release.asset_url):
            raise ValueError("Pacote fora do projeto oficial.")
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
                    if size > package['size']:
                        raise ValueError("O pacote excede o limite de 1 GB.")
                    digest.update(block)
                    out.write(block)
                    if progress: progress(size, package['size'])
            if size != package['size'] or digest.hexdigest() != release.sha256:
                raise ValueError("Integridade inválida: SHA-256 diferente. O pacote não será instalado.")
            target = directory / release.name
            os.replace(tmp, target)
            from .config_store import atomic_private
            atomic_private(target.with_suffix('.deb.manifest.json'), release.manifest.decode())
            atomic_private(target.with_suffix('.deb.manifest.sig'), release.signature.decode())
            return target
        finally:
            await response.aclose()
            Path(tmp).unlink(missing_ok=True)
