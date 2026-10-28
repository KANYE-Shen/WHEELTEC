"""One-shot local continuation guard; never approves robot motion or pushes git."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
STATE=ROOT/'setup/verification/2026-10-27-irregular-frontier-task.json'
SESSION='01a17bf2-e4a2-7283-9e65-2ec9169ff665'

def should_resume(state, now):
    status=state.get('status')
    if status not in ('completed','blocked','running','pending','awaiting_continuation'):
        raise ValueError('Unknown task status; refusing automatic execution')
    if status in ('completed','blocked'):return False
    # An agent actively updating its checkpoint is already working; avoid two writers.
    if status=='running' and 0 <= now-float(state.get('heartbeat_epoch',0)) < 300:return False
    return True

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    state=json.loads(STATE.read_text(encoding='utf-8'))
    eligible=should_resume(state,time.time())
    if args.dry_run:
        print(json.dumps({'eligible_now':eligible,'session':SESSION,'task_status':state['status'],'mode':'dry_run_no_model_invocation'}))
        return
    if not eligible:return
    logs=Path(tempfile.gettempdir())/'wheeltec-irregular-frontier-wake-20261028'
    logs.mkdir(exist_ok=True)
    stamp=time.strftime('%Y%m%dT%H%M%S')
    # Serialize the queue request; the existing chat retains its permission mode.
    import msvcrt
    with (logs/'worker.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        try:
            if not should_resume(json.loads(STATE.read_text(encoding='utf-8')),time.time()):return
            binaries=list((Path(os.environ['LOCALAPPDATA'])/'OpenAI/Codex/bin').glob('*/codex.exe'))
            if not binaries:raise RuntimeError('Codex executable unavailable')
            binary=max(binaries,key=lambda x:x.stat().st_mtime)
            prompt=(ROOT/'setup/automation/irregular-frontiers-continuation.md').read_text(encoding='utf-8')
            command=[str(binary),'queue','--thread',SESSION,'--message',prompt]
            result=subprocess.run(command,capture_output=True,cwd=ROOT)
            (logs/(stamp+'-exit.json')).write_text(json.dumps({'returncode':result.returncode,'session':SESSION,'started_at':stamp}),encoding='utf-8')
            if result.returncode:raise SystemExit(result.returncode)
        finally:
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

if __name__=='__main__':main()
