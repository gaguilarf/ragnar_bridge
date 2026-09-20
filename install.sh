#!/usr/bin/env bash
# Instala ragnar-bridge como servicio de systemd de usuario (sin root).
#
#   curl -fsSL https://raw.githubusercontent.com/gaguilarf/ragnar_bridge/main/install.sh \
#     | bash -s -- --agent claude --url wss://panel.ragnargroup.app/api/v1/bridge/ws --token ragbrg_...
#
# --agent claude  (default)  Claude Code: tiene que estar instalado y logueado.
# --agent agy                Antigravity CLI: tiene que estar instalado y logueado.
#
# El bridge usa TU sesion del CLI: no te pide credenciales y Ragnar nunca las
# ve. Cada bridge maneja UN agente; para tener los dos, corre este script dos
# veces con --name distinto (y un token distinto cada vez).
set -euo pipefail

AGENT="claude"
URL=""
TOKEN=""
WORKDIR="$HOME"
MODEL=""
NAME=""
SOURCE="git+https://github.com/gaguilarf/ragnar_bridge"

while [ $# -gt 0 ]; do
  case "$1" in
    --agent) AGENT="$2"; shift 2 ;;
    --url) URL="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --workdir) WORKDIR="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    *) echo "Argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$URL" ] || [ -z "$TOKEN" ]; then
  echo "Uso: install.sh [--agent claude|agy] --url wss://.../api/v1/bridge/ws --token ragbrg_... [--workdir DIR] [--model M] [--name N]" >&2
  exit 2
fi
case "$AGENT" in claude|agy) ;; *) echo "--agent tiene que ser claude o agy." >&2; exit 2 ;; esac

command -v python3 >/dev/null || { echo "Falta python3 (>= 3.9, con el modulo venv)." >&2; exit 1; }

CLI_BIN="$(command -v "$AGENT" || true)"
if [ -z "$CLI_BIN" ]; then
  echo "No encuentro \`$AGENT\` en el PATH." >&2
  if [ "$AGENT" = "claude" ]; then
    echo "  Instalalo:  curl -fsSL https://claude.ai/install.sh | bash   y logueate corriendo:  claude" >&2
  else
    echo "  Instalalo:  curl -fsSL https://antigravity.google/cli/install.sh | bash   y logueate corriendo:  agy" >&2
  fi
  echo "  (si acabas de instalarlo, abri una terminal nueva para que el PATH se recargue)" >&2
  exit 1
fi

SUFIJO=""
[ -n "$NAME" ] && SUFIJO="-$NAME"
CONFIG_DIR="$HOME/.config/ragnar-bridge"
CONFIG="$CONFIG_DIR/config$SUFIJO.json"
SERVICIO="ragnar-bridge$SUFIJO"
VENV="$HOME/.local/share/ragnar-bridge/venv"

echo "==> Instalando ragnar-bridge en $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet --upgrade "$SOURCE"

echo "==> Escribiendo la config en $CONFIG (permisos 600), agente: $AGENT"
INIT_ARGS=(--config "$CONFIG" init --url "$URL" --token "$TOKEN" --agent "$AGENT" --cli "$CLI_BIN" --workdir "$WORKDIR")
[ -n "$MODEL" ] && INIT_ARGS+=(--model "$MODEL")
"$VENV/bin/ragnar-bridge" "${INIT_ARGS[@]}"

echo "==> Verificando (config, CLI y conexion con Ragnar; no gasta cuota)"
if ! "$VENV/bin/ragnar-bridge" --config "$CONFIG" doctor; then
  echo >&2
  echo "Algun paso fallo (arriba). Corregilo y corre:  $VENV/bin/ragnar-bridge --config $CONFIG doctor" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null || ! systemctl --user show-environment >/dev/null 2>&1; then
  echo
  echo "No hay systemd de usuario disponible. Para correrlo a mano:"
  echo "  $VENV/bin/ragnar-bridge --config $CONFIG run"
  exit 0
fi

UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/$SERVICIO.service" <<UNIT
[Unit]
Description=Ragnar bridge ($AGENT)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=$VENV/bin/ragnar-bridge --config $CONFIG run
Restart=always
RestartSec=5
# Salida 78 = Ragnar rechazo el token (revocado/invalido): reintentar no sirve.
RestartPreventExitStatus=78
# El CLI (y Node, en el caso de claude) tienen que estar en el PATH del servicio.
Environment=PATH=$PATH

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICIO.service"

# Sin linger el servicio de usuario muere al cerrar tu sesion SSH.
if ! loginctl enable-linger "$USER" 2>/dev/null; then
  echo "AVISO: no pude activar linger; el bridge se detendra al cerrar tu sesion." >&2
  echo "       Corre una vez como root:  loginctl enable-linger $USER" >&2
fi

echo
echo "Listo. Ya deberias verlo conectado (punto verde) en la app de Ragnar."
echo "  Estado:  systemctl --user status $SERVICIO"
echo "  Logs:    journalctl --user -u $SERVICIO -f"
echo "  Chequeo: $VENV/bin/ragnar-bridge --config $CONFIG doctor"
