"""Render source-backed synthetic comparisons; never a Gazebo screenshot."""
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'simulation'))
from irregular_fixtures import LAYOUTS,fixture,frontier_cells,ray_clear_oracle
RUN=Path.home()/'wheeltec_sim_ws/data/runs/20261027-irregular-mechanism-v1'
rows=json.loads((RUN/'rows.json').read_text())
fig,axes=plt.subplots(2,4,figsize=(14,7.5),layout='constrained')
for col,layout in enumerate(LAYOUTS):
    grid,robot=fixture(layout,0,0)
    fs=frontier_cells(grid)
    row=next(x for x in rows if x['layout']==layout and x['spawn']==0 and x['seed']==0)
    image=np.asarray(grid.data).reshape(grid.height,grid.width)
    image=np.where(image<0,1,np.where(image>25,2,0))
    for rank,strategy in enumerate(('centroid','visibility')):
        ax=axes[rank,col]
        ax.imshow(image,origin='lower',extent=(0,5,0,5),cmap=ListedColormap(['#f2f5fa','#9aa7b9','#182536']),vmin=0,vmax=2)
        goal=row[strategy]['goals'][0];a=grid.world_to_cell(goal['x'],goal['y'])
        visible=[p for p in fs if ray_clear_oracle(grid,a,p)]
        occluded=[p for p in fs if p not in set(visible)]
        for values,color in ((occluded,'#d8793c'),(visible,'#1baf85')):
            if values:
                points=np.array([grid.cell_to_world(*p) for p in values])
                ax.scatter(*points.T,s=5,color=color,zorder=3)
        ax.plot(robot[0],robot[1],'o',color='#3376bd',ms=5)
        ax.plot(goal['x'],goal['y'],'*',color='#dc3156',ms=13)
        ax.arrow(goal['x'],goal['y'],.25*np.cos(goal['yaw']),.25*np.sin(goal['yaw']),width=.016,color='#dc3156',zorder=4)
        ax.set_title(f"{layout} / {strategy}\nvisible {len(visible)}/{len(fs)}; gain {goal['oracle_gain']:.1f}",fontsize=10)
        ax.set_aspect('equal');ax.set_xticks([0,2.5,5]);ax.set_yticks([0,2.5,5]);ax.set_xlabel('m')
fig.legend(handles=[Line2D([],[],marker='o',ls='',color=c,label=l) for c,l in [('#3376bd','Robot start'),('#dc3156','Selected goal'),('#1baf85','Visible frontier'),('#d8793c','Occluded frontier')]],loc='lower center',bbox_to_anchor=(.5,-.03),ncol=4,frameon=False)
fig.suptitle('Synthetic 25 m² snapshots (seed 0, start 0) - geometry only, not closed-loop acceptance',fontsize=13)
fig.savefig(Path(__file__).with_name('viewpoint-comparison.png'),dpi=160,bbox_inches='tight')
fig.savefig(Path(__file__).with_name('viewpoint-comparison.svg'),bbox_inches='tight')

svg=Path(__file__).with_name("viewpoint-comparison.svg")
svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines())+"\n")
