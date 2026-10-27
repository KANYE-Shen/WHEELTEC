"""Replay fixed timestamps from genuine recorded ROS captures, without truth input.

Counterfactual one-step planning on historical maps, NOT new robot trajectories.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from benchmark_viewpoints import inspect_goals
from check_exploration import source_manifest
from wheeltec_explore.frontiers import Grid,select_frontiers

OFFSETS=(5.,30.,60.,120.,240.)


def snapshot(document,offset):
    frames=document['frames']
    if not frames: return None,'empty_capture'
    target=frames[0]['t']+offset
    frame=next((x for x in frames if x['t']>=target),None)
    if frame is None: return None,'timestamp_not_recorded'
    if frame.get('pose') is None: return None,'missing_or_stale_pose'
    if frame.get('pose_age_s') is None or not 0<=frame['pose_age_s']<=1.: return None,'stale_pose'
    if frame.get('map') is None: return None,'no_map'
    if frame.get('scan_age_s') is None or not 0<=frame['scan_age_s']<=1.: return None,'stale_scan'
    g=document['maps'][frame['map']]
    return (Grid(g['width'],g['height'],g['resolution'],*g['origin'],g['data']),frame),'ready'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix',type=Path,default=Path(__file__).resolve().parents[1]/'setup/verification/unknown_rooms/matrix.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.output.expanduser().resolve();root.mkdir(parents=True,exist_ok=False)
    cases=json.loads(args.matrix.read_text(encoding='utf-8'))['cases'];source=source_manifest()
    (root/'plan.json').write_text(json.dumps(dict(source=source,cases=[c['result'] for c in cases],offsets=OFFSETS,
        no_truth_inputs=True,data_kind='recorded_ros_capture',counterfactual_one_step_only=True,visited_history='not_reconstructed'),indent=2)+'\n')
    rows=[]
    for case in cases:
        process=Path(case['result']).parent/'process.json'
        try: raw=process.read_bytes();document=json.loads(raw)
        except (OSError,ValueError) as exc:
            rows.append(dict(case=case['case'],error=str(exc)));continue
        for offset in OFFSETS:
            if source_manifest()['sha256']!=source['sha256']: raise RuntimeError('source changed during replay')
            item,reason=snapshot(document,offset)
            row=dict(case=case['case'],offset_s=offset,status=reason,capture_sha256=hashlib.sha256(raw).hexdigest())
            if item is not None:
                grid,frame=item
                row.update(t=frame['t'],pose=frame['pose'],issues=frame.get('issues',[]),map_index=frame['map'])
                for strategy in ('centroid','visibility'):
                    started=time.perf_counter()
                    result=select_frontiers(grid,tuple(frame['pose'][:2]),frontier_viewpoint_strategy=strategy)
                    elapsed=time.perf_counter()-started
                    row[strategy]=dict(**inspect_goals(grid,frame['pose'][:2],result),selector_wall_seconds=elapsed)
            rows.append(row)
            (root/'rows.json').write_text(json.dumps(rows,indent=2)+'\n')
    comparable=[r for r in rows if r.get('status')=='ready']
    improved=sum(r['visibility']['best_oracle_gain']>r['centroid']['best_oracle_gain']+1e-9 for r in comparable)
    worse=sum(r['visibility']['best_oracle_gain']+1e-9<r['centroid']['best_oracle_gain'] for r in comparable)
    report=dict(planned_snapshots=len(cases)*len(OFFSETS),ready=len(comparable),improved=improved,worse=worse,
                unchanged=len(comparable)-improved-worse,all_goals_safe=all(r[s]['all_safe'] for r in comparable for s in ('centroid','visibility')),
                both_no_goals=sum(not r['centroid']['goals'] and not r['visibility']['goals'] for r in comparable),
                skipped=[{k:r[k] for k in ('case','offset_s','status')} for r in rows if 'status' in r and r['status']!='ready'],
                failures=[r for r in rows if 'error' in r],counterfactual_one_step_only=True,
                map_health='capture issues retained; not certified healthy',no_truth_inputs=True)
    (root/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__': main()
