"""Run scoped regressions and retain raw logs; no Gazebo or robot commands."""
import argparse,hashlib,json,os
from pathlib import Path
import re,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
OUT=parser.parse_args().output.expanduser().resolve()
OUT.mkdir(parents=True,exist_ok=False)
commands=[['-m','unittest','discover','-s','src/wheeltec_explore/test','-v']]
commands += [['-m','unittest','discover','-s','simulation','-p',name,'-v'] for name in (
    'test_validation.py','test_regression_batch.py','test_outcomes.py','test_paired_viewpoints.py',
    'test_replay_viewpoints.py','test_explorer_time_ros.py','test_health_ros.py')]
commands += [['-m','unittest','discover','-s','setup/automation','-v'],
             ['-m','unittest','discover','-s','setup/verification/irregular-20261027','-p','test_collector.py','-v']]
rows=[]
env=dict(os.environ,ROS_LOCALHOST_ONLY='1',ROS_DOMAIN_ID='89')
for i,args in enumerate(commands):
    start=time.monotonic();result=subprocess.run([sys.executable,*args],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    log=OUT/f'{i:02d}.log';log.write_bytes(result.stdout)
    match=re.search(rb'Ran (\d+) tests?',result.stdout)
    rows.append(dict(command=[sys.executable,*args],returncode=result.returncode,
        tests=int(match.group(1)) if match else None,wall_seconds=time.monotonic()-start,
        log=str(log),sha256=hashlib.sha256(result.stdout).hexdigest()))
report=dict(check_groups=len(rows),tests=sum(x['tests'] or 0 for x in rows),
    all_passed=all(x['returncode']==0 for x in rows),groups=rows)
(OUT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if not report['all_passed']:raise SystemExit(1)
