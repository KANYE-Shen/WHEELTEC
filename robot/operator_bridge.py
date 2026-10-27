"""Authenticated loopback bridge: status, human heartbeat and stop only."""
import json,os,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from bridge_auth import authenticate

def main():
    token=os.environ.get('WHEELTEC_OPERATOR_TOKEN','')
    if len(token)<32: raise SystemExit('Provide a private operator token of at least 32 characters')
    allowed_origin=os.environ.get('WHEELTEC_OPERATOR_ORIGIN','')
    if not allowed_origin.startswith('https://'): raise SystemExit('Explicit HTTPS operator origin required')
    import rclpy
    from std_msgs.msg import Empty,Bool,String
    rclpy.init(); node=rclpy.create_node('wheeltec_operator_bridge')
    heartbeat=node.create_publisher(Empty,'/safety/operator_heartbeat',10)
    stop=node.create_publisher(Bool,'/safety/estop',10)
    latest={'state':'unavailable'}
    subscription=node.create_subscription(String,'/safety/status',lambda m:latest.update(status=m.data),10)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass # Never log headers, credentials or request targets.
        def serve(self,post=False):
            if not authenticate(self.headers.get('Authorization'),token): self.send_error(401); return
            if post and self.headers.get('Origin')!=allowed_origin: self.send_error(403); return
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Length','0')!='0': self.send_error(413); return
            if not post and self.path=='/api/status': payload=dict(latest)
            elif post and self.path=='/api/heartbeat': heartbeat.publish(Empty()); payload={'received':True}
            elif post and self.path=='/api/stop': stop.publish(Bool(data=True)); payload={'stop_requested':True}
            else: self.send_error(404); return
            data=json.dumps(payload).encode(); self.send_response(200)
            self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_GET(self): self.serve()
        def do_POST(self): self.serve(True)
    server=ThreadingHTTPServer(('127.0.0.1',8765),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally: server.shutdown(); server.server_close(); node.destroy_node(); rclpy.shutdown()
if __name__=='__main__': main()
