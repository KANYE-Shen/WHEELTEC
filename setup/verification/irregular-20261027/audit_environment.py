"""Read-only end-of-run audit of isolated test domains; no process mutation."""
import datetime,hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
DATA=Path.home()/'wheeltec_sim_ws/data'
rows=[]
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
    try:
        argv=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        env=dict(x.split(b'=',1) for x in (proc/'environ').read_bytes().split(b'\0') if b'=' in x)
        domain=env.get(b'ROS_DOMAIN_ID',b'').decode()
        if domain in ('84','88','89') and argv:
            rows.append(dict(pid=int(proc.name),domain=domain,command=argv))
    except (OSError,ValueError):continue
latest=DATA/'maps/latest.json'
report=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    domains=[84,88,89],processes=rows,latest_path=str(latest),
    latest_sha256=hashlib.sha256(latest.read_bytes()).hexdigest() if latest.is_file() else None,
    note='Read-only process snapshot. Raw logs still retain nested forced shutdowns; current absence does not imply graceful exits.')
(ROOT/'setup/verification/irregular-20261027/environment-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
