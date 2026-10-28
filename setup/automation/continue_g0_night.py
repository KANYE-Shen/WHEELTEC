"""One-shot quota check; queues a prompt in the same chat with existing permissions."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
ROOT=Path(__file__).resolve().parents[2]
STATE=ROOT/'setup/verification/2026-10-28-night/task.json'
SESSION='01a17bf2-e4a2-7283-9e65-2ec9169ff665'

def should_resume(completed, locked, quota):
    return not completed and not locked and quota

def quota_failure(events):
    failed=False
    for event in events:
        payload=event.get('payload',{}) if event.get('type')=='event_msg' else event
        kind=payload.get('type')
        if kind in ('task_started','task_complete'):failed=False
        if kind=='error':
            text=json.dumps(payload,ensure_ascii=False).lower()
            if any(x in text for x in ('usage limit','usage_limit','quota','额度')):failed=True
    return failed

def writer_locked():
    import msvcrt
    path=Path.home()/'.codex/thread-writer-locks'/f'{SESSION}.lock'
    if not path.exists():return False
    try:
        with path.open('rb') as file:
            msvcrt.locking(file.fileno(),msvcrt.LK_NBRLCK,1)
            msvcrt.locking(file.fileno(),msvcrt.LK_UNLCK,1)
        return False
    except OSError:return True

def latest_quota_failure():
    paths=list((Path.home()/'.codex/sessions').glob(f'**/*{SESSION}.jsonl'))
    if not paths:return False
    path=max(paths,key=lambda p:p.stat().st_mtime)
    with path.open('rb') as file:
        file.seek(max(0,path.stat().st_size-1048576))
        lines=file.read().decode('utf-8',errors='replace').splitlines()
    events=[]
    for line in lines:
        try:events.append(json.loads(line))
        except json.JSONDecodeError:pass
    return quota_failure(events)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    state=json.loads(STATE.read_text(encoding='utf-8'))
    locked=writer_locked()
    quota=state.get('status')=='quota_exhausted' or latest_quota_failure()
    eligible=should_resume(state.get('status')=='completed',locked,quota)
    if args.dry_run:
        print(json.dumps({'eligible':eligible,'writer_locked':locked,'quota_failure':quota,'status':state.get('status'),'resume_at':state.get('resume_at'),'session':SESSION}))
        return
    if not eligible:return
    # The official queue command uses this chat's existing server and permissions.
    # It never launches an exec agent or changes any approval/sandbox setting.
    binaries=list((Path.home()/'AppData/Local/OpenAI/Codex/bin').glob('*/codex.exe'))
    if not binaries:raise RuntimeError('Codex CLI missing')
    binary=max(binaries,key=lambda p:p.stat().st_mtime)
    prompt=(ROOT/'setup/automation/g0-night-continuation.md').read_text(encoding='utf-8')
    result=subprocess.run([str(binary),'queue','--thread',SESSION,'--message',prompt],capture_output=True,cwd=ROOT)
    logs=Path(tempfile.gettempdir())/'wheeltec-g0-night-20261029'
    logs.mkdir(exist_ok=True)
    (logs/(time.strftime('%Y%m%dT%H%M%S')+'-queue.json')).write_text(json.dumps({'returncode':result.returncode,'session':SESSION,'kind':'same_thread_queue_existing_permissions'}),encoding='utf-8')
    if result.returncode:raise SystemExit(result.returncode)
if __name__=='__main__':main()
