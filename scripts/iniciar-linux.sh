#!/usr/bin/env bash
# Executa o coletor em primeiro plano (Ctrl+C encerra com segurança: a tarefa em curso é devolvida pela reserva).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/atlas-worker ] || { echo "Rode primeiro: scripts/instalar-linux.sh"; exit 1; }
[ -f .env ] || { echo "Falta o arquivo .env: rode scripts/instalar-linux.sh"; exit 1; }
exec .venv/bin/atlas-worker --env .env run
