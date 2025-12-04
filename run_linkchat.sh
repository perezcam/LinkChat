#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------
# Lanza un par backend+UI con servicios NUEVOS nombrados por ALIAS,
# sin modificar docker-compose.yml. Perfecto para N laptops (cada una
# con su ALIAS) conectadas a un hotspot.

ENVFILE="${1:-.env}"
[[ -f "$ENVFILE" ]] || { echo "ERROR: no existe $ENVFILE"; exit 1; }

# Carga variables del .env
set -a
# shellcheck disable=SC1090
source "$ENVFILE"
set +a

# Validaciones mínimas
: "${ALIAS:?Define ALIAS en tu .env (p.ej. ALIAS=Jose)}"
: "${BASE_DIR:=/shared}"
: "${ETHER_TYPE:=0x88B5}"
: "${CHUNK_SIZE:=900}"
: "${LOG_LEVEL:=INFO}"
: "${XAUTH_HOST:=/home/$USER/.Xauthority}"   

if [[ -z "${WIFI_IFACE:-}" || "$WIFI_IFACE" == "auto" ]]; then
  WIFI_IFACE="$(ip -o link | awk -F': ' '/wl|wlan/{print $2; exit}')"
fi
if [[ -z "${WIFI_IFACE:-}" ]]; then
  echo "ADVERTENCIA: no pude detectar WIFI_IFACE; usando 'wlan0' por defecto."
  WIFI_IFACE="wlan0"
fi

safe_alias="$(echo "$ALIAS" | tr '[:upper:] ' '[:lower:]-' | tr -cd '[:alnum:]-')"
SVC_BACK="l2-${safe_alias}"
SVC_UI="ui-${safe_alias}"

echo "[launcher] ENV=$ENVFILE  ALIAS=$ALIAS  WIFI_IFACE=$WIFI_IFACE"
echo "[launcher] Servicios -> $SVC_BACK + $SVC_UI"

mkdir -p ./shared

# Genera override temporal con servicios NUEVOS
OVR_FILE="$(mktemp -t dc-over-${safe_alias}-XXXX.yml)"
trap 'rm -f "$OVR_FILE"' EXIT

cat > "$OVR_FILE" <<YAML
services:
  ${SVC_BACK}:
    image: linkchat-backend
    network_mode: host
    cap_add:
      - NET_RAW
      - NET_ADMIN
    environment:
      ALIAS: ${ALIAS}
      INTERFACE: ${WIFI_IFACE}
      IPC_SOCKET: /ipc/linkchat-${ALIAS}.sock
      BASE_DIR: ${BASE_DIR}
      ETHER_TYPE: ${ETHER_TYPE}
      CHUNK_SIZE: ${CHUNK_SIZE}
      LOG_LEVEL: ${LOG_LEVEL}
      PYTHONUNBUFFERED: "1"
      PSK: ${PSK}
    volumes:
      - "./ipc:/ipc"
      - ".:/app"
      - "./shared:${BASE_DIR}"
      - "/:/host:ro"
    tty: true
    stdin_open: true
    restart: unless-stopped

  ${SVC_UI}:
    image: linkchat-ui
    depends_on: []
    environment:
      DISPLAY: ${DISPLAY}
      XAUTHORITY: /root/.Xauthority
      SDL_VIDEODRIVER: x11
      QT_X11_NO_MITSHM: "1"
      IPC_SOCKET: /ipc/linkchat-${ALIAS}.sock
      LIBGL_ALWAYS_SOFTWARE: "1"
      MESA_LOADER_DRIVER_OVERRIDE: llvmpipe
      PYTHONUNBUFFERED: "1"
      BASE_DIR: ${BASE_DIR}
      LOG_LEVEL: ${LOG_LEVEL}
      PSK: ${PSK}
    volumes:
      - "/tmp/.X11-unix:/tmp/.X11-unix:ro"
      - "${XAUTH_HOST}:/root/.Xauthority:ro"
      - "./ipc:/ipc:ro"
      - "./ui:/app/"
      - "./shared:${BASE_DIR}"
      - "/:/host:ro"
    tty: true
    stdin_open: true
    restart: unless-stopped
YAML

echo "[launcher] Override: $OVR_FILE"
docker compose --env-file "$ENVFILE" -f docker-compose.yml -f "$OVR_FILE" up -d ${SVC_BACK} ${SVC_UI}
docker compose ps
echo "[launcher] Listo. Este nodo corre como servicios: ${SVC_BACK} y ${SVC_UI}"
echo "[launcher] Conecta todas las laptops al hotspot del teléfono ANTES de ejecutar este script."
