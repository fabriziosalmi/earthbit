import asyncio
import json
import os
import random
from aiohttp import web, ClientSession, ClientTimeout

REGISTRY = {}
PROXIES = []
PROXY_FAILS = {}  # ip -> (fails, last_fail_ts)

# Configurable via env
ELECTION_INTERVAL = float(os.environ.get('ELECTION_INTERVAL', '10'))
ELECTION_K = int(os.environ.get('ELECTION_K', '1'))
WORKER_TTL = float(os.environ.get('WORKER_TTL', '30'))
CLEANUP_INTERVAL = float(os.environ.get('CLEANUP_INTERVAL', '10'))
PROXY_BLACKLIST_TTL = float(os.environ.get('PROXY_BLACKLIST_TTL', '60'))
PROXY_MAX_FAILS = int(os.environ.get('PROXY_MAX_FAILS', '3'))
REQUEST_TIMEOUT = float(os.environ.get('REQUEST_TIMEOUT', '5'))
DISPATCH_RETRIES = int(os.environ.get('DISPATCH_RETRIES', '3'))
DISPATCH_BACKOFF_BASE = float(os.environ.get('DISPATCH_BACKOFF_BASE', '0.5'))

_RR_INDEX = 0

async def register(request):
    data = await request.json()
    ip = request.remote
    now = asyncio.get_event_loop().time()
    REGISTRY[ip] = {"info": data, "last": now}
    # return the manager's view so worker can verify
    return web.json_response({"status": "ok", "ip": ip, "now": now})

async def list_workers(request):
    return web.json_response(REGISTRY)


async def list_proxies(request):
    return web.json_response({"proxies": PROXIES})


def _get_available_proxies():
    now = asyncio.get_event_loop().time()
    available = []
    for p in PROXIES:
        fails, last_fail = PROXY_FAILS.get(p, (0, 0))
        if fails >= PROXY_MAX_FAILS and (now - last_fail) < PROXY_BLACKLIST_TTL:
            # skip blacklisted
            continue
        available.append(p)
    return available


async def dispatch(request):
    """Dispatch task to a proxy with retries and backoff.

    Request body is forwarded to worker /task. Tries up to DISPATCH_RETRIES
    distinct proxies (if available) and returns first successful response.
    """
    global _RR_INDEX
    data = await request.json()
    if not PROXIES:
        return web.json_response({'error': 'no proxies'}, status=503)

    available = _get_available_proxies()
    if not available:
        return web.json_response({'error': 'no available proxies'}, status=503)

    # rotate starting index for fairness
    start = _RR_INDEX
    _RR_INDEX = (_RR_INDEX + 1) % max(1, len(PROXIES))

    session: ClientSession = request.app['session']
    tried = set()
    last_error = None
    for attempt in range(DISPATCH_RETRIES):
        # pick next candidate skipping tried ones
        candidates = [p for p in available if p not in tried]
        if not candidates:
            break
        proxy_ip = candidates[(start + attempt) % len(candidates)]
        tried.add(proxy_ip)
        url = f'http://{proxy_ip}:{request.app.get("worker_port", 9999)}/task'
        timeout = ClientTimeout(total=REQUEST_TIMEOUT)
        backoff = DISPATCH_BACKOFF_BASE * (2 ** attempt)
        # jitter
        backoff = backoff * (0.8 + random.random() * 0.4)
        try:
            async with session.post(url, json=data, timeout=timeout) as resp:
                text = await resp.text()
                if 200 <= resp.status < 300:
                    # success: clear failure record
                    PROXY_FAILS.pop(proxy_ip, None)
                    return web.json_response({'proxy': proxy_ip, 'status': resp.status, 'body': text})
                else:
                    last_error = f'status {resp.status}'
                    # treat as failure and record
                    fails, _ = PROXY_FAILS.get(proxy_ip, (0, 0))
                    PROXY_FAILS[proxy_ip] = (fails + 1, asyncio.get_event_loop().time())
        except Exception as e:
            last_error = str(e)
            fails, _ = PROXY_FAILS.get(proxy_ip, (0, 0))
            PROXY_FAILS[proxy_ip] = (fails + 1, asyncio.get_event_loop().time())
        # wait before next attempt
        await asyncio.sleep(backoff)

    return web.json_response({'error': 'dispatch failed', 'detail': last_error}, status=502)


async def elect_proxies():
    global PROXIES
    while True:
        await asyncio.sleep(ELECTION_INTERVAL)
        # Simple election: pick k workers with newest 'last'
        items = sorted(REGISTRY.items(), key=lambda kv: kv[1].get('last', 0), reverse=True)
        PROXIES = [ip for ip, _ in items[:ELECTION_K]]
        print(f"Elected proxies: {PROXIES}")


async def cleanup_stale_workers():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        now = asyncio.get_event_loop().time()
        stale = [ip for ip, v in REGISTRY.items() if (now - v.get('last', 0)) > WORKER_TTL]
        for ip in stale:
            REGISTRY.pop(ip, None)
            print(f"Removed stale worker {ip}")


async def start_background(app):
    app['session'] = ClientSession()
    app['election_task'] = asyncio.create_task(elect_proxies())
    app['cleanup_task'] = asyncio.create_task(cleanup_stale_workers())


async def cleanup_background(app):
    app['election_task'].cancel()
    app['cleanup_task'].cancel()
    await app['session'].close()


def create_app():
    app = web.Application()
    app.add_routes([
        web.post('/register', register),
        web.get('/workers', list_workers),
        web.get('/proxies', list_proxies),
        web.post('/dispatch', dispatch),
        web.get('/health', lambda request: web.json_response({'status': 'ok'})),
    ])
    # set default worker port, can be overridden by env
    try:
        app['worker_port'] = int(os.environ.get('WORKER_PORT', '9999'))
    except Exception:
        app['worker_port'] = 9999
    app.on_startup.append(start_background)
    app.on_cleanup.append(cleanup_background)
    return app


if __name__ == '__main__':
    web.run_app(create_app(), port=int(os.environ.get('MANAGER_PORT', '8888')))
