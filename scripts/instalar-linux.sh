#!/usr/bin/env bash
# Instala o coletor neste computador (Ubuntu/Linux): ambiente virtual, dependências, configuração e (opcional) serviço systemd.
# Não sobrescreve configuração nem serviço existentes (use --forcar-config / --forcar-servico, conscientemente).
# Uso:  scripts/instalar-linux.sh [--url URL] [--nome NOME] [--token-arquivo ARQ] [--servico | --sem-servico] [--forcar-config] [--forcar-servico]
#   --permitir-http-local: só para testes com servidor em 127.0.0.1 (http); a configuração recusa http em qualquer outro endereço.
#   Sem opções, pergunta o que faltar. O token é lido sem eco ou de um arquivo; nunca vai para a linha de comando nem para o Git.
set -euo pipefail
cd "$(dirname "$0")/.."
RAIZ=$(pwd); URL=""; NOME=""; TOKEN_ARQ=""; SERVICO="perguntar"; FORCAR_CFG=0; FORCAR_SVC=0; HTTP_LOCAL=0
while [ $# -gt 0 ]; do case "$1" in
  --url) URL=$2; shift 2;; --nome) NOME=$2; shift 2;; --token-arquivo) TOKEN_ARQ=$2; shift 2;;
  --servico) SERVICO=sim; shift;; --sem-servico) SERVICO=nao; shift;; --forcar-config) FORCAR_CFG=1; shift;; --forcar-servico) FORCAR_SVC=1; shift;; --permitir-http-local) HTTP_LOCAL=1; shift;;
  -h|--help) sed -n 2,7p "$0"; exit 0;; *) echo "Opção desconhecida: $1"; exit 2;; esac; done
umask 077

# 1) Python 3.11+
PY=""; for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then PY=$c; break; fi; done
[ -n "$PY" ] || { echo "Python 3.11 ou superior não encontrado. Ubuntu: sudo apt install python3 python3-venv python3-pip"; exit 1; }
"$PY" -c 'import venv, ensurepip' 2>/dev/null || { echo "Falta o módulo venv. Ubuntu: sudo apt install python3-venv"; exit 1; }
echo "Python: $($PY --version)"

# 2) Ambiente virtual e dependências
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e .
echo "Dependências instaladas: $(.venv/bin/atlas-worker version)"

# 3) Configuração (.env): só cria se não existir
if [ -f .env ] && [ "$FORCAR_CFG" = "0" ]; then
  echo "Configuração existente mantida (.env). Use --forcar-config para recriar."
else
  [ -n "$URL" ] || read -r -p "Endereço da API do Radar (ex.: https://servidor.exemplo.com/radar/api/v1): " URL
  [ -n "$NOME" ] || { sugestao="coletor-$(hostname -s | tr -c 'A-Za-z0-9\n' '-' | cut -c1-40)"; read -r -p "Nome deste computador [$sugestao]: " NOME; NOME=${NOME:-$sugestao}; }
  if [ -n "$TOKEN_ARQ" ]; then TOKEN=$(tr -d '[:space:]' < "$TOKEN_ARQ"); else read -r -s -p "Chave de API deste computador (não aparece na tela): " TOKEN; echo; fi
  [ -n "$TOKEN" ] || { echo "Chave vazia."; exit 1; }
  [ ! -f .env ] || cp -p .env ".env.anterior.$(date +%Y%m%d%H%M%S)"
  { sed -e "s|^RADAR_API_URL=.*|RADAR_API_URL=$URL|" -e "s|^WORKER_NAME=\([^ #]*\).*|WORKER_NAME=$NOME|" -e "s|^WORKER_TOKEN=.*|WORKER_TOKEN=$TOKEN|" .env.example; } > .env
  [ "$HTTP_LOCAL" = "0" ] || echo 'ALLOW_INSECURE_HTTP=1' >> .env    # só testes em 127.0.0.1; a configuração recusa http em qualquer outro endereço
  chmod 600 .env
  echo "Configuração gravada em $RAIZ/.env (permissão 600)."
fi

# 4) Confere a conexão
echo "Verificando a conexão com o servidor..."
.venv/bin/atlas-worker --env .env verificar || { echo "A verificação falhou: corrija o .env e rode: .venv/bin/atlas-worker --env .env verificar"; exit 1; }

# 5) Serviço systemd (inicia com o sistema e reinicia após falhas)
mkdir -p deploy-gerado
cat > deploy-gerado/atlas-worker.service <<UNIT
[Unit]
Description=Atlas Worker - coletor distribuido do Atlas/Radar
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(id -un)
WorkingDirectory=$RAIZ
ExecStart=$RAIZ/.venv/bin/atlas-worker --env $RAIZ/.env run
Restart=always
RestartSec=10
TimeoutStopSec=60
KillSignal=SIGTERM
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full

[Install]
WantedBy=multi-user.target
UNIT
echo "Unidade gerada: deploy-gerado/atlas-worker.service"
if [ "$SERVICO" = "perguntar" ]; then read -r -p "Instalar e iniciar o serviço systemd agora (pede sudo)? [s/N] " r; case "$r" in s|S) SERVICO=sim;; *) SERVICO=nao;; esac; fi
if [ "$SERVICO" = "sim" ]; then
  if [ -f /etc/systemd/system/atlas-worker.service ] && [ "$FORCAR_SVC" = "0" ]; then
    echo "O serviço já existe em /etc/systemd/system; mantido. Use --forcar-servico para substituir."
  else
    SUDO=""; [ "$(id -u)" = "0" ] || SUDO="sudo"
    $SUDO install -m 644 deploy-gerado/atlas-worker.service /etc/systemd/system/atlas-worker.service
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now atlas-worker.service
    echo "Serviço ativo. Acompanhar: journalctl -u atlas-worker -f"
  fi
else
  echo "Para instalar o serviço depois:  sudo install -m 644 $RAIZ/deploy-gerado/atlas-worker.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now atlas-worker"
  echo "Para rodar agora em primeiro plano:  scripts/iniciar-linux.sh"
fi
