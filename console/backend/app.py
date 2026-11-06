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
import paramiko
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
        self.connecting = False
        self.connection_generation = 0
        self.recovery = None
        self.preparation = None

    def begin_connection(self, replace=False):
        with self.lock:
            if self.connecting or ((self.ssh or self.recovery) and not replace):
                raise HTTPException(409, '已有连接或正在连接；请先断开现有连接')
            self.connection_generation += 1
            generation = self.connection_generation
            self.connecting = True
            self.preparation = None
            old, token = self.ssh, self.token
            pending, self.recovery = self.recovery, None
            self.ssh, self.token, self.profile, self.maintenance = None, '', None, None
        if pending:
            pending['ssh'].close()
        return generation, old, token

    def accept_connection(self, generation, ssh, token, profile):
        with self.lock:
            if generation != self.connection_generation or not self.connecting:
                raise HTTPException(409, '连接已取消，请重新连接')
            self.ssh, self.token, self.profile = ssh, token, profile
            self.recovery = None

    def keep_for_recovery(self, generation, ssh, token, profile):
        with self.lock:
            if generation != self.connection_generation or not self.connecting:
                raise HTTPException(409, '连接已取消，请重新连接')
            self.recovery = {'ssh':ssh, 'token':token, 'profile':profile}

    def begin_recovery(self):
        with self.lock:
            if not self.recovery or self.connecting or self.ssh:
                raise HTTPException(409, '请先连接 SSH，且不要同时执行其他连接操作')
            self.connecting = True
            return self.connection_generation, self.recovery

    def recovery_available(self):
        with self.lock:
            return self.recovery is not None

    def set_preparation(self, generation, stage):
        with self.lock:
            if generation != self.connection_generation or not self.connecting:
                raise HTTPException(409, '连接已取消')
            self.preparation = stage

    def preparation_stage(self):
        with self.lock:
            return self.preparation

    def finish_connection(self, generation):
        with self.lock:
            if generation == self.connection_generation:
                self.connecting = False
                self.preparation = None

    def request(self, path, body=None):
        with self.lock:
            if not self.ssh:
                raise ValueError('Not connected')
            ssh, token = self.ssh, self.token
        return ssh.request('GET' if body is None else 'POST', path, b'' if body is None else json.dumps(body).encode(), token)

    def stop(self):
        try:
            self.request('/control', {'action': 'stop'})
        except Exception:
            pass

    def close(self):
        with self.lock:
            self.connection_generation += 1
            self.connecting = False
            self.preparation = None
            ssh, token = self.ssh, self.token
            pending, self.recovery = self.recovery, None
            self.ssh = None
            self.token = ''
            self.profile = None
            self.maintenance = None
        if pending:
            pending['ssh'].close()
        close_connection(ssh, token)


def close_connection(ssh, token):
    if ssh:
        try:
            ssh.request('POST', '/control', b'{"action": "stop"}', token)
        except Exception:
            pass
        finally:
            ssh.close()


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
    generation, old, old_token = session.begin_connection(replace=True)
    ssh = None
    try:
        await asyncio.to_thread(close_connection, old, old_token)
        ssh = await asyncio.to_thread(SSH, p, d.get('password') or None)
        token = d.get('adapter_token', '')
        state = json.loads(await asyncio.to_thread(ssh.request, 'GET', '/state', token=token))
        if state['kind'] != p['kind']:
            raise ValueError('Target kind mismatch; refusing control')
        session.accept_connection(generation, ssh, token, p)
        ssh = None
        managed_event(
            'SSH and target adapter connected; explicit control claim required')
        return {'connected': True, 'kind': state['kind']}
    except HTTPException:
        raise
    except Exception:
        managed_event('SSH or adapter connection rejected', 40)
        raise HTTPException(
            400, 'Connection failed: verify fingerprint, credentials and adapter configuration')
    finally:
        if ssh:
            await asyncio.to_thread(ssh.close)
        session.finish_connection(generation)


