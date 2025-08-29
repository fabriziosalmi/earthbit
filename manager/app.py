import asyncio
import json
from aiohttp import web
import aiohttp

import os

REGISTRY = {}
PROXIES = []

ELECTION_INTERVAL = int(os.environ.get('ELECTION_INTERVAL', '10'))
ELECTION_K = int(os.environ.get('ELECTION_K', '1'))

async def register(request):
    data = await request.json()
    ip = request.remote
    REGISTRY[ip] = {"info": data, "last": asyncio.get_event_loop().time()}
    return web.json_response({"status": "ok", "ip": ip})

async def list_workers(request):
    return web.json_response(REGISTRY)


async def list_proxies(request):
    return web.json_response({"proxies": PROXIES})


RR_INDEX = 0

async def dispatch(request):
    global RR_INDEX
    data = await request.json()
    if not PROXIES:
        return web.json_response({'error': 'no proxies'}, status=503)
    # Round-robin select proxy
    proxy_ip = PROXIES[RR_INDEX % len(PROXIES)]
    RR_INDEX += 1
    # forward task to proxy (assume worker port 9999 and /task)
    url = f'http://{proxy_ip}:9999/task'
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(url, json=data, timeout=5) as resp:
                text = await resp.text()
                return web.json_response({'proxy': proxy_ip, 'status': resp.status, 'body': text})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def elect_proxies():
    global PROXIES
    while True:
        await asyncio.sleep(ELECTION_INTERVAL)
        # Simple election: pick k workers with newest 'last'
        items = sorted(REGISTRY.items(), key=lambda kv: kv[1].get('last', 0), reverse=True)
        PROXIES = [ip for ip, _ in items[:ELECTION_K]]
        print(f"Elected proxies: {PROXIES}")

async def start_background(app):
    app['election_task'] = asyncio.create_task(elect_proxies())

async def cleanup_background(app):
    app['election_task'].cancel()

def create_app():
    app = web.Application()
    app.add_routes([
        web.post('/register', register),
        web.get('/workers', list_workers),
        web.get('/proxies', list_proxies),
        web.post('/dispatch', dispatch),
    ])
    app.on_startup.append(start_background)
    app.on_cleanup.append(cleanup_background)
    return app

if __name__ == '__main__':
    web.run_app(create_app(), port=8888)
