"""Self-contained estimate-only replay export and fixed-route loopback server.

No ROS or npm dependency. serve never offers directory listing or write routes.
"""
import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import signal
import threading
from urllib.parse import urlsplit


DIRECTORY = Path(__file__).resolve().parent


def atomic_text(path, text):
    path = Path(path)
    temporary = path.with_name(path.name+'.viewer-tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def checked_document(path):
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    if document.get('version') != 1 or document.get('coordinate_frame') != 'map':
        raise ValueError('Expected process.json version 1 in coordinate_frame map')
    if not isinstance(document.get('frames'), list) or not isinstance(document.get('maps'), list):
        raise ValueError('Process frames and maps must be arrays')
    return document


def embedded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',',':'), allow_nan=False).replace('<', '\\u003c')


def render_page(document=None, result=None, live=False):
    template = (DIRECTORY/'process_viewer.html').read_text(encoding='utf-8')
    script = (DIRECTORY/'process_viewer.js').read_text(encoding='utf-8')
    values = {'/* VIEWER_CODE */':script, '__PROCESS_DATA__':embedded(document),
              '__RESULT_DATA__':embedded(result), '__LIVE_DATA__':'true' if live else 'false'}
    # Replace template tokens once; recorded text may itself contain token names.
    return re.sub(r'/\* VIEWER_CODE \*/|__PROCESS_DATA__|__RESULT_DATA__|__LIVE_DATA__',
                  lambda match:values[match.group(0)],template)


def export_replay(process_path, output=None, result_path=None):
    process_path = Path(process_path)
    document = checked_document(process_path)
    result_path = Path(result_path) if result_path else process_path.with_name('result.json')
    result = json.loads(result_path.read_text(encoding='utf-8')) if result_path.is_file() and not result_path.is_symlink() else None
    output = Path(output) if output else process_path.with_name('replay.html')
    atomic_text(output, render_page(document, result))
    return output


def make_server(run, port=0):
    run = Path(run).resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, body=b'', kind='text/plain; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def do_GET(self):
            host = self.headers.get('Host', '')
            if host not in ('127.0.0.1:'+str(self.server.server_port), 'localhost:'+str(self.server.server_port)):
                return self.respond(403)
            origin = self.headers.get('Origin')
            if origin and origin not in ('http://127.0.0.1:'+str(self.server.server_port), 'http://localhost:'+str(self.server.server_port)):
                return self.respond(403)
            route = urlsplit(self.path).path
            if route == '/':
                return self.respond(200, render_page(live=True).encode('utf-8'), 'text/html; charset=utf-8')
            names = {'/process.json':'process.json', '/result.json':'result.json', '/replay.html':'replay.html'}
            name = names.get(route)
            if name is None:
                return self.respond(404)
            path = run/name
            if path.is_symlink() or not path.is_file() or path.resolve().parent != run:
                return self.respond(404)
            try:
                payload = path.read_bytes()
            except OSError:
                return self.respond(404)
            return self.respond(200, payload, 'text/html; charset=utf-8' if name.endswith('.html') else 'application/json; charset=utf-8')

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            self.respond(405)

        do_PUT = do_DELETE = do_PATCH = do_POST

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('export', help='Generate double-clickable replay.html beside process.json')
    export.add_argument('process', type=Path)
    export.add_argument('--output', type=Path)
    export.add_argument('--result', type=Path)
    serve = sub.add_parser('serve', help='Read-only local live/replay server')
    serve.add_argument('run', type=Path)
    serve.add_argument('--port', type=int, default=0)
    args = parser.parse_args(argv)
    if args.command == 'export':
        print(export_replay(args.process, args.output, args.result))
        return 0
    server = make_server(args.run, args.port)
    print('过程查看器 http://127.0.0.1:'+str(server.server_port)+'/', flush=True)
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        while not stop.wait(.25):
            pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
