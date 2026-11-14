#!/usr/bin/env bash
# Atualiza o coletor pelo Git preservando a configuração local (.env, estado e logs ficam fora do Git).
# Recusa atualizar se houver alteração local em arquivos versionados. Reinicia o serviço se ele estiver ativo.
set -euo pipefail
cd "$(dirname "$0")/.."
git rev-parse --git-dir >/dev/null 2>&1 || { echo "Esta pasta não é um clone do Git."; exit 1; }
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then echo "Há alterações locais em arquivos versionados; não vou sobrescrevê-las:"; git status --short --untracked-files=no; exit 1; fi
ANTES=$(git rev-parse --short HEAD)
git fetch --quiet origin
git pull --ff-only --quiet
DEPOIS=$(git rev-parse --short HEAD)
[ -x .venv/bin/pip ] || { echo "Ambiente virtual ausente: rode scripts/instalar-linux.sh"; exit 1; }
.venv/bin/pip install --quiet -e .
echo "Versão: $(.venv/bin/atlas-worker version)  ($ANTES -> $DEPOIS)"
if systemctl is-active --quiet atlas-worker 2>/dev/null; then
  SUDO=""; [ "$(id -u)" = "0" ] || SUDO="sudo"
  $SUDO systemctl restart atlas-worker && echo "Serviço reiniciado (a tarefa em curso é devolvida e retomada)."
fi
.venv/bin/atlas-worker --env .env verificar || echo "Atenção: a verificação falhou depois da atualização."
