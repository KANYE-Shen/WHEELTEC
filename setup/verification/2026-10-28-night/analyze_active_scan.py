"""Offline diagnostic only: saved estimated maps, never an explorer input."""
from pathlib import Path
import sys,json,math,statistics
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
root=Path('/mnt/d/虚拟c盘/WHEELTEC')
sys.path.insert(0,str(root/'src/wheeltec_explore'))
from wheeltec_explore.frontiers import Grid
base=Path('/home/wheeltec/wheeltec_sim_ws/data/runs/20261028-active-scan-ab-v1')
out=root/'setup/verification/2026-10-28-night'
summary=json.loads((base/'summary.json').read_text())
rows=[];sample=None
for row in summary['rows']:
 run=Path(row['run_dir'])
 data=json.loads((run/'process.json').read_text())
 own=json.loads((run/'map.exploration.json').read_text()) if (run/'map.exploration.json').is_file() else {}
 events=own.get('active_scans',[])
 event=events[0] if events else None
 frames=[f for f in data['frames'] if f.get('pose') is not None and f.get('map') is not None and (not event or f['t']<=event['started_ros'])]
 frame=frames[-1] if frames else None
 counts=Counter();unknown=[]
 if frame:
  m=data['maps'][frame['map']]
  g=Grid(m['width'],m['height'],m['resolution'],*m['origin'],m['data'])
  pose=frame['pose'];cx,cy=g.world_to_cell(*pose[:2])
  pad=g.resolution/math.sqrt(2);reach=math.ceil((.35+pad)/g.resolution)+1
  for y in range(cy-reach,cy+reach+1):
   for x in range(cx-reach,cx+reach+1):
    wx,wy=g.cell_to_world(x,y)
    if math.hypot(wx-pose[0],wy-pose[1])<=.35+pad:
     k='outside' if not(0<=x<g.width and 0<=y<g.height) else 'unknown' if g.value(x,y)<0 else 'free' if g.value(x,y)==0 else 'occupied_or_uncertain'
     counts[k]+=1
     if k=='unknown':unknown.append((wx,wy))
  if event and sample is None:sample=(g,pose,unknown)
 r=json.loads((run/'result.json').read_text())
 rows.append(dict(scenario=row['scenario'],seed=row['seed'],angle=row['angle'],
  original_success=row['success'],wire_terminal_received=bool(row.get('state')),
  artifact_state=own.get('state'),artifact_reason=own.get('reason'),
  legal_goals=len(own.get('goals',[])),motion_requested=any(e.get('motion_requested') for e in events),
  plan_reason=event['plan']['reason'] if event else None,
  nearby_estimated_map_cells=dict(counts),saved_map_metrics=r.get('saved_map_metrics',{}),
  health=own.get('map_health'),truth_quality=r.get('truth_quality'),
  trajectory_safety=r.get('trajectory_safety'),error=r.get('error')))
report=dict(source='Offline diagnostics, not rescoring or explorer input',rows=rows,
 attempts=len(rows),strict_successes=sum(r['original_success'] for r in rows),
 wire_terminal_missing=sum(not r['wire_terminal_received'] for r in rows),
 artifact_states=dict(Counter(r['artifact_state'] for r in rows)),
 artifact_reasons=dict(Counter(r['artifact_reason'] for r in rows)),
 motion_requests=sum(r['motion_requested'] for r in rows),
 first_goals=sum(r['legal_goals']>0 for r in rows))
(out/'active-scan-v1-diagnostic.json').write_text(json.dumps(report,indent=2)+'\n')
g,pose,unknown=sample
fig,axes=plt.subplots(1,2,figsize=(10,4),dpi=160)
a=np.array(g.data).reshape(g.height,g.width)
a=np.where(a<0,0,np.where(a==0,1,2))
for i,ax in enumerate(axes):
 ax.imshow(a,origin='lower',extent=(g.origin_x,g.origin_x+g.width*g.resolution,g.origin_y,g.origin_y+g.height*g.resolution),vmin=0,vmax=2,cmap=ListedColormap(['#b6c0cb','#ffffff','#202936']),interpolation='nearest')
 ax.add_patch(plt.Circle(pose[:2],.35,fill=False,color='#d43d51',lw=1.8))
 ax.plot(pose[0],pose[1],'o',color='#1c90ad',ms=4)
 ax.set_aspect('equal');ax.set_xlabel('Estimated map x (m)');ax.set_ylabel('Estimated map y (m)')
 if i:
  ax.set_xlim(pose[0]-.6,pose[0]+.6);ax.set_ylim(pose[1]-.6,pose[1]+.6)
  if unknown:ax.scatter(*zip(*unknown),marker='x',s=16,color='#e04357',label='Unknown cells intersect envelope')
  ax.legend(fontsize=6,loc='upper left')
axes[0].set_title('Saved SLAM occupancy (not ground truth)')
axes[1].set_title('0.35 m conservative rotation envelope')
fig.tight_layout();fig.savefig(out/'estimated-sweep-refusal.png');plt.close(fig)
print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))

