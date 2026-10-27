"""One isolated reproduction per retained runtime failure; never replaces seeds."""
import hashlib,json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'simulation'))
from check_exploration import source_manifest
DATA=Path.home()/'wheeltec_sim_ws/data/runs'
OUT=DATA/'20261027-irregular-runtime-reproductions-v1'
OUT.mkdir(parents=True,exist_ok=False)
specs=[('20261027-irregular-gazebo-v2',2,'on',300.,460.,'tf_stale'),
       ('20261027-irregular-nominal-v1',6,'off',120.,280.,'Nav2 did not become active'),
       ('20261027-irregular-nominal-v1',16,'off',120.,280.,'Nav2 did not become active'),
       ('20261027-irregular-nominal-v1',19,'off',120.,280.,'tf_stale')]
plan=[]
for batch,index,mode,budget,deadline,symptom in specs:
    p=json.loads((DATA/batch/'plan.json').read_text())['plan'][index]
    plan.append(dict(original_batch=batch,original_index=index,realism=mode,task_timeout=budget,
                     timeout=deadline,symptom=symptom,trial=p))
source=source_manifest()
(OUT/'plan.json').write_text(json.dumps(dict(source=source,plan=plan,attempts_per_failure=1,not_replacements=True),indent=2)+'\n')
rows=[]
for i,case in enumerate(plan):
    if source_manifest()['sha256']!=source['sha256']:raise RuntimeError('source changed during reproductions')
    t=case['trial'];run=OUT/f'{i:02d}_{t["scenario"]}_seed{t["seed"]}_{case["realism"]}'
    command=[sys.executable,str(ROOT/'simulation/check_exploration.py'),'--scenario',t['scenario'],'--spawn','0',
        '--spawn-pose',*map(str,t['pose']),'--seed',str(t['seed']),'--realism',case['realism'],
        '--viewpoint-strategy',t['strategy'],'--task-timeout',str(case['task_timeout']),'--timeout',str(case['timeout']),
        '--domain','88','--record','--output',str(run)]
    if case['realism']=='off':command=['taskset','-c','0,1,2,3',*command]
    with (OUT/(run.name+'-console.log')).open('x') as log:
        rc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
    row=dict(**case,run=str(run),returncode=rc,reproduced=False)
    if (run/'result.json').is_file():
        raw=(run/'result.json').read_text();r=json.loads(raw)
        log=(run/'explore.log').read_text() if (run/'explore.log').is_file() else ''
        row.update(reproduced=case['symptom'] in raw or case['symptom'] in log,
            state=r.get('explorer',{}).get('state'),reason=r.get('explorer',{}).get('reason'),
            functional_success=r.get('functional_success'),formal_success=r.get('success'),failures=r.get('failures'),
            result_sha256=hashlib.sha256(raw.encode()).hexdigest())
    rows.append(row)
    (OUT/'summary.json').write_text(json.dumps(dict(planned=4,executed=len(rows),rows=rows,
        original_failures_retained=True,no_parameter_repairs_attempted=True),indent=2)+'\n')
    print(json.dumps({k:row.get(k) for k in ('original_batch','original_index','reproduced','state','reason','functional_success')},ensure_ascii=False),flush=True)
