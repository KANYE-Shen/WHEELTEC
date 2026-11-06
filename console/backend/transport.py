"""SSH with explicit SHA256 pinning. Never auto-accept a host key."""
import socket
import threading
import time
from pathlib import Path
import paramiko
from .policy import fingerprint


class PinnedKey(paramiko.MissingHostKeyPolicy):
    def __init__(self, pin): self.pin = pin

    def missing_host_key(self, client, hostname, key):
        if fingerprint(key.asbytes()) != self.pin:
            raise paramiko.SSHException('Host key fingerprint mismatch')


class SSH:
    def __init__(self, config, password=None):
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(
            PinnedKey(config['fingerprint']))
        try:
            self.client.connect(config['host'], port=config.get('port', 22), username=config['username'], password=password,
                                key_filename=config.get('key_file') or None, timeout=8, auth_timeout=8, banner_timeout=8, allow_agent=True, look_for_keys=True)
            if fingerprint(self.client.get_transport().get_remote_server_key().asbytes()) != config['fingerprint']:
                raise paramiko.SSHException('Host key fingerprint mismatch')
            self.client.get_transport().set_keepalive(5)
        except Exception:
            self.client.close()
            raise
        self.port = int(config.get('adapter_port', 8767))
        self.desktop_port = int(config.get('desktop_port', 6080))

    def channel(self, port=None):
        channel = self.client.get_transport().open_channel(
            'direct-tcpip', ('127.0.0.1', port or self.port), ('127.0.0.1', 0), timeout=5)
        channel.settimeout(4)
        return channel

    def request(self, method, path, body=b'', token=''):
        import http.client
        # HTTPConnection closes a Connection: close socket before its body is read.
        # Paramiko makefile() does not keep a closed channel alive like socket.makefile().

        class TunnelConnection(http.client.HTTPConnection):
            def close(self): pass
        conn = TunnelConnection('127.0.0.1', timeout=4)
        channel = self.channel()
        conn.sock = channel
        try:
            conn.request(method, path, body, {
                         'Authorization': 'Bearer '+token, 'Content-Type': 'application/json', 'Connection': 'close'})
            response = conn.getresponse()
            data = response.read(16*1024*1024)
            if response.status != 200:
                import json
                try:
                    detail = json.loads(data).get('detail')
                except (ValueError, AttributeError):
                    detail = None
                raise ValueError(detail[:512] if isinstance(detail, str) else
                                 'Target rejected request: '+str(response.status))
            return data
        finally:
            channel.close()

    def terminal(self):
        return self.client.invoke_shell(term='xterm-256color', width=100, height=30)

    def adapter_token(self):
        # Relative to the authenticated SSH account's SFTP home; never invoke a shell.
        sftp = self.client.open_sftp()
        try:
            with sftp.open('.wheeltec-console/adapter.token', 'r') as source:
                raw = source.read(1025)
            if not raw or len(raw) > 1024:
                raise ValueError('Invalid adapter token')
            token = raw.decode('ascii').strip()
            if not token or any(c.isspace() for c in token):
                raise ValueError('Invalid adapter token')
            return token
        finally:
            sftp.close()

    def adapter_operation(self, operation):
        # Fixed code from this installation, never caller-supplied source/commands.
        if operation not in ('inspect', 'restore', 'plan', 'prepare'):
            raise ValueError('Unsupported fixed adapter operation')
        if operation in ('restore', 'prepare') and self.port != 8767:
            raise ValueError('Fixed restore supports only the original adapter port')
        import json
        source = Path(__file__).with_name('recovery_script.py').read_text(encoding='utf-8')
        source += '\nmain('+repr(operation)+')\n'
        command = 'python3 -'
        if operation != 'inspect':
            command = ('bash --noprofile --norc -c \'source /opt/ros/humble/setup.bash && '
                       'source "$HOME/wheeltec_ros2/install/setup.bash" && exec python3 -\'')
        stdin, stdout, stderr = self.client.exec_command(command, timeout=90 if operation=='prepare' else 30)
        stdin.write(source); stdin.flush(); stdin.channel.shutdown_write()
        data = stdout.read(128*1024)
        # Do not echo stderr: diagnostics may contain environment details.
        stderr.read(8192)
        if stdout.channel.recv_exit_status() != 0:
            raise ValueError('Fixed adapter operation failed')
        return json.loads(data)

    def prepare_robot(self, password=None, progress=None):
        def stage(name):
            if progress:progress(name)
        stage('checking')
        plan=self.adapter_operation('plan')
        if plan.get('status')!='planned':return plan
        corrected=False
        if abs(time.time()-float(plan['wall_time']))>2:
            if not plan.get('clock_reset_allowed'):
                return {'status':'blocked','reason':'clock_drift_live_stack'}
            stage('clock')
            # Password stays on encrypted stdin, never in a command or file.
            command=('sudo -S -p "" ' if password is not None else 'sudo -n ')
            command+='/usr/bin/date -u -s @'+format(time.time(),'.6f')
            stdin,stdout,stderr=self.client.exec_command(command,timeout=10)
            if password is not None:stdin.write(password+'\n');stdin.flush()
            stdin.channel.shutdown_write()
            stdout.read(1024);stderr.read(2048)
            if stdout.channel.recv_exit_status()!=0:
                return {'status':'blocked','reason':'clock_auth_required'}
            corrected=True
        stage('services')
        result=self.adapter_operation('prepare')
        result['clock_corrected']=corrected
        return result

    def close(self): self.client.close()


def probe(host, port):
    with socket.create_connection((host, port), timeout=5) as sock:
        transport = paramiko.Transport(sock)
        try:
            transport.start_client(timeout=5)
            return fingerprint(transport.get_remote_server_key().asbytes())
        finally:
            transport.close()
