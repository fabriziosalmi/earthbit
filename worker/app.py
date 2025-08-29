import asyncio
import os
import socket
import logging
import time
from aiohttp import web, ClientSession, ClientTimeout
from prometheus_client import CollectorRegistry, generate_latest, Gauge, Histogram, Counter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('worker')

MANAGER_HOST = os.environ.get('MANAGER_HOST', 'manager')
MANAGER_PORT = int(os.environ.get('MANAGER_PORT', '8888'))
REGISTER_INTERVAL = float(os.environ.get('REGISTER_INTERVAL', '5'))
REGISTER_RETRIES = int(os.environ.get('REGISTER_RETRIES', '5'))
REGISTER_BACKOFF_BASE = float(os.environ.get('REGISTER_BACKOFF_BASE', '0.5'))
WORKER_PORT = int(os.environ.get('WORKER_PORT', '9999'))


async def handle(request):
    return web.json_response({'status': 'worker ok'})


async def task_handler(request):
    data = await request.json()
    logger.info('received task %s', data)
    # simulate work here; keep it idempotent and quick for WAN scenarios
    # Support a simple sample task format: { "type": "http_call", "url": "http://...", "method": "POST", "body": {...} }
    try:
        ttype = data.get('type')
        if ttype == 'http_call':
            url = data.get('url')
            method = data.get('method', 'POST').upper()
            body = data.get('body', {})
            timeout = ClientTimeout(total=10)
            async with ClientSession() as sess:
                async with sess.request(method, url, json=body, timeout=timeout) as resp:
                    text = await resp.text()
                    return web.json_response({'status': 'done', 'echo': data, 'target_status': resp.status, 'target_body': text})
        else:
            return web.json_response({'status': 'done', 'echo': data})
    except Exception as e:
        logger.exception('task execution failed')
        return web.json_response({'status': 'error', 'error': str(e)}, status=500)


def get_own_ip():
    # Determine outbound IP by connecting a UDP socket to manager. This doesn't send packets.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((MANAGER_HOST, MANAGER_PORT))
        return s.getsockname()[0]
    except Exception:
        return '0.0.0.0'
    finally:
        s.close()


async def register_once(session: ClientSession, payload: dict):
    url = f'http://{MANAGER_HOST}:{MANAGER_PORT}/register'
    timeout = ClientTimeout(total=5)
    last_exc = None
    for attempt in range(REGISTER_RETRIES):
        try:
            async with session.post(url, json=payload, timeout=timeout) as resp:
                text = await resp.text()
                if 200 <= resp.status < 300:
                    logger.info('registered with manager: %s', text)
                    return True
                else:
                    last_exc = f'status {resp.status}: {text}'
        except Exception as e:
            last_exc = e
        backoff = REGISTER_BACKOFF_BASE * (2 ** attempt)
        await asyncio.sleep(backoff)
    logger.warning('failed to register after retries: %s', last_exc)
    return False


async def register_periodically(app):
    session = app['session']
    while True:
        ip = get_own_ip()
        payload = {'ip': ip, 'role': 'worker', 'port': WORKER_PORT}
        try:
            ok = await register_once(session, payload)
            if not ok:
                # wait longer on persistent failures to avoid storming the manager
                await asyncio.sleep(max(REGISTER_INTERVAL, 5))
            else:
                await asyncio.sleep(REGISTER_INTERVAL)
        except Exception as e:
            logger.exception('unexpected error during register: %s', e)
            await asyncio.sleep(REGISTER_INTERVAL)


async def start_background(app):
    app['session'] = ClientSession()
    app['register_task'] = asyncio.create_task(register_periodically(app))


# Prometheus metrics
REGISTRY_METRICS = CollectorRegistry()
PING_HIST = Histogram('worker_ping_latency_seconds', 'Latency of /ping handler', registry=REGISTRY_METRICS)
TASKS_HANDLED = Counter('worker_tasks_handled_total', 'Total tasks handled by worker', registry=REGISTRY_METRICS)


async def cleanup_background(app):
    app['register_task'].cancel()
    await app['session'].close()


def create_app():
    app = web.Application()
    app.add_routes([
        web.get('/', handle),
    web.post('/task', task_handler),
    web.get('/health', lambda request: web.json_response({'status': 'ok'})),
    web.get('/ping', lambda request: web.json_response({'status': 'pong'})),
    web.get('/metrics', lambda request: web.Response(body=generate_latest(REGISTRY_METRICS), content_type='text/plain; version=0.0.4')),
    ])
    app.on_startup.append(start_background)
    app.on_cleanup.append(cleanup_background)
    return app


if __name__ == '__main__':
    web.run_app(create_app(), port=WORKER_PORT)
