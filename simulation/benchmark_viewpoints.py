"""Paired synthetic-grid mechanism benchmark, never an exploration acceptance test."""
import argparse
from collections import defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from scipy.ndimage import distance_transform_edt,label
from irregular_fixtures import LAYOUTS,fixture,frontier_cells,ray_clear_oracle
from wheeltec_explore.frontiers import select_frontiers
from regression_batch import wilson
from check_exploration import source_manifest


def inspect_goals(grid,robot,result):
    # Independent EDT and four-connected labeling; no internal explorer safe set.
    data=np.asarray(grid.data).reshape(grid.height,grid.width)
    yy,xx=np.indices(data.shape)
    border=np.minimum.reduce([xx+.5,yy+.5,grid.width-xx-.5,grid.height-yy-.5])*grid.resolution
    safe=(distance_transform_edt((data>=0)&(data<=25))*grid.resolution>.35+grid.resolution*.5)&(border>=.35)
    components,_=label(safe)
    rx,ry=grid.world_to_cell(*robot); component=components[ry,rx]
    fs=frontier_cells(grid)
    goals=[]
    for goal in result.goals:
        a=grid.world_to_cell(goal.x,goal.y)
        visible=[b for b in fs if ray_clear_oracle(grid,a,b)]
        valid=component>0 and components[a[1],a[0]]==component and goal.distance>=.2
        goals.append(dict(**asdict(goal),visible_cells=len(visible),total_frontier_cells=len(fs),
                          oracle_gain=len(visible)/(.5+goal.distance),safe_and_connected=bool(valid)))
    return {'goals':goals,'all_safe':all(x['safe_and_connected'] for x in goals),
            'best_oracle_gain':max((x['oracle_gain'] for x in goals),default=0.),
            'maximum_visible_cells':max((x['visible_cells'] for x in goals),default=0),
            'unreachable_clusters':result.unreachable_clusters,
            'diagnostics':result.viewpoint_diagnostics}


def summarize(rows):
    cells=defaultdict(list)
    for row in rows: cells[(row['layout'],row['spawn'])].append(row)
    summary=[]
    for (layout,spawn),values in sorted(cells.items()):
        improved=sum(x['visibility']['best_oracle_gain']>x['centroid']['best_oracle_gain']+1e-9 for x in values)
        worse=sum(x['visibility']['best_oracle_gain']+1e-9<x['centroid']['best_oracle_gain'] for x in values)
        summary.append(dict(layout=layout,spawn=spawn,pairs=len(values),improved=improved,worse=worse,
            unchanged=len(values)-improved-worse,improvement_wilson_95=wilson(improved,len(values)),
            mean_gain_before=float(np.mean([x['centroid']['best_oracle_gain'] for x in values])),
            mean_gain_after=float(np.mean([x['visibility']['best_oracle_gain'] for x in values])),
            mean_visible_before=float(np.mean([x['centroid']['maximum_visible_cells'] for x in values])),
            mean_visible_after=float(np.mean([x['visibility']['maximum_visible_cells'] for x in values]))))
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seeds',type=int,default=5)
    args=parser.parse_args()
    if args.seeds<5: parser.error('minimum five seeds')
    root=args.output.expanduser().resolve();root.mkdir(parents=True,exist_ok=False)
    source=source_manifest()
    plan=[dict(layout=l,spawn=p,seed=s) for l in LAYOUTS for p in range(3) for s in range(args.seeds)]
    (root/'plan.json').write_text(json.dumps(dict(source=source,plan=plan,data_kind='synthetic',acceptance_test=False),indent=2)+'\n')
    rows=[]
    for case in plan:
        if source_manifest()['sha256']!=source['sha256']: raise RuntimeError('source changed during frozen benchmark')
        grid,robot=fixture(**case);row=dict(**case,robot=robot,grid_sha256=hashlib.sha256(bytes(v+1 for v in grid.data)).hexdigest())
        strategies=('centroid','visibility') if case['seed']%2==0 else ('visibility','centroid')
        for strategy in strategies:
            started=time.perf_counter();result=select_frontiers(grid,robot,frontier_viewpoint_strategy=strategy)
            elapsed=time.perf_counter()-started
            row[strategy]=dict(**inspect_goals(grid,robot,result),selector_wall_seconds=elapsed)
        rows.append(row)
        (root/'rows.json').write_text(json.dumps(rows,indent=2)+'\n')
    elapsed={s:dict(p50=float(np.percentile([x[s]['selector_wall_seconds'] for x in rows],50)),
                    p95=float(np.percentile([x[s]['selector_wall_seconds'] for x in rows],95)),
                    maximum=max(x[s]['selector_wall_seconds'] for x in rows)) for s in ('centroid','visibility')}
    report=dict(data_kind='synthetic',acceptance_test=False,pairs=len(rows),cells=summarize(rows),timing_seconds=elapsed,
                all_goals_safe=all(x[s]['all_safe'] for x in rows for s in ('centroid','visibility')),
                no_goal_cases=[{k:x[k] for k in ('layout','spawn','seed')} for x in rows if any(not x[s]['goals'] for s in ('centroid','visibility'))],
                limitations=['LOS only; no measured sensor FOV or information gain','Not a closed-loop exploration success rate','Desktop load, not RDK X5 timing'])
    (root/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
