"""Launch-owned estimate recorder and read-only process viewer.

This program has no control publishers, simulator truth or evaluation geometry.
Closing the browser cannot affect the ROS session.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from view_process import atomic_text, export_replay, make_server

TERMINAL = ('completed','completed_with_residual_frontiers','map_unstable','incomplete','failed','interrupted')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--metadata', default='{}')
    parser.add_argument('--open-browser', choices=('true','false'), default='true')
    args = parser.parse_args(argv)
    run = args.run.expanduser().resolve()
    run.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(args.metadata)
    server = make_server(run, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = 'http://127.0.0.1:'+str(server.server_port)+'/'
    session = {'version':1, 'session_kind':'normal_exploration', 'independent_assessment':False,
               'started_at':datetime.now(timezone.utc).isoformat(), 'run_dir':str(run),
               'viewer_url':url, 'recorder_pid':os.getpid(), 'scenario':metadata}
    atomic_text(run/'session.json',json.dumps(session,ensure_ascii=False,indent=2)+'\n')
    print('过程查看器 '+url+'\n过程记录 '+str(run/'process.json')+'\n结束后回放 '+str(run/'replay.html'),flush=True)
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    if args.open_browser == 'true':
        try:
            subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden',
                              '-Command',"Start-Process '"+url+"'"],
                             stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError as exc:
            print('请手动打开上方查看器网址：'+str(exc),flush=True)
    node = capture = None
    finalized = False
    exit_code = 0
    try:
        import rclpy
        from rclpy.parameter import Parameter
        from rclpy.signals import SignalHandlerOptions
        from tf2_ros import Buffer, TransformListener
        from process_capture import ProcessCapture
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node = rclpy.create_node('wheeltec_process_capture',parameter_overrides=[Parameter('use_sim_time',value=True)])
        buffer = Buffer(node=node)
        listener = TransformListener(buffer,node)
        capture = ProcessCapture(node,buffer,run/'process.json',metadata)
        capture.save()
        while not stop.is_set():
            if finalized:
                stop.wait(.2)
                continue
            rclpy.spin_once(node,timeout_sec=.1)
            if capture.status.get('state') in TERMINAL:
                capture.close(capture.status)
                finalized = True
                export_replay(run/'process.json')
                print('探索已结束，自包含回放已保存：'+str(run/'replay.html'),flush=True)
    except Exception as exc:
        exit_code = 1
        session['capture_error'] = repr(exc)
        print('过程录制异常：'+repr(exc),flush=True)
    finally:
        if capture is not None and not finalized:
            terminal = capture.status if capture.status.get('state') in TERMINAL else {
                **capture.status,'state':'interrupted' if exit_code==0 else 'failed',
                'reason':'operator_interrupted' if exit_code==0 else 'capture_error'}
            capture.status = terminal
            try:
                capture.close(terminal)
                export_replay(run/'process.json')
            except Exception as exc:
                exit_code = 1
                session['finalize_error'] = repr(exc)
                print('过程收尾异常：'+repr(exc),flush=True)
        if node is not None:
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        server.shutdown()
        server.server_close()
        session.update(ended_at=datetime.now(timezone.utc).isoformat(),recorder_exit_code=exit_code)
        atomic_text(run/'session.json',json.dumps(session,ensure_ascii=False,indent=2)+'\n')
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
