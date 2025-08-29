#!/usr/bin/env bash
set -euo pipefail
# Request DHCP lease on eth0 (needs NET_ADMIN capability). Skip if USE_DHCLIENT=0
if [ "${USE_DHCLIENT:-1}" != "0" ] && command -v dhclient >/dev/null 2>&1; then
  dhclient -v eth0 || true
fi
exec python -u app.py
