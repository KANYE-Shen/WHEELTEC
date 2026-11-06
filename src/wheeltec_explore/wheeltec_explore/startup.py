"""Optional console-owned start barrier; CLI/simulation entries are unchanged."""
import json
import os
import time
from pathlib import Path


def wait_for_console_start(spin, *, environment=None, timeout=30., clock=time.monotonic):
    environment = os.environ if environment is None else environment
    directory = environment.get('WHEELTEC_CONSOLE_START_GATE')
    if not directory:
        return
    gate = Path(directory)
    if not gate.is_dir():
        raise RuntimeError('Console start gate is missing; no navigation released')
    ready = gate/'ready.json'
    temporary = ready.with_suffix('.tmp')
    temporary.write_text(json.dumps({'pid': os.getpid(), 'stamp': time.time()}))
    temporary.replace(ready)
    deadline = clock()+timeout
    while clock() < deadline:
        if (gate/'go').is_file():
            return
        spin()
    raise RuntimeError('Console start release timed out; no navigation released')
