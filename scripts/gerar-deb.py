#!/usr/bin/env python3
"""Gera .deb autossuficiente no Ubuntu 24.04; todo staging fica fora do projeto."""
from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(output: Path):
    from atlas_worker import __version__
    os_info = platform.freedesktop_os_release()
    if os_info.get("ID") != "ubuntu" or os_info.get("VERSION_ID") != "24.04":
        raise SystemExit("Gere o pacote em Ubuntu 24.04 para garantir compatibilidade de bibliotecas.")
    arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
    if not arch: raise SystemExit("Arquitetura não suportada.")
    if not shutil.which("dpkg-deb"): raise SystemExit("Falta dpkg-deb.")
    output = output.expanduser().resolve(); output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="atlas-deb-") as tmp:
        stage = Path(tmp)
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed", "--name", "atlas-coletor", "--distpath", str(stage / "dist"), "--workpath", str(stage / "build"), "--specpath", str(stage), "--paths", str(ROOT / "src"), "--collect-data", "atlas_worker", "--exclude-module", "PySide6.QtWebEngineCore", "--exclude-module", "PySide6.QtWebEngineWidgets", str(ROOT / "packaging" / "launcher.py")], check=True, cwd=stage)
        package = stage / "package"
        app = package / "opt" / "atlas-coletor"
        app.parent.mkdir(parents=True)
        shutil.copytree(stage / "dist" / "atlas-coletor", app)
        bin_dir = package / "usr" / "bin"; bin_dir.mkdir(parents=True)
        for name, flag in [("atlas-coletor", ""), ("atlas-worker", "--cli ")]:
            wrapper = bin_dir / name
            wrapper.write_text('#!/bin/sh\nexec /opt/atlas-coletor/atlas-coletor ' + flag + '"$@"\n')
            wrapper.chmod(0o755)
        desktops = package / "usr" / "share" / "applications"; desktops.mkdir(parents=True)
        (desktops / "atlas-coletor.desktop").write_text("[Desktop Entry]\nType=Application\nName=ATLAS — Coletor Distribuído\nComment=Configure e acompanhe a coleta do Radar\nExec=atlas-coletor\nIcon=atlas-coletor\nTerminal=false\nCategories=Network;Utility;\nStartupWMClass=atlas-coletor\n")
        icons = package / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps"; icons.mkdir(parents=True)
        shutil.copy2(ROOT / "src" / "atlas_worker" / "gui" / "atlas.svg", icons / "atlas-coletor.svg")
        docs = package / "usr" / "share" / "doc" / "atlas-coletor"; docs.mkdir(parents=True)
        shutil.copy2(ROOT / "README.md", docs / "README.md")
        control = package / "DEBIAN"; control.mkdir()
        size = sum(p.stat().st_size for p in package.rglob('*') if p.is_file()) // 1024
        (control / "control").write_text(f"Package: atlas-coletor\nVersion: {__version__}\nSection: net\nPriority: optional\nArchitecture: {arch}\nMaintainer: Justisoft <contato@justisoft.com.br>\nInstalled-Size: {size}\nDepends: libc6 (>= 2.39), libglib2.0-0t64, libdbus-1-3, libfontconfig1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-xinerama0, libegl1, libgl1, libopengl0, libx11-xcb1, libxcb-shape0, libxcb-randr0, libxcb-xfixes0, libxcb-sync1\nDescription: Aplicativo gráfico Atlas Coletor Distribuído\n Interface PySide6 e motor do Radar com Python e Qt incluídos.\n Configurações individuais ficam no diretório do usuário e são preservadas.\n")
        target = output / f"atlas-coletor_{__version__}_ubuntu24.04_{arch}.deb"
        subprocess.run(["dpkg-deb", "-Zzstd", "-z6", "--threads-max=2", "--root-owner-group", "--build", str(package), str(target)], check=True)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(target.suffix + ".sha256").write_text(digest + "  " + target.name + "\n")
    print(target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads" / "atlas-coletor")
    build(parser.parse_args().output)
