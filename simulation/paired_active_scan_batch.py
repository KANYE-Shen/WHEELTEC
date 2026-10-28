"""Frozen angle-only active observation experiment; every attempted run counts."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import subprocess
import sys
from check_exploration import source_manifest, parse_arguments as check_arguments
from regression_batch import make_plan, wilson

ANGLES = (0., 90., 180., 360.)

def paired_plan(scenarios, seeds):
    if seeds < 5:
        raise ValueError('minimum five seeds')
    pairs = make_plan(scenarios, [0], range(seeds), [1.])
    rows = []
    for index, pair in enumerate(pairs):
        offset = pair['seed'] % len(ANGLES)
        for angle in ANGLES[offset:] + ANGLES[:offset]:
            rows.append(dict(**pair, pair=index, angle=angle))
    return rows

def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row['scenario'], row['spawn'], row['angle']].append(row)
    cells = []
    for (scene, spawn, angle), values in sorted(groups.items()):
        n = len(values)
        k = sum(x.get('success') is True for x in values)
        first = sum(x.get('first_goal') is True for x in values)
        cells.append(dict(scenario=scene, spawn=spawn, angle=angle, trials=n,
                          successes=k, success_rate=k/n, wilson_95=wilson(k,n),
                          first_goal_count=first, first_goal_rate=first/n,
                          first_goal_wilson_95=wilson(first,n),
                          seeds=[x.get('seed') for x in values]))
    return cells

def outcome(trial, run, returncode):
    row = dict(**trial, run_dir=str(run), returncode=returncode,
               success=False, first_goal=False)
    try:
        result = json.loads((run/'result.json').read_text())
        explorer = result.get('explorer') or {}
        goals = explorer.get('goals') or []
        statuses = result.get('status_history') or []
        goal_statuses = [x for x in statuses if x.get('target') is not None]
        row.update(success=result.get('success') is True,
                   functional_success=result.get('functional_success') is True,
                   first_goal=bool(goals or goal_statuses),
                   first_goal_elapsed_ros_s=next((x.get('elapsed_ros_seconds') for x in goal_statuses),None),
                   state=explorer.get('state'), reason=explorer.get('reason'),
                   goals=len(goals), active_scans=explorer.get('active_scans',[]),
                   acceptance=result.get('acceptance',{}),
                   failures=result.get('failures',[]), error=result.get('error'),
                   map_metrics=result.get('map_metrics',{}),
                   health=explorer.get('map_health',{}),
                   trajectory_safety=result.get('trajectory_safety',{}),
                   return_error_m=result.get('gazebo_return_error_m'),
                   traveled_distance_m=result.get('truth_traveled_distance_m'),
                   truth_quality=result.get('truth_quality',{}),
                   shutdown=result.get('shutdown',{}),
                   latest_preserved=result.get('latest_selector_sha256_before') ==
                                    result.get('latest_selector_sha256_after'))
    except (OSError, ValueError, TypeError) as exc:
        row['failures'] = [f'missing/unreadable result: {exc}']
    return row

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scenarios',nargs='+',default=['irregular_arc','recess'])
    parser.add_argument('--seeds',type=int,default=5)
    parser.add_argument('--task-timeout',type=float,default=300.)
    parser.add_argument('--timeout',type=float,default=460.)
    parser.add_argument('--domain',type=int,default=90)
    parser.add_argument('--resume',action='store_true')
    args = parser.parse_args()
    check_arguments(['--task-timeout',str(args.task_timeout),'--timeout',str(args.timeout),
                     '--domain',str(args.domain)])
    plan = paired_plan(args.scenarios,args.seeds)
    settings = dict(realism='on',task_timeout=args.task_timeout,timeout=args.timeout,
                    domain=args.domain,viewpoint_strategy='centroid')
    root = args.output.expanduser().resolve()
    source = source_manifest()
    if args.resume:
        old = json.loads((root/'plan.json').read_text())
        if old['plan'] != plan or old['source']['sha256'] != source['sha256'] or old['settings'] != settings:
            raise RuntimeError('changed frozen plan/source/settings; preserve and start new batch')
    else:
        root.mkdir(parents=True,exist_ok=False)
        (root/'plan.json').write_text(json.dumps(dict(plan=plan,source=source,settings=settings,
            all_failures_retained=True,position_jitter_m=.03,yaw_jitter_rad=.06),indent=2)+'\n')
    rows = []
    for index,trial in enumerate(plan):
        if source_manifest()['sha256'] != source['sha256']:
            raise RuntimeError('source changed; retain batch and start another')
        run = root/f'{index:03d}_{trial["scenario"]}_seed{trial["seed"]}_angle{trial["angle"]:g}'
        console_log = root/(run.name+'-console.log')
        rc = None
        if not (args.resume and (run.exists() or console_log.exists())):
            command = [sys.executable,str(Path(__file__).with_name('check_exploration.py')),
                '--scenario',trial['scenario'],'--spawn',str(trial['spawn']),
                '--spawn-pose',*map(str,trial['pose']),'--seed',str(trial['seed']),
                '--noise-scale','1','--realism','on','--viewpoint-strategy','centroid',
                '--active-scan-angle',str(trial['angle']),'--task-timeout',str(args.task_timeout),
                '--timeout',str(args.timeout),'--domain',str(args.domain),'--record','--output',str(run)]
            with console_log.open('x') as log:
                rc = subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
        rows.append(outcome(trial,run,rc))
        report = dict(complete=len(rows)==len(plan),planned_trials=len(plan),executed_trials=len(rows),
                      successes=sum(x['success'] for x in rows),cells=summarize(rows),rows=rows)
        (root/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(done=len(rows),total=len(plan),scene=trial['scenario'],
             seed=trial['seed'],angle=trial['angle'],state=rows[-1].get('state'),
             first_goal=rows[-1]['first_goal'],success=rows[-1]['success'])),flush=True)

if __name__ == '__main__':
    main()