@app.post('/api/v1/connect-robot')
async def connect_robot(request: Request):
    data = await request.json()
    password = data.get('password')
    if not isinstance(password, str) or not password:
        raise HTTPException(400, '请输入 SSH 密码')
    robots = [p for p in profiles().values() if p.get('kind') == 'robot']
    if len(robots) != 1:
        raise HTTPException(400, '需要一个已保存且已验证指纹的实车配置')
    profile = valid_profile(robots[0])
    generation, _, _ = session.begin_connection()
    session.set_preparation(generation, 'ssh')
    ssh = None
    try:
        try:
            ssh = await asyncio.to_thread(SSH, profile, password)
        except Exception:
            raise HTTPException(400, 'SSH 连接失败：请检查热点、密码和已保存的主机指纹')
        try:
            token = await asyncio.to_thread(ssh.adapter_token)
        except Exception:
            raise HTTPException(503, '无法读取车端适配器令牌，请检查车端配置')
        try:
            state = json.loads(await asyncio.to_thread(ssh.request, 'GET', '/state', token=token))
            if state.get('kind') != 'robot':
                raise ValueError('Unexpected target kind')
        except paramiko.ChannelException as exc:
            if exc.code != 2:
                raise HTTPException(503, 'SSH 已连接，但 SSH 服务器拒绝适配器隧道；请检查转发权限')
            session.keep_for_recovery(generation, ssh, token, profile)
            managed_event('Robot adapter port unavailable; authenticated SSH retained for fixed recovery', 30)
            try:
                result = await asyncio.to_thread(ssh.prepare_robot, password,
                    lambda stage: session.set_preparation(generation, stage))
                if result.get('status') != 'ready':
                    raise HTTPException(503, preparation_error(result))
                token = await asyncio.to_thread(ssh.adapter_token)
                state = json.loads(await asyncio.to_thread(ssh.request, 'GET', '/state', token=token))
                if state.get('kind') != 'robot':
                    raise HTTPException(503, '准备后的适配器目标身份不符')
            except HTTPException:
                ssh = None
                raise
            except Exception:
                ssh = None
                raise HTTPException(503, '自动停车准备未完成，SSH 已保留，可读取诊断后重试')
        except Exception:
            raise HTTPException(503, 'SSH 已连接，但车端适配器不可用或认证失败；请检查车端服务')
        session.accept_connection(generation, ssh, token, profile)
        ssh = None
        managed_event('SSH and target adapter connected; explicit control claim required')
        return {'connected': True, 'kind': 'robot'}
    finally:
        if ssh:
            await asyncio.to_thread(ssh.close)
        session.finish_connection(generation)


def preparation_error(result):
    reasons={'runtime_preflight_failed':'原运行配置核对未通过','unowned_ros_processes':'检测到未登记的ROS进程，未启动服务',
             'clock_drift_live_stack':'现有运行进程存在时钟偏差，未修改系统时间','clock_auth_required':'校时认证失败，请断开并重新输入SSH密码连接',
             'not_parked':'尚未确认停车保持','vehicle_moving':'检测到车辆运动或非零输出','parked_evidence_unavailable':'未收到新鲜停车状态',
             'navigation_services_unavailable':'导航服务尚未就绪','adapter_still_running':'原适配器仍在运行，未重启',
             'component_exited':'原服务启动后退出','adapter_start_timeout':'适配器启动未完成','runtime_manifest_missing':'原运行索引缺失'}
    reason=result.get('reason','unknown')
    detail=reasons.get(reason,reason)
    if result.get('error'):detail+='：'+str(result['error'])[:256]
    if result.get('missing_services'):detail+='；缺失服务：'+', '.join(result['missing_services'])
    return 'SSH 已连接，适配器端口未就绪；自动停车准备未完成：'+detail


