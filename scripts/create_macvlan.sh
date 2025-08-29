#!/usr/bin/env bash
# Create a macvlan network for containers to get DHCP from the upstream network.
set -euo pipefail
if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <network-name> <parent-iface>"
  exit 2
fi
NAME="$1"
PARENT="$2"

docker network create -d macvlan \
  --subnet="${SUBNET:-192.168.100.0/24}" \
  --gateway="${GATEWAY:-192.168.100.1}" \
  -o parent="$PARENT" \
  "$NAME"

echo "Created macvlan network '$NAME' using parent '$PARENT'"
