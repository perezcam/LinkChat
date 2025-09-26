#!/bin/bash

# Detectar interfaz LAN (Ethernet) activa usando ifconfig
LAN_INTERFACE=$(ifconfig | grep -E 'en|eth' | awk '{print $1}')

# Detectar interfaz Wi-Fi activa usando iwconfig
WIFI_INTERFACE=$(iwconfig 2>&1 | grep -o '^[[:alnum:]]*')

# Comprobar si se encuentra una interfaz LAN
if [ -n "$LAN_INTERFACE" ]; then
  echo "Conexión LAN detectada en la interfaz: $LAN_INTERFACE"
  docker network connect $LAN_INTERFACE my_container

# Comprobar si se encuentra una interfaz Wi-Fi
elif [ -n "$WIFI_INTERFACE" ]; then
  echo "Conexión Wi-Fi detectada en la interfaz: $WIFI_INTERFACE"
  docker network connect $WIFI_INTERFACE my_container

else
  echo "No se encontró conexión LAN ni Wi-Fi. Usando red virtualizada predeterminada."
  # Si no hay LAN ni Wi-Fi, conecta el contenedor a la red Dockerizada por defecto
  docker network connect virtual_network my_container
fi