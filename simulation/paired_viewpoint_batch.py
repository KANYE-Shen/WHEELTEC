"""Frozen paired Gazebo/ROS runs. Strategy is the only A/B input difference."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from check_exploration import source_manifest
from regression_batch import make_plan,wilson


def paired_plan(scenarios,seeds):
    if seeds<5: raise ValueError('minimum five seeds')
    pairs=make_plan(scenarios,[0],range(seeds),[1.])
    return [dict(**p,strategy=s,pair=i) for i,p in enumerate(pairs)
            for s in (('centroid','visibility') if p['seed']%2==0 else ('visibility','centroid'))]


def summarize(rows):
    cells=[]
    for scene in sorted({x['scenario'] for x in rows}):
        for strategy in ('centroid','visibility'):
            values=[x for x in rows if x['scenario']==scene and x['strategy']==strategy]
            n=len(values);k=sum(x['success'] for x in values)
            cells.append(dict(scenario=scene,spawn=0,strategy=strategy,trials=n,successes=k,
                              success_rate=k/n,wilson_95=wilson(k,n)))
    return cells


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scenarios',nargs='+',default=['irregular_arc','irregular_frame'])
    parser.add_argument('--seeds',type=int,default=5)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    plan=paired_plan(args.scenarios,args.seeds)
    root=args.output.expanduser().resolve();source=source_manifest()
    if args.resume:
        old=json.loads((root/'plan.json').read_text())
        if old['plan']!=plan or old['source']['sha256']!=source['sha256']: raise RuntimeError('changed frozen plan/source')
    else:
        root.mkdir(parents=True,exist_ok=False)
        (root/'plan.json').write_text(json.dumps(dict(source=source,plan=plan,realism='on',all_failures_retained=True),indent=2)+'\n')
    rows=[]
    for i,trial in enumerate(plan):
        if source_manifest()['sha256']!=source['sha256']: raise RuntimeError('source changed; retain batch and start another')
        run=root/f'{i:03d}_{trial["scenario"]}_seed{trial["seed"]}_{trial["strategy"]}'
        rc=None
        if not (args.resume and run.exists()):
            command=[sys.executable,str(Path(__file__).with_name('check_exploration.py')),
                     '--scenario',trial['scenario'],'--spawn','0','--spawn-pose',*map(str,trial['pose']),
                     '--seed',str(trial['seed']),'--noise-scale','1','--realism','on',
                     '--viewpoint-strategy',trial['strategy'],'--domain','88','--record','--output',str(run)]
            with (root/(run.name+'-console.log')).open('x') as log:
                rc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
        row=dict(**trial,run_dir=str(run),returncode=rc,success=False)
        try:
            r=json.loads((run/'result.json').read_text())
            row.update(success=r.get('success') is True,state=r.get('explorer',{}).get('state'),
                       reason=r.get('explorer',{}).get('reason'),goals=len(r.get('explorer',{}).get('goals',[])),
                       acceptance=r.get('acceptance',{}),failures=r.get('failures',[]),map_metrics=r.get('map_metrics',{}),
                       truth_quality=r.get('truth_quality',{}),realism=r.get('realism',{}),
                       latest_preserved=r.get('latest_selector_sha256_before')==r.get('latest_selector_sha256_after'))
        except (OSError,ValueError) as exc: row['failures']=[str(exc)]
        rows.append(row)
        report=dict(complete=len(rows)==len(plan),planned_trials=len(plan),executed_trials=len(rows),
                    successes=sum(x['success'] for x in rows),cells=summarize(rows),rows=rows)
        (root/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(done=len(rows),total=len(plan),strategy=trial['strategy'],scene=trial['scenario'],
                              seed=trial['seed'],state=row.get('state'),goals=row.get('goals'),success=row['success'])),flush=True)

if __name__=='__main__': main()
