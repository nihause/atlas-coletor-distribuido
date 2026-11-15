#!/usr/bin/env bash
# Instalação por usuário a partir do código; não altera .env nem serviços existentes.
set -euo pipefail
ATLAS_ROOT=$(cd "$(dirname "$0")/.." && pwd)
command -v zenity >/dev/null || { echo 'Use o pacote .deb pelo instalador gráfico do Ubuntu. Este instalador alternativo requer Zenity.'; exit 1; }
. /etc/os-release
[ "${ID:-}" = ubuntu ] || { zenity --error --text='Este instalador é destinado ao Ubuntu.'; exit 1; }
if ! command -v python3 >/dev/null || ! python3 -c 'import venv, ensurepip, sys, ctypes; assert sys.version_info >= (3,11); ctypes.CDLL("libxcb-cursor.so.0"); ctypes.CDLL("libxkbcommon-x11.so.0"); ctypes.CDLL("libOpenGL.so.0")' 2>/dev/null; then
  zenity --question --text='Instalar Python 3, venv e dependências gráficas? O Ubuntu solicitará autorização de administrador.' || exit 0
  pkexec /usr/bin/apt-get install -y python3 python3-venv libxcb-cursor0 libxkbcommon-x11-0 libopengl0
fi
ATLAS_STATUS=$(mktemp -d /tmp/atlas-instalar.XXXXXX)
trap 'rm -rf "$ATLAS_STATUS"' EXIT
(
  [ -d "$ATLAS_ROOT/.venv" ] || python3 -m venv "$ATLAS_ROOT/.venv"
  "$ATLAS_ROOT/.venv/bin/python" -m pip install "$ATLAS_ROOT[gui]"
  "$ATLAS_ROOT/.venv/bin/python" - "$ATLAS_ROOT" <<'PY'
import os, sys
from pathlib import Path
from atlas_worker.gui.desktop import desktop_quote
root = Path(sys.argv[1])
apps = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'applications'
apps.mkdir(parents=True, exist_ok=True)
command = [str(root / '.venv/bin/atlas-coletor')]
if (root / '.env').exists(): command += ['--env', str(root / '.env')]
(apps / 'atlas-coletor.desktop').write_text('[Desktop Entry]\nType=Application\nName=ATLAS — Coletor Distribuído\nExec=' + ' '.join(desktop_quote(x) for x in command) + '\nIcon=' + str(root / 'src/atlas_worker/gui/atlas.svg') + '\nTerminal=false\nCategories=Network;Utility;\n')
PY
) > "$ATLAS_STATUS/instalacao.log" 2>&1 &
ATLAS_PID=$!
# O progresso fecha quando a instalação termina; não usa cancelamento para deixar pip órfão.
(while kill -0 "$ATLAS_PID" 2>/dev/null; do echo '# Instalando Atlas e dependências…'; sleep 1; done; echo 100) | zenity --progress --pulsate --auto-close --no-cancel --title='Instalar Atlas Coletor' || true
if wait "$ATLAS_PID"; then
  zenity --info --text="Atlas instalado no menu de aplicativos do Ubuntu. Sua configuração foi preservada."
else
  zenity --error --text='Não foi possível instalar o Atlas. Confira a conexão e as dependências do Ubuntu.'
  exit 1
fi
