#!/usr/bin/env bash
# Instala ragnar-bridge como servicio de systemd (usuario, sin root).
#
#   curl -fsSL https://raw.githubusercontent.com/gaguilarf/ragnar_bridge/main/install.sh \
#     | bash -s -- --url wss://panel.ragnargroup.app/api/v1/bridge/ws --token ragbrg_...
#
# Requisitos: python3 >= 3.9 con venv, y `claude` instalado y logueado (correlo
# una vez a mano). El bridge usa TU sesion de Claude: no te pide credenciales
# y Ragnar nunca las ve.
set -euo pipefail

URL=""
TOKEN=""
WORKDIR="$HOME"
SOURCE="git+https://github.com/gaguilarf/ragnar_bridge"

while [ $# -gt 0 ]; do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --workdir) WORKDIR="$2"; shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    *) echo "Argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$URL" ] || [ -z "$TOKEN" ]; then
  echo "Uso: install.sh --url wss://.../api/v1/bridge/ws --token ragbrg_... [--workdir DIR]" >&2
  exit 2
fi

command -v python3 >/dev/null || { echo "Falta python3." >&2; exit 1; }
CLAUDE_BIN="$(command -v claude || true)"
if [ -z "$CLAUDE_BIN" ]; then
  echo "No encuentro \`claude\` en el PATH. Instalalo y logueate una vez (corre \`claude\`), y volve a correr esto." >&2
  exit 1
fi

VENV="$HOME/.local/share/ragnar-bridge/venv"
echo "==> Creando entorno en $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet --upgrade "$SOURCE"

echo "==> Escribiendo la config (permisos 600)"
"$VENV/bin/ragnar-bridge" init --url "$URL" --token "$TOKEN" --claude "$CLAUDE_BIN" --workdir "$WORKDIR"

if ! command -v systemctl >/dev/null || ! systemctl --user show-environment >/dev/null 2>&1; then
  echo
  echo "No hay systemd de usuario disponible. Para correrlo a mano:"
  echo "  $VENV/bin/ragnar-bridge run"
  exit 0
fi

UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/ragnar-bridge.service" <<UNIT
[Unit]
Description=Ragnar bridge (conecta tu CLI de Claude con Ragnar)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=$VENV/bin/ragnar-bridge run
Restart=always
RestartSec=5
# Salida 78 = Ragnar rechazo el token (revocado/invalido): reintentar no sirve.
RestartPreventExitStatus=78
# El CLI y Node tienen que estar en el PATH del servicio.
Environment=PATH=$PATH

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now ragnar-bridge.service

# Sin linger el servicio de usuario muere al cerrar tu sesion SSH.
if ! loginctl enable-linger "$USER" 2>/dev/null; then
  echo "AVISO: no pude activar linger; el bridge se detendra al cerrar tu sesion." >&2
  echo "       Corre una vez como root:  loginctl enable-linger $USER" >&2
fi

echo
echo "Listo. Estado:   systemctl --user status ragnar-bridge"
echo "      Logs:      journalctl --user -u ragnar-bridge -f"
