from pathlib import Path
import sys,json,math
import numpy as np,yaml
sys.path.insert(0,'/mnt/d/虚拟c盘/WHEELTEC/simulation')
from map_metrics import reference_footprint
run=Path('/home/wheeltec/wheeltec_sim_ws/data/runs/20261028-active-scan-ab-v3/000_irregular_arc_seed0_angle0')
manifest=json.loads((run/'realism/manifest.json').read_text())
parts=reference_footprint(run/'realism/model.sdf')
model_max=max(float(np.linalg.norm(p,axis=1).max()) for p in parts)
nav=yaml.safe_load((run/'realism/nav2.yaml').read_text())
points=json.loads(nav['local_costmap']['local_costmap']['ros__parameters']['footprint'])
nav_max=max(math.hypot(*p) for p in points)
radius=manifest['robot_radius']
result={'scope':'Offline static geometry audit, not truth-fed control or real chassis measurement',
        'model_projection_max_radius_m':model_max,'nav2_footprint_max_radius_m':nav_max,
        'active_scan_radius_m':radius,'sdf_contained':model_max<=radius,'nav2_contained':nav_max<=radius,
        'margin_from_nav2_m':radius-nav_max,'measured_real_robot_geometry':False}
assert result['sdf_contained'] and result['nav2_contained']
out=Path('/mnt/d/虚拟c盘/WHEELTEC/setup/verification/2026-10-28-night/rotation-envelope-audit.json')
out.write_text(json.dumps(result,indent=2)+'\n');print(out.read_text())

