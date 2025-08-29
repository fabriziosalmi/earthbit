import asyncio
import os
import socket
from aiohttp import web, ClientSession

MANAGER_HOST = os.environ.get('MANAGER_HOST', 'manager')
MANAGER_PORT = int(os.environ.get('MANAGER_PORT', '8888'))

async def handle(request):
    return web.json_response({'status': 'worker ok'})

async def task_handler(request):
    data = await request.json()
    # simple echo behavior to simulate doing work
    print('received task', data)
    return web.json_response({'status': 'done', 'echo': data})

def get_own_ip():
    # Determine outbound IP by opening a UDP socket to manager (doesn't send data)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((MANAGER_HOST, MANAGER_PORT))
        return s.getsockname()[0]
    except Exception:
        return '0.0.0.0'
    finally:
        s.close()

async def register_periodically(app):
    async with ClientSession() as sess:
        while True:
            await asyncio.sleep(5)
            ip = get_own_ip()
            try:
                url = f'http://{MANAGER_HOST}:{MANAGER_PORT}/register'
                data = {'ip': ip, 'role': 'worker', 'port': 9999}
                async with sess.post(url, json=data, timeout=2) as resp:
                    await resp.text()
            except Exception as e:
                print('register failed', e)

def create_app():
    app = web.Application()
    app.add_routes([web.get('/', handle), web.post('/task', task_handler)])
    app.on_startup.append(lambda app: asyncio.create_task(register_periodically(app)))
    return app

if __name__ == '__main__':
    web.run_app(create_app(), port=9999)
