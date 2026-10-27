"""Explain every negative one-step replay; does not tune or mutate the selector."""
import argparse,hashlib,json,math
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'simulation'))
from replay_viewpoints import snapshot
from irregular_fixtures import ray_clear_oracle,frontier_cells
from wheeltec_explore.frontiers import select_frontiers
from wheeltec_explore.viewpoints import choose_viewpoint
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--export-fixture',action='store_true')
args=parser.parse_args()
RUN=Path.home()/'wheeltec_sim_ws/data/runs/20261027-irregular-replay-v1'
rows=json.loads((RUN/'rows.json').read_text())
cases=json.loads((ROOT/'setup/verification/unknown_rooms/matrix.json').read_text())['cases']
paths={x['case']:Path(x['result']).parent/'process.json' for x in cases}
report=[]
for row in rows:
    if row.get('status')!='ready' or not row['visibility']['best_oracle_gain']+1e-9<row['centroid']['best_oracle_gain']:continue
    grid,frame=snapshot(json.loads(paths[row['case']].read_text()),row['offset_s'])[0]
    fs=frontier_cells(grid);clusters=[]
    def audit(candidates,cluster,free,distances,resolution,offset,bias,cb,fb):
        selected,diag=choose_viewpoint(candidates,cluster,free,distances,resolution,offset,bias,cb,fb)
        cx=sum(p[0] for p in cluster)/len(cluster);cy=sum(p[1] for p in cluster)/len(cluster)
        baseline=min(candidates,key=lambda p:math.hypot(p[0]-cx,p[1]-cy)+bias*distances[p])
        def metric(cell):
            return dict(cell=cell,local_visible=sum(ray_clear_oracle(grid,cell,p) for p in cluster),
                global_visible=sum(ray_clear_oracle(grid,cell,p) for p in fs),distance_m=distances[cell]*resolution)
        item=dict(cluster_size=len(cluster),diagnostics=diag,centroid=metric(baseline),visibility=metric(selected[0]) if selected else None)
        for key in ('centroid','visibility'):
            if item[key] is not None:item[key]['local_gain']=item[key]['local_visible']/(offset+item[key]['distance_m'])
        if args.export_fixture and selected is None and row['case']=='baseline-spawn0':
            points=[*candidates,*cluster]
            x0=max(0,min(p[0] for p in points)-1);y0=max(0,min(p[1] for p in points)-1)
            x1=min(grid.width,max(p[0] for p in points)+2);y1=min(grid.height,max(p[1] for p in points)+2)
            origin=grid.cell_to_world(x0-.5,y0-.5)
            data=dict(source_kind='recorded_ros_occupancy_crop_not_truth',case=row['case'],offset_s=row['offset_s'],
                process_sha256=hashlib.sha256(paths[row['case']].read_bytes()).hexdigest(),
                map_index=frame['map'],frame_t=frame['t'],width=x1-x0,height=y1-y0,resolution=grid.resolution,
                origin=[*origin,grid.origin_yaw],data=[grid.value(x,y) for y in range(y0,y1) for x in range(x0,x1)],
                candidates=[[p[0]-x0,p[1]-y0,distances[p]] for p in candidates],
                cluster=[[p[0]-x0,p[1]-y0] for p in cluster])
            target=ROOT/'src/wheeltec_explore/test/fixtures/recorded_occluded_frontier.json'
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(data,indent=2)+'\n')
        clusters.append(item);return selected,diag
    with patch('wheeltec_explore.frontiers.choose_viewpoint',side_effect=audit):
        select_frontiers(grid,frame['pose'][:2],frontier_viewpoint_strategy='visibility')
    report.append(dict(case=row['case'],offset=row['offset_s'],clusters=clusters))
Path(__file__).with_name('replay-regression-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps([dict(case=r['case'],offset=r['offset'],clusters=len(r['clusters']),
    local_gain_reduced=sum(c['visibility'] is not None and c['visibility']['local_gain']+1e-9<c['centroid']['local_gain'] for c in r['clusters']),
    new_no_sampled_visible=sum(c['visibility'] is None for c in r['clusters'])) for r in report],indent=2))
