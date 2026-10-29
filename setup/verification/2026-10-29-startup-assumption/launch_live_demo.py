import json,os,subprocess,sys,hashlib,zipfile
from pathlib import Path
root=Path('/mnt/d/虚拟c盘/WHEELTEC');sys.path.insert(0,str(root/'simulation'))
from check_exploration import source_manifest
out=root/'setup/verification/2026-10-29-startup-assumption'
base=Path.home()/'wheeltec_sim_ws/data/runs/20261029-startup-assumption-view-v1'
base.mkdir(exist_ok=False)
plan=json.loads((root/'setup/verification/2026-10-28-night/active-scan-ab-v3/plan.json').read_text())
trial=next(x for x in plan['plan'] if x['scenario']=='irregular_arc' and x['seed']==0 and x['angle']==360)
source=source_manifest()
(out/'source.json').write_text(json.dumps(source,indent=2)+'\n')
with zipfile.ZipFile(out/'frozen-source.zip','x',zipfile.ZIP_DEFLATED) as z:
 for name in source['sha256']:z.write(root/name,name)
command=[sys.executable,str(root/'simulation/check_exploration.py'),'--scenario',trial['scenario'],'--spawn','0','--spawn-pose',*map(str,trial['pose']),'--seed','0','--realism','on','--noise-scale','1','--active-scan-angle','360','--initial-rotation-assumed-safe','--task-timeout','300','--timeout','460','--domain','90','--record','--output',str(base/'candidate-seed0')]
env=dict(os.environ,ROS_DOMAIN_ID='90',ROS_LOCALHOST_ONLY='1')
with (base/'candidate-console.log').open('x') as log:
 process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
receipt={'pid':process.pid,'process_group':process.pid,'command':command,'run':str(base/'candidate-seed0'),'source_hashes':source['sha256'],'single_seed_demonstration_not_acceptance':True,'physical_robot':False}
(out/'live-start.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'pid':process.pid,'run':receipt['run']}))
