#!/usr/bin/env bash
set -euo pipefail
if [ "${USE_DHCLIENT:-1}" != "0" ] && command -v dhclient >/dev/null 2>&1; then
  dhclient -v eth0 || true
fi
exec python -u app.py
