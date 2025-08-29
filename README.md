# Sun & Moons — manager/workers Docker demo

This repository shows a minimal Docker setup for a manager and multiple workers that obtain DHCP-assigned IPs (via a macvlan-based network) and communicate over those IPs.

High level
- manager listens on port 8888
- workers listen on port 9999
- workers obtain a DHCP IP on the container interface and register to the manager using that IP
- manager keeps a registry and periodically elects a small subset of "proxy" workers (simple selection algorithm)

Notes / assumptions
- This setup uses Docker macvlan and requires a host network interface provided as PARENT_IFACE that is attached to a real L2 network where DHCP service is available.
- On many systems creating a macvlan network requires host privileges and network configuration knowledge. If you cannot use macvlan, you can adapt the compose file to use host networking for single-host testing (not covered here).

Files
- `docker-compose.yml` — brings up 1 manager + 2 workers (build from local folders)
- `scripts/create_macvlan.sh` — helper to create a macvlan network (customize PARENT_IFACE)
- `manager/` and `worker/` — service code, Dockerfile and start scripts

Quick start (example)
1. Edit `.env` or export env vars: PARENT_IFACE (e.g. eno1), SUBNET, GATEWAY.
2. Create the macvlan network (optional if you let compose create it):
   ```bash
   ./scripts/create_macvlan.sh lannet ${PARENT_IFACE}
   ```
3. Start with docker-compose:
   ```bash
   docker compose up --build
   ```

If macvlan is not available, run with `network_mode: host` in `docker-compose.yml` for quick single-host testing (each container will then share host IP).
