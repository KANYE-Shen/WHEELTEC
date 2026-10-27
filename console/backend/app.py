"""Local-only gateway. Run from repository: python -m console.backend.app."""
import asyncio
from collections import deque
import json
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from .policy import check_origin
from .transport import SSH, probe

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT/'frontend/dist'
STATE = Path(os.environ.get('WHEELTEC_CONSOLE_STATE',
             str(Path.home()/'.wheeltec-console')))


@asynccontextmanager
async def lifespan(app):
    try:
        yield
    finally:
        await asyncio.to_thread(session.close)

app = FastAPI(docs_url=None, redoc_url=None, lifespan=lifespan)
secret = secrets.token_urlsafe(32)
managed_logs = deque(maxlen=100)


def managed_event(message, level=20):
    # Fixed event strings only: never pass SSH commands, credentials or request bodies.
    managed_logs.append({'id': -time.time_ns(), 'stamp': time.time(), 'level': level,
                         'name': 'console.gateway', 'message': message})


managed_event('Local gateway started; motion remains held')


class Session:
    def __init__(self):
        self.ssh = None
        self.token = ''
        self.profile = None
        self.lock = threading.Lock()
        self.maintenance = None

    def request(self, path, body=None):
        with self.lock:
            if not self.ssh:
                raise ValueError('Not connected')
            return self.ssh.request('GET' if body is None else 'POST', path, b'' if body is None else json.dumps(body).encode(), self.token)

    def stop(self):
        try:
            self.request('/control', {'action': 'stop'})
        except Exception:
            pass

    def close(self):
        self.stop()
        with self.lock:
            if self.ssh:
                self.ssh.close()
            self.ssh = None
            self.token = ''
            self.profile = None
            self.maintenance = None


session = Session()


def profiles():
    try:
        return json.loads((STATE/'profiles.json').read_text())
    except FileNotFoundError:
        return {}


def save_profiles(data):
    STATE.mkdir(parents=True, exist_ok=True)
    p = STATE/'profiles.json'
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.chmod(0o600)
    tmp.replace(p)


def valid_profile(data):
    allowed = {'name', 'kind', 'host', 'port', 'username',
               'fingerprint', 'key_file', 'adapter_port', 'desktop_port'}
    p = {k: v for k, v in data.items() if k in allowed}
    if p.get('kind') not in ('robot', 'simulation'):
        raise ValueError('Explicit robot/simulation kind required')
    for key in ('name', 'host', 'username', 'fingerprint'):
        if not isinstance(p.get(key), str) or not p[key] or len(p[key]) > 256:
            raise ValueError('Invalid '+key)
    if not p['fingerprint'].startswith('SHA256:'):
        raise ValueError('Verify the host fingerprint first')
    for key, default in [('port', 22), ('adapter_port', 8767), ('desktop_port', 6080)]:
        p[key] = int(p.get(key, default))
        if not 1 <= p[key] <= 65535:
            raise ValueError('Invalid port')
    return p


