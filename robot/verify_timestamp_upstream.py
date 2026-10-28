"""Compile/run the pinned upstream headers in an isolated WSL temporary directory."""
import json
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
report=root/'setup/verification/2026-10-28-night/g0-timestamp'
linux='/mnt/d/'+root.as_posix().split(':/',1)[1]
base=linux+'/setup/verification/2026-10-28-night/g0-timestamp'
wsl=['wsl','-d','WHEELTEC-Ubuntu-22.04','--']
tmp=subprocess.check_output(wsl+['mktemp','-d','/tmp/wheeltec-timestamp-XXXXXX'],text=True).strip()
results={'offline_only':True,'temporary_directory':tmp,'full_driver_build':False,'real_robot_verified':False,'states':{}}
for state in ['legacy','pr267','candidate']:
    cmd=wsl+['g++','-std=c++17','-Wall','-Wextra','-Werror','-I'+base+'/fixtures/'+state+'/include',linux+'/robot/test_timestamp_upstream.cpp','-o',tmp+'/'+state]
    if state=='legacy': cmd.insert(len(wsl)+1,'-DLEGACY')
    compiled=subprocess.run(cmd,capture_output=True,text=True)
    result={'compile_returncode':compiled.returncode,'compile_stdout':compiled.stdout,'compile_stderr':compiled.stderr}
    if compiled.returncode==0:
        run=subprocess.run(wsl+[tmp+'/'+state],capture_output=True,text=True)
        result.update(returncode=run.returncode,stdout=run.stdout,stderr=run.stderr)
    results['states'][state]=result
print(json.dumps(results,indent=2))
# Red baselines are expected failures; a compilation failure is NEVER an expected red.
valid=all(v['compile_returncode']==0 for v in results['states'].values()) and all(results['states'][s].get('returncode')==expected for s,expected in [('legacy',1),('pr267',1),('candidate',0)])
sys.exit(0 if valid else 1)