@app.post('/api/v1/robot/prepare')
async def prepare_robot(request: Request):
    body=await request.json()
    if body != {'confirm_parked':True} or body.get('confirm_parked') is not True:
        raise HTTPException(400, '此接口只允许固定停车准备')
    generation,pending=session.begin_recovery()
    try:
        ssh=pending['ssh']
        result=await asyncio.to_thread(ssh.prepare_robot,None,lambda stage:session.set_preparation(generation,stage))
        if result.get('status')!='ready':raise HTTPException(409,preparation_error(result))
        token=await asyncio.to_thread(ssh.adapter_token)
        state=json.loads(await asyncio.to_thread(ssh.request,'GET','/state',token=token))
        if state.get('kind')!='robot':raise HTTPException(503,'适配器目标身份不符')
        session.accept_connection(generation,ssh,token,pending['profile'])
        managed_event('Robot parked preparation complete; adapter connected; explicit exploration request required')
        return {'connected':True,'kind':'robot','preparation':result}
    except HTTPException:raise
    except Exception:raise HTTPException(503,'停车准备未完成，可读取诊断；不会自动重试或启动探索')
    finally:session.finish_connection(generation)


@app.get('/api/v1/adapter/diagnostics')
async def adapter_diagnostics():
    generation, pending = session.begin_recovery()
    try:
        return await asyncio.to_thread(pending['ssh'].adapter_operation, 'inspect')
    except Exception:
        raise HTTPException(503, '无法读取适配器诊断，请检查 SSH 连接')
    finally:
        session.finish_connection(generation)


@app.post('/api/v1/adapter/restore')
async def restore_adapter(request: Request):
    body = await request.json()
    if body != {'confirm_parked': True} or body.get('confirm_parked') is not True:
        raise HTTPException(400, '请确认小车已停车；此接口只允许恢复原适配器')
    generation, pending = session.begin_recovery()
    try:
        ssh = pending['ssh']
        result = await asyncio.to_thread(ssh.adapter_operation, 'restore')
        if result.get('status') != 'ready':
            missing = result.get('missing_services', [])
            reason = result.get('reason', 'unknown')
            raise HTTPException(409, '未恢复适配器：'+reason+('；缺失服务：'+', '.join(missing) if missing else ''))
        token = await asyncio.to_thread(ssh.adapter_token)
        state = json.loads(await asyncio.to_thread(ssh.request, 'GET', '/state', token=token))
        if state.get('kind') != 'robot':
            raise HTTPException(503, '适配器目标身份不符，拒绝建立控制连接')
        session.accept_connection(generation, ssh, token, pending['profile'])
        managed_event('Original adapter available; SSH and target adapter connected; motion remains held')
        return {'connected': True, 'kind': 'robot', 'recovery':result}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, '适配器恢复或连接检查失败，可读取诊断查看原因')
    finally:
        session.finish_connection(generation)


@app.post('/api/v1/task')
async def task_command(request: Request):
    body = await request.json()
    if body.get('action') not in ('explore', 'remote', 'stop', 'reset_map'):
        raise ValueError('未知任务操作')
    if session.maintenance and body['action'] in ('explore', 'reset_map'):
        raise ValueError('请先关闭维护终端，再执行自主探索或地图重置')
    return json.loads(await asyncio.to_thread(session.request, '/task', {'action': body['action']}))


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
                await ws.send_json({'type': 'offline', 'data': {'reason': 'Target unavailable; motion lease will expire', 'logs': list(managed_logs), 'adapter_recovery': session.recovery_available(), 'preparation':session.preparation_stage()}})
            await asyncio.sleep(.15)
    task = asyncio.create_task(stream())
    try:
        while True:
            d = await ws.receive_json()
            if d.get('type') == 'control':
                try:
                    body = d.get('data', {})
                    body['owner'] = owner
                    if body.get('action') not in ('claim', 'command', 'stop', 'release', 'heartbeat', 'gear'):
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
