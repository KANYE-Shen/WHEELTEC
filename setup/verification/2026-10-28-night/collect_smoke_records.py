from pathlib import Path
import json,hashlib,shutil
root=Path('/mnt/d/虚拟c盘/WHEELTEC/setup/verification/2026-10-28-night')
base=Path('/home/wheeltec/wheeltec_sim_ws/data/runs')
out=root/'smoke-records';out.mkdir(exist_ok=False)
for name in ('20261028-active-scan-smoke-v1','20261028-active-scan-observer-smoke-v3'):
 run=base/name;dest=out/name;dest.mkdir()
 for f in ('result.json','map.exploration.json','explore.log','launch.log','bag.log','bag/metadata.yaml'):
  p=run/f
  if p.is_file():shutil.copyfile(p,dest/f.replace('/','-'))
 manifest=[dict(path=str(p.relative_to(run)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(run.rglob('*')) if p.is_file()]
 (dest/'raw-artifacts.json').write_text(json.dumps(dict(raw_root=str(run),raw_retained=True,files=manifest),indent=2)+'\n')
print('two failed smoke attempts retained')

