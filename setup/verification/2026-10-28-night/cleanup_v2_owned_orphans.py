from pathlib import Path
import os,signal,time,json
root='/home/wheeltec/wheeltec_sim_ws/data/runs/20261028-active-scan-ab-v2/'
expected={6835:'wheeltec-validation-6822',6837:root}
def live(group):
 result=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   stat=(p/'stat').read_text().rpartition(')')[2].split()
   if int(stat[2])==group and stat[0] not in ('Z','X','x'):result.append(int(p.name))
  except OSError:pass
 return result
records=[]
for pid,marker in expected.items():
 p=Path('/proc')/str(pid)
 assert marker in (p/'cmdline').read_bytes().decode().replace('\0',' '),pid
 assert os.getpgid(pid)==pid
 records.append({'group':pid,'before':live(pid),'verified_owner_marker':marker,'forced_kill':False})
for item in records:os.killpg(item['group'],signal.SIGINT)
deadline=time.monotonic()+25.
while any(live(item['group']) for item in records) and time.monotonic()<deadline:time.sleep(.1)
for item in records:
 if live(item['group']):
  os.killpg(item['group'],signal.SIGKILL);item['forced_kill']=True
 item['after']=live(item['group'])
 time.sleep(.1)
 item['after']=live(item['group'])
out=Path('/mnt/d/虚拟c盘/WHEELTEC/setup/verification/2026-10-28-night/v2-owned-orphan-cleanup.json')
out.write_text(json.dumps({'scope':'Only exact verified v2 groups; parent interruption did not complete owned cleanup. This attempt remains invalid.','groups':records},indent=2)+'\n')
print(out.read_text())

