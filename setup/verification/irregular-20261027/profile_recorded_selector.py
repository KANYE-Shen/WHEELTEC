"""Isolated selector timing on failed real ROS snapshot; not online scheduling proof."""
import hashlib,json,statistics,time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src/wheeltec_explore'))
from wheeltec_explore.frontiers import Grid,select_frontiers
RUN=Path.home()/'wheeltec_sim_ws/data/runs/20261027-irregular-nominal-v1/019_irregular_frame_seed4_visibility'
d=json.loads((RUN/'process.json').read_text())
frames=[f for f in d['frames'] if f.get('map') is not None and f.get('pose') is not None]
f=min(frames,key=lambda f:abs(f['t']-4.001));g=d['maps'][f['map']]
grid=Grid(g['width'],g['height'],g['resolution'],*g['origin'],g['data'])
rows=[]
for i in range(5):
    for strategy in ('centroid','visibility') if i%2==0 else ('visibility','centroid'):
        t=time.perf_counter();result=select_frontiers(grid,f['pose'][:2],frontier_viewpoint_strategy=strategy)
        rows.append(dict(repeat=i,strategy=strategy,wall_seconds=time.perf_counter()-t,goals=len(result.goals)))
r=dict(run=str(RUN),snapshot_t=f['t'],map_index=f['map'],width=grid.width,height=grid.height,rows=rows,
    source_sha256=hashlib.sha256((ROOT/'src/wheeltec_explore/wheeltec_explore/viewpoints.py').read_bytes()).hexdigest(),
    limitations='Idle isolated four-core affinity; not exact decision trace or concurrent SLAM/Nav2 runtime')
Path(__file__).with_name('recorded-selector-profile.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({s:dict(median=statistics.median(v['wall_seconds'] for v in rows if v['strategy']==s),maximum=max(v['wall_seconds'] for v in rows if v['strategy']==s)) for s in ('centroid','visibility')},indent=2))
