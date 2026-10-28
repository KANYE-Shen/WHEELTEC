from pathlib import Path
import shutil,json,hashlib
batch=Path('/home/wheeltec/wheeltec_sim_ws/data/runs/20261028-active-scan-ab-v1')
out=Path('/mnt/d/虚拟c盘/WHEELTEC/setup/verification/2026-10-28-night/active-scan-ab-v1')
summary=json.loads((batch/'summary.json').read_text())
assert summary['complete'] and summary['executed_trials']==40
out.mkdir(exist_ok=False)
for name in ('summary.json','plan.json'):shutil.copyfile(batch/name,out/name)
manifest=[]
for p in sorted(batch.rglob('*')):
 if p.is_file():
  manifest.append({'path':str(p.relative_to(batch)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
for row in summary['rows']:
 run=Path(row['run_dir']); dest=out/run.name;dest.mkdir()
 for name in ('result.json','map.exploration.json','explore.log','launch.log','bag.log','bag/metadata.yaml'):
  p=run/name
  if p.is_file():shutil.copyfile(p,dest/(name.replace('/','-')))
 if (batch/(run.name+'-console.log')).is_file():shutil.copyfile(batch/(run.name+'-console.log'),dest/'console.log')
(out/'raw-artifacts.json').write_text(json.dumps({'raw_root':str(batch),'raw_retained':True,'files':manifest},indent=2)+'\n')
source=json.loads((out.parent/'active-scan-frozen-source-v1.json').read_text())['files']
expected=json.loads((batch/'plan.json').read_text())['source']['sha256']
assert source==expected,'frozen source archive mismatch'
print(json.dumps({'runs':len(summary['rows']),'successes':summary['successes'],'source_archive_matches':True,'raw_files':len(manifest),'cells':summary['cells']},indent=2))

