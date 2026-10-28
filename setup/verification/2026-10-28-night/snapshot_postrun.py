from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,'/mnt/d/虚拟c盘/WHEELTEC/simulation')
from check_exploration import _live_group_members
base=Path('/home/wheeltec/wheeltec_sim_ws/data/runs/20261028-active-scan-ab-v3')
groups=set()
for p in base.glob('*/result.json'):
 r=json.loads(p.read_text())
 for s in r.get('shutdown',{}).values():
  if s and s.get('process_group_id'):groups.add(s['process_group_id'])
remaining={g:_live_group_members(g) for g in groups if _live_group_members(g)}
latest=Path('/home/wheeltec/wheeltec_sim_ws/data/maps/latest.json')
sha=hashlib.sha256(latest.read_bytes()).hexdigest()
assert not remaining
assert sha=='46fe655145eceeb53d0882f7c56cc22714553eea0e9c563c475055409c9ca1c6'
out={'checked_owned_groups':len(groups),'remaining_live_group_members':remaining,'latest_selector_sha256':sha,'latest_unchanged':True,'unrelated_processes_not_managed':True}
p=Path('/mnt/d/虚拟c盘/WHEELTEC/setup/verification/2026-10-28-night/post-run-environment.json')
p.write_text(json.dumps(out,indent=2)+'\n');print(p.read_text())

