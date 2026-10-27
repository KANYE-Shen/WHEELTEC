"""SSH with explicit SHA256 pinning. Never auto-accept a host key."""
import socket
import threading
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
                raise ValueError('Target rejected request: ' +
                                 str(response.status))
            return data
        finally:
            channel.close()

    def terminal(self):
        return self.client.invoke_shell(term='xterm-256color', width=100, height=30)

    def close(self): self.client.close()


def probe(host, port):
    with socket.create_connection((host, port), timeout=5) as sock:
        transport = paramiko.Transport(sock)
        try:
            transport.start_client(timeout=5)
            return fingerprint(transport.get_remote_server_key().asbytes())
        finally:
            transport.close()