@app.middleware('http')
async def secure(request: Request, call_next):
    host = request.headers.get('host', '')
    if host.split(':')[0] not in ('127.0.0.1', 'localhost'):
        return Response(status_code=403)
    if request.url.path.startswith('/api/'):
        if not secrets.compare_digest(request.cookies.get('wheeltec_session', ''), secret):
            return Response(status_code=401)
        if request.method != 'GET' and not check_origin(request.headers.get('origin'), host):
            return Response(status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@app.exception_handler(ValueError)
async def value_error(request, exc): return JSONResponse(
    {'detail': str(exc)}, status_code=400)


@app.get('/bootstrap')
def bootstrap():
    response = JSONResponse({'version': 1})
    response.set_cookie('wheeltec_session', secret,
                        httponly=True, samesite='strict')
    return response


@app.get('/api/v1/logs')
def process_logs(): return list(managed_logs)


@app.get('/api/v1/profiles')
def get_profiles(): return profiles()


@app.post('/api/v1/profiles')
async def put_profile(request: Request):
    p = valid_profile(await request.json())
    data = profiles()
    data[p['name']] = p
    save_profiles(data)
    return p


@app.post('/api/v1/probe')
async def probe_key(request: Request):
    d = await request.json()
    try:
        return {'fingerprint': await asyncio.to_thread(probe, d['host'], int(d.get('port', 22)))}
    except Exception:
        raise HTTPException(
            400, 'SSH host-key probe failed; check address and port')


@app.post('/api/v1/connect')
async def connect(request: Request):
    d = await request.json()
    p = valid_profile(d['profile'])
    await asyncio.to_thread(session.close)
    try:
        ssh = await asyncio.to_thread(SSH, p, d.get('password') or None)
        session.ssh = ssh
        session.token = d.get('adapter_token', '')
        session.profile = p
        state = json.loads(await asyncio.to_thread(session.request, '/state'))
        if state['kind'] != p['kind']:
            raise ValueError('Target kind mismatch; refusing control')
        managed_event(
            'SSH and target adapter connected; explicit control claim required')
        return {'connected': True, 'kind': state['kind']}
    except Exception:
        await asyncio.to_thread(session.close)
        managed_event('SSH or adapter connection rejected', 40)
        raise HTTPException(
            400, 'Connection failed: verify fingerprint, credentials and adapter configuration')


@app.post('/api/v1/disconnect')
async def disconnect():
    await asyncio.to_thread(session.close)
    managed_event('Connection closed; target motion lease released')
    return {'connected': False}


@app.get('/api/v1/camera')
async def camera():
    try:
        return Response(await asyncio.to_thread(session.request, '/camera'), media_type='image/jpeg')
    except Exception:
        return Response(status_code=503)


async def ws_auth(ws, subprotocol=None):
    if not check_origin(ws.headers.get('origin'), ws.headers.get('host', '')) or not secrets.compare_digest(ws.cookies.get('wheeltec_session', ''), secret):
        await ws.close(code=1008)
        return False
    await ws.accept(subprotocol=subprotocol)
    return True


@app.websocket('/api/v1/events')
async def events(ws: WebSocket):
    if not await ws_auth(ws):
        return
    owner = secrets.token_urlsafe(24)

    async def stream():
        while True:
            try:
                data = json.loads(await asyncio.to_thread(session.request, '/state'))
                data['logs'] = data.get('logs', []) + list(managed_logs)
                data['connected'] = True
                data['maintenance'] = session.maintenance is not None
                data['connection'] = {k: session.profile[k] for k in (
                    'name', 'host', 'username', 'kind')} if session.profile else None
                data['control']['mine'] = data['control'].get('owner') == owner
                data['control'].pop('owner', None)
                await ws.send_json({'type': 'state', 'data': data})
            except Exception:
                await ws.send_json({'type': 'offline', 'data': {'reason': 'Target unavailable; motion lease will expire', 'logs': list(managed_logs)}})
            await asyncio.sleep(.15)
    task = asyncio.create_task(stream())
    try:
        while True:
            d = await ws.receive_json()
            if d.get('type') == 'control':
                try:
                    body = d.get('data', {})
                    body['owner'] = owner
                    if body.get('action') not in ('claim', 'command', 'stop', 'release'):
                        raise ValueError('Unknown action')
                    if session.maintenance and body['action'] not in ('stop', 'release'):
                        raise ValueError('Maintenance terminal active')
                    result = json.loads(await asyncio.to_thread(session.request, '/control', body))
                    await ws.send_json({'type': 'ack', 'data': result})
                except Exception as exc:
                    await ws.send_json({'type': 'error', 'data': {'reason': str(exc) if isinstance(exc, ValueError) else 'Control request failed'}})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        task.cancel()
        try:
            await asyncio.to_thread(session.request, '/control', {'action': 'release', 'owner': owner})
        except Exception:
            pass


@app.websocket('/api/v1/terminal')
async def terminal(ws: WebSocket):
    if not await ws_auth(ws):
        return
    if not session.ssh or session.maintenance:
        await ws.close(code=1008)
        return
    marker = secrets.token_hex(8)
    session.maintenance = marker
    channel = None
    try:
        # A read-only robot adapter cannot acknowledge a final driver stop.
        before = json.loads(await asyncio.to_thread(session.request, '/state'))
        robot = before['kind'] == 'robot'
        if robot and not before['control']['enabled']:
            raise ValueError('Robot is read-only; verified safety stop service required before maintenance PTY')
        revision = before['control'].get('watchdog_revision', 0)
        await asyncio.to_thread(session.request, '/control', {'action': 'stop'})
        if robot:
            deadline = time.monotonic()+1.5
            while True:
                state = json.loads(await asyncio.to_thread(session.request, '/state'))['control']
                if (state.get('watchdog_fresh') and state.get('watchdog_revision', 0) > revision
                        and state.get('watchdog', {}).get('armed') is False
                        and state.get('reason') not in ('driver_output_not_exclusive', 'watchdog_unavailable')):
                    break
                if time.monotonic() >= deadline:
                    raise ValueError('Final watchdog stop acknowledgment missing; maintenance PTY remains closed')
                await asyncio.sleep(.05)
        channel = await asyncio.to_thread(session.ssh.terminal)
        managed_event('Maintenance PTY opened after acknowledged stop')
        channel.settimeout(.1)

        async def read():
            while not channel.closed:
                if channel.recv_ready():
                    data = channel.recv(32768)
                    if not data:
                        break
                    await ws.send_bytes(data)
                else:
                    await asyncio.sleep(.02)
            await ws.close()
        reader = asyncio.create_task(read())
        try:
            while True:
                message = await ws.receive_json()
                if message.get('type') == 'input':
                    await asyncio.to_thread(channel.sendall, message['data'][:32768])
                elif message.get('type') == 'resize':
                    channel.resize_pty(width=max(20, min(300, int(message['cols']))), height=max(
                        5, min(120, int(message['rows']))))
        finally:
            reader.cancel()
    except Exception as exc:
        try:
            await ws.send_text('\r\n[Maintenance refused: '+(str(exc) if isinstance(exc, ValueError) else 'verify SSH and final safety state')+']\r\n')
            await ws.close(code=1011)
        except RuntimeError:
            pass
    finally:
        if channel:
            channel.close()
            managed_event('Maintenance PTY closed; motion remains held')
        if session.maintenance == marker:
            session.maintenance = None


@app.api_route('/api/v1/desktop/{path:path}', methods=['GET'])
async def desktop(path: str):
    if not session.ssh or not session.profile or session.profile['kind'] != 'simulation':
        raise HTTPException(403, 'Simulation desktop only')
    if '..' in path or '?' in path or '\r' in path or '\n' in path:
        raise HTTPException(400)
    try:
        # Desktop has a separate loopback port; keep the SSH channel pinned there.
        def fetch():
            import http.client
            import mimetypes

            class TunnelConnection(http.client.HTTPConnection):
                def close(self): pass
            c = TunnelConnection('127.0.0.1', timeout=5)
            channel = session.ssh.channel(session.ssh.desktop_port)
            c.sock = channel
            try:
                c.request('GET', '/'+path)
                r = c.getresponse()
                return r.status, r.read(8*1024*1024), r.getheader('Content-Type', mimetypes.guess_type(path)[0] or 'application/octet-stream')
            finally:
                channel.close()
        status, data, mime = await asyncio.to_thread(fetch)
        return Response(data, status_code=status, media_type=mime)
    except Exception:
        raise HTTPException(
            503, 'Start the optional loopback noVNC desktop on the simulation host')


@app.websocket('/api/v1/desktop/websockify')
async def desktop_ws(ws: WebSocket):
    if not await ws_auth(ws, subprotocol='binary'):
        return
    if not session.ssh or session.profile['kind'] != 'simulation':
        await ws.close(code=1008)
        return
    import websockets
    # A short-lived TCP tunnel is unnecessary: websocket-client uses a preopened SSH socket.
    import websocket as websocket_client
    remote = None
    try:
        channel = session.ssh.channel(session.ssh.desktop_port)
        remote = await asyncio.to_thread(websocket_client.create_connection, 'ws://127.0.0.1:'+str(session.ssh.desktop_port)+'/websockify', socket=channel, timeout=2, subprotocols=['binary'])

        async def incoming():
            while True:
                try:
                    data = await asyncio.to_thread(remote.recv)
                except (TimeoutError, websocket_client.WebSocketTimeoutException):
                    continue
                if not data:
                    break
                await ws.send_bytes(data if isinstance(data, bytes) else data.encode())
        task = asyncio.create_task(incoming())
        try:
            while True:
                await asyncio.to_thread(remote.send_binary, await ws.receive_bytes())
        finally:
            task.cancel()
    except Exception:
        pass
    finally:
        if remote:
            remote.close()


@app.get('/')
def index(): return FileResponse(DIST/'index.html')


if (DIST/'assets').exists():
    app.mount('/assets', StaticFiles(directory=DIST/'assets'))


def main():
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8766,
                log_level='warning', access_log=False)


if __name__ == '__main__':
    main()
