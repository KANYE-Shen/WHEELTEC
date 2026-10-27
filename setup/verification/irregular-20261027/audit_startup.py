"""Independent known-free footprint audit of retained on-trial snapshots."""
import hashlib,json,math
from pathlib import Path
import sys
import numpy as np
from scipy.ndimage import distance_transform_edt
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src/wheeltec_explore'))
from wheeltec_explore.frontiers import Grid
RUN=Path.home()/'wheeltec_sim_ws/data/runs/20261027-irregular-gazebo-v2'
rows=[]
for path in sorted(RUN.glob('*/process.json')):
    document=json.loads(path.read_text())
    frames=[f for f in document['frames'] if f.get('pose') is not None and f.get('map') is not None
            and f.get('pose_age_s') is not None and 0<=f['pose_age_s']<=1.]
    for label,frame in [('first_fresh',frames[0]),('last_fresh',frames[-1])] if frames else []:
        d=document['maps'][frame['map']];grid=Grid(d['width'],d['height'],d['resolution'],*d['origin'],d['data'])
        data=np.asarray(d['data']).reshape(grid.height,grid.width)
        yy,xx=np.indices(data.shape)
        border=np.minimum.reduce([xx+.5,yy+.5,grid.width-xx-.5,grid.height-yy-.5])*grid.resolution
        safe=(distance_transform_edt((data>=0)&(data<=25))*grid.resolution>.35+grid.resolution*.5)&(border>=.35)
        robot=grid.world_to_cell(*frame['pose'][:2]);ys,xs=np.nonzero(safe)
        nearest=float(np.hypot(xs-robot[0],ys-robot[1]).min()*grid.resolution) if len(xs) else None
        rows.append(dict(run=path.parent.name,snapshot=label,t=frame['t'],safe_cells=int(safe.sum()),
                         robot_cell=robot,nearest_safe_center_from_robot_cell_m=nearest,
                         no_safe_start_with_original_snap=nearest is None or nearest>.15,
                         process_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
report=dict(trials=len(list(RUN.glob('*/result.json'))),snapshots=len(rows),rows=rows,
    all_audited_starts_blocked=all(r['no_safe_start_with_original_snap'] for r in rows),
    minimum_nearest_safe_m=min(r['nearest_safe_center_from_robot_cell_m'] for r in rows if r['nearest_safe_center_from_robot_cell_m'] is not None),
    maximum_nearest_safe_m=max(r['nearest_safe_center_from_robot_cell_m'] for r in rows if r['nearest_safe_center_from_robot_cell_m'] is not None),
    note='First and last fresh recorded snapshots, not a replacement for unavailable decision-time trace')
Path(__file__).with_name('startup-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
