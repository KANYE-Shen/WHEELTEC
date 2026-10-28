"""Archive completed/partial owned batch without rescoring missing trials away."""
import argparse,hashlib,json,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('batch');p.add_argument('--partial',action='store_true');args=p.parse_args()
root=Path('/mnt/d/虚拟c盘/WHEELTEC/setup/verification/2026-10-28-night')
base=Path('/home/wheeltec/wheeltec_sim_ws/data/runs')/args.batch
out=root/args.batch.removeprefix('20261028-')
summary=json.loads((base/'summary.json').read_text())
if not args.partial:assert summary['complete']
out.mkdir(exist_ok=False)
for name in ('summary.json','plan.json'):shutil.copyfile(base/name,out/name)
version=args.batch.rsplit('-',1)[-1]
source=json.loads((root/f'active-scan-frozen-source-{version}.json').read_text())['files']
expected=json.loads((base/'plan.json').read_text())['source']['sha256']
assert source==expected,'source archive mismatch'
manifest=[]
for f in sorted(base.rglob('*')):
 if f.is_file():manifest.append(dict(path=str(f.relative_to(base)),bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
attempts=[]
for run in sorted(base.iterdir()):
 if not run.is_dir():continue
 dest=out/run.name;dest.mkdir()
 for name in ('result.json','map.exploration.json','explore.log','launch.log','bag.log','bag/metadata.yaml'):
  f=run/name
  if f.is_file():shutil.copyfile(f,dest/name.replace('/','-'))
 console=base/(run.name+'-console.log')
 if console.is_file():shutil.copyfile(console,dest/'console.log')
 present=(run/'result.json').is_file()
 result=json.loads((run/'result.json').read_text()) if present else {}
 attempts.append(dict(run=run.name,result_present=present,success=result.get('success') is True,error=result.get('error','missing result; interrupted attempt' if not present else None)))
(out/'all-attempts.json').write_text(json.dumps(dict(planned_trials=len(json.loads((base/'plan.json').read_text())['plan']),summary_rows=len(summary['rows']),attempted=len(attempts),successes=sum(x['success'] for x in attempts),partial=args.partial,attempts=attempts),indent=2)+'\n')
(out/'raw-artifacts.json').write_text(json.dumps(dict(raw_root=str(base),raw_retained=True,source_archive_matches=True,files=manifest),indent=2)+'\n')
print(json.dumps(dict(batch=args.batch,summary_rows=len(summary['rows']),all_attempts=len(attempts),successes=sum(x['success'] for x in attempts),partial=args.partial)))

