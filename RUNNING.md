Run instructions

1. For single-host testing use host networking (already configured): services run with `network_mode: host` so they bind to host IP/ports.

2. Build and run:

   docker compose up --build

3. Verify endpoints (on the host):

   - Manager workers list: http://127.0.0.1:8888/workers
   - Manager proxies: http://127.0.0.1:8888/proxies
   - Dispatch a task (example):

     ```bash
     curl -s -X POST http://127.0.0.1:8888/dispatch -H 'Content-Type: application/json' -d '{"job":"hello"}' | jq
     ```

Notes: In host mode we set `USE_DHCLIENT=0` in compose so the start scripts skip calling dhclient. Workers will determine their IP by opening a UDP socket to the manager and registering that outbound address; in host mode this will typically be the host IP.
