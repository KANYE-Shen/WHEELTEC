"""Paired, append-only scenario/seed regressions. All outcomes count."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys
from scenarios import scenario_ids,load_scenario,geometry_at


def wilson(successes,trials,z=1.959963984540054):
    if trials==0: return None,None
    if not 0<=successes<=trials: raise ValueError('invalid counts')
    p=successes/trials; divisor=1+z*z/trials
    center=(p+z*z/(2*trials))/divisor
    half=z*math.sqrt(p*(1-p)/trials+z*z/(4*trials*trials))/divisor
    return max(0.,center-half),min(1.,center+half)


def make_plan(scenarios=None,spawns=None,seeds=range(5),scales=(1.,),position_jitter=.03,yaw_jitter=.06):
    if any(not math.isfinite(x) or x<0 for x in [position_jitter,yaw_jitter,*scales]): raise ValueError('invalid perturbation/scale')
    rows=[]
    for name in scenarios or scenario_ids():
        scene=load_scenario(name)
        for spawn in spawns if spawns is not None else range(len(scene['spawns'])):
            if not 0<=spawn<len(scene['spawns']): raise ValueError('invalid spawn')
            for seed in seeds:
                if seed<0: raise ValueError('invalid seed')
                digest=hashlib.sha256(f'{name}/{spawn}/{seed}'.encode()).digest()
                rng=random.Random(int.from_bytes(digest,'big'))
                pose=list(scene['spawns'][spawn]['pose'])
                pose=[pose[0]+rng.uniform(-position_jitter,position_jitter),pose[1]+rng.uniform(-position_jitter,position_jitter),pose[2]+rng.uniform(-yaw_jitter,yaw_jitter)]
                # Fail the plan rather than silently discard an inconvenient seed.
                if geometry_at(scene,[pose[:2]])[1][0]<.35: raise ValueError('unsafe seeded start')
                for scale in scales:
                    rows.append({'scenario':name,'spawn':spawn,'seed':seed,'scale':float(scale),'pose':pose})
    return rows


def summarize(rows):
    cells=defaultdict(list)
    for row in rows: cells[(row['scenario'],row['spawn'],row['scale'])].append(row)
    output=[]
    for (scene,spawn,scale),trials in sorted(cells.items()):
        count=sum(row.get('success') is True for row in trials); n=len(trials)
        output.append({'scenario':scene,'spawn':spawn,'scale':scale,'successes':count,'trials':n,'success_rate':count/n,'wilson_95':wilson(count,n),'seeds':[x['seed'] for x in trials]})
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scenarios',nargs='+',choices=scenario_ids())
    parser.add_argument('--spawns',type=int,nargs='+')
    parser.add_argument('--seeds',type=int,default=5,help='Number of seeds per cell, minimum 5')
    parser.add_argument('--scales',type=float,nargs='+',default=[1.])
    parser.add_argument('--plan-only',action='store_true')
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if args.seeds<5: parser.error('at least five seeds per cell')
    if len(set(args.scales))!=len(args.scales): parser.error('duplicate scale')
    from check_exploration import source_manifest
    root=args.output.expanduser().resolve()
    plan=make_plan(args.scenarios,args.spawns,range(args.seeds),args.scales)
    source=source_manifest()
    manifest={'schema':1,'plan':plan,'source':source,'realism':'on','seed_count':args.seeds,'position_jitter_m':.03,'yaw_jitter_rad':.06,'all_failures_retained':True}
    if args.resume:
        old=json.loads((root/'plan.json').read_text())
        if old['plan']!=plan or old['source']['sha256']!=source['sha256']: raise SystemExit('Refusing changed plan/source on resume')
    else:
        root.mkdir(parents=True,exist_ok=False)
        (root/'plan.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if args.plan_only:
        print(json.dumps({'planned_trials':len(plan),'output':str(root)},flush=True)); return
    rows=[]
    for index,trial in enumerate(plan):
        if source_manifest()['sha256']!=source['sha256']: raise SystemExit('Source changed during frozen batch; retain results and start a new batch')
        run=root/f'{index:03d}_{trial["scenario"]}_spawn{trial["spawn"]}_seed{trial["seed"]}_scale{trial["scale"]:g}'
        if args.resume and run.exists():
            # Never retry or replace a missing/corrupt result in place.
            returncode=None
        else:
            with (root/(run.name+'-console.log')).open('x') as log:
                command=[sys.executable,str(Path(__file__).with_name('check_exploration.py')),'--scenario',trial['scenario'],'--spawn',str(trial['spawn']),'--seed',str(trial['seed']),'--noise-scale',str(trial['scale']),'--spawn-pose',*map(str,trial['pose']),'--realism','on','--record','--output',str(run)]
                returncode=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
        row={**trial,'run_dir':str(run),'returncode':returncode,'success':False}
        try:
            result=json.loads((run/'result.json').read_text())
            row.update(success=result.get('success') is True,state=result.get('explorer',{}).get('state'),reason=result.get('explorer',{}).get('reason'),acceptance=result.get('acceptance',{}),failures=result.get('failures',[]),map_metrics=result.get('map_metrics',{}),return_error_m=result.get('gazebo_return_error_m'),truth_quality=result.get('truth_quality',{}),resources=result.get('resource_summary',{}))
        except (OSError,ValueError) as exc: row['failures']=[f'missing/unreadable result: {exc}']
        rows.append(row)
        # Summary is a derived view. Raw run directories and frozen plan are immutable.
        summary={'planned_trials':len(plan),'executed_trials':len(rows),'complete':len(rows)==len(plan),'successes':sum(x['success'] for x in rows),'cells':summarize(rows),'rows':rows}
        (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps({'done':len(rows),'total':len(plan),'successes':summary['successes'],'trial':trial,'state':row.get('state')},ensure_ascii=False),flush=True)

if __name__=='__main__': main()
