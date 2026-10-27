import io
import json
import unittest
from console.backend.transport import SSH


class Channel:
    def __init__(self): self.file = io.BytesIO(
        b'HTTP/1.0 200 OK\r\nContent-Length: 11\r\n\r\n{"ok":true}'); self.closed = False

    def sendall(self, data): pass
    def makefile(self, *args): return self.file
    def close(self): self.closed = True; self.file.close()


class TransportTests(unittest.TestCase):
    def test_http_close_keeps_channel_alive_until_body_consumed(self):
        ssh = SSH.__new__(SSH)
        channel = Channel()
        ssh.channel = lambda: channel
        self.assertEqual(json.loads(
            ssh.request('GET', '/state')), {'ok': True})
        self.assertTrue(channel.closed)
