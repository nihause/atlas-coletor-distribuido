"""Verificação offline do manifesto oficial, antes do download e da instalação."""
from __future__ import annotations
import base64
import hashlib
import json
import platform
import re
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging.version import Version, InvalidVersion
from .release_trust import PUBLIC_KEY_HEX

REPO = 'nihause/atlas-coletor-distribuido'

def verify_manifest(raw: bytes, signature: bytes, *, public_key=None) -> dict:
    try:
        if len(raw)>65536 or len(signature)>1024: raise ValueError()
        Ed25519PublicKey.from_public_bytes(public_key or bytes.fromhex(PUBLIC_KEY_HEX)).verify(base64.b64decode(signature,validate=True),raw)
        data=json.loads(raw)
        if data['repository']!=REPO or data['schema']!=1: raise ValueError()
        if not re.fullmatch(r'\d+\.\d+\.\d+',data['version']): raise ValueError()
        version=Version(data['version'])
        if version.is_prerelease or version.is_devrelease or version.local: raise ValueError()
        if not data['packages'] or len(data['packages'])>4: raise ValueError()
        for p in data['packages']:
            if p['os']!='ubuntu24.04' or p['arch'] not in ('amd64','arm64'): raise ValueError()
            if p['name']!=f"atlas-coletor_{version}_ubuntu24.04_{p['arch']}.deb": raise ValueError()
            if not re.fullmatch('[a-f0-9]{64}',p['sha256']) or not 0<p['size']<=1024**3: raise ValueError()
        return data
    except (InvalidSignature,KeyError,ValueError,TypeError,InvalidVersion) as exc:
        raise ValueError('Assinatura ou manifesto oficial inválido. Atualização bloqueada.') from exc

def platform_arch(machine=None, os_release=None):
    distro=os_release if os_release is not None else platform.freedesktop_os_release()
    arch={'x86_64':'amd64','aarch64':'arm64'}.get(machine or platform.machine())
    if distro.get('ID')!='ubuntu' or distro.get('VERSION_ID')!='24.04' or not arch:
        raise ValueError('A atualização por pacote requer Ubuntu 24.04 e arquitetura compatível.')
    return arch

def verify_package(path: Path, raw: bytes, signature: bytes, current: str, *, machine=None, os_release=None):
    data=verify_manifest(raw,signature)
    if Version(data['version'])<=Version(current): raise ValueError('Downgrade ou reinstalação não autorizada.')
    arch=platform_arch(machine,os_release)
    package=next((p for p in data['packages'] if p['name']==path.name and p['arch']==arch),None)
    if not package or path.stat().st_size!=package['size']: raise ValueError('Pacote incompatível ou tamanho inválido.')
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    if digest.hexdigest()!=package['sha256']:raise ValueError('Integridade inválida: SHA-256 diferente.')
    return data
