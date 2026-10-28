from pathlib import Path
import json,os,signal
root='/home/wheeltec/wheeltec_sim_ws/data/runs/20261028-active-scan-ab-v2'
matches=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  args=(p/'cmdline').read_bytes().decode().strip('\0').split('\0')
  if any(Path(a).name=='paired_active_scan_batch.py' for a in args) and root in args:matches.append((int(p.name),args))
 except (OSError,UnicodeError):pass
assert len(matches)==1,matches
pid,args=matches[0];children=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  stat=(p/'stat').read_text().split()
  child=(p/'cmdline').read_bytes().decode().strip('\0').split('\0')
  if int(stat[3])==pid and any(Path(a).name=='check_exploration.py' for a in child):
   output=child[child.index('--output')+1]
   assert output.startswith(root+'/')
   children.append((int(p.name),child))
 except (OSError,UnicodeError):pass
record={'reason':'Protocol diagnosis: no status samples at all in affected short-lived Explorer runs; wall drain alone insufficient. Stop invalid diagnostic batch before testing subscriber readiness. Preserve partial summary and all raw trials.','parent':pid,'children':[x[0] for x in children],'root':root,'signals':'SIGINT only; check runner performs its owned stack shutdown'}
out=Path('/mnt/d/虚拟c盘/WHEELTEC/setup/verification/2026-10-28-night/v2-interruption.json')
out.write_text(json.dumps(record,indent=2)+'\n')
for child,_ in children:os.kill(child,signal.SIGINT)
os.kill(pid,signal.SIGINT)
print(json.dumps(record))

