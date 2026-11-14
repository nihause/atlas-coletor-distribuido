#!/usr/bin/env bash
# Confere conexão, chave e contrato com o servidor, sem pedir tarefa.
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/atlas-worker --env .env verificar
