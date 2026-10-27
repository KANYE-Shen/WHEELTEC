"""Synthetic 25 m2 occupancy snapshots, not measured sensors or Gazebo output."""
import math
from pathlib import Path
import random
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/wheeltec_explore'))
from wheeltec_explore.frontiers import Grid

LAYOUTS=('straight','curved_c','wavy_edge','thin_frame')


def fixture(layout,seed=0,spawn=0):
    if layout not in LAYOUTS: raise ValueError('unknown fixture')
    rng=random.Random(seed)
    # One fixed shape per seed, shared by both algorithms. No discarded starts.
    phase=rng.uniform(-.15,.15)
    width=height=100; resolution=.05
    cells=[]
    for iy in range(height):
        for ix in range(width):
            x,y=(ix+.5)*resolution,(iy+.5)*resolution
            occupied=ix in (0,99) or iy in (0,99)
            if layout=='straight':
                unknown=x>3.3+phase
            elif layout=='curved_c':
                angle=math.atan2(y-2.5,x-2.6)
                radius=math.hypot(x-2.6,y-2.5)
                unknown=.65<radius<1.25 and abs(angle)<2.65
                occupied |= .055>abs(radius-1.38) and abs(angle)<2.3
            elif layout=='wavy_edge':
                edge=3.0+.45*math.sin(3.3*y+phase)+.15*math.sin(8*y)
                unknown=x>edge
                occupied |= 2.1<x<2.2 and .8<y<2.8
            else:
                unknown=2.25<x<4.2 and 1.4<y<3.9
                occupied |= (2.0<x<2.1 and 1.25<y<3.15) or (2.0<x<3.6 and 3.1<y<3.2)
            cells.append(100 if occupied else -1 if unknown else 0)
    poses=((.85,.85),(.85,4.1),(1.5,2.45))
    x,y=poses[spawn]
    return Grid(width,height,resolution,0.,0.,0.,cells),(x+rng.uniform(-.03,.03),y+rng.uniform(-.03,.03))


def ray_clear_oracle(grid,a,b):
    """Independent closed-square/segment slab intersection over non-free cells.

    Includes exact corner touches, unlike point sampling. Centers in grid units.
    Used only by tests/evaluation; not imported by the explorer.
    """
    ax,ay=a[0]+.5,a[1]+.5; bx,by=b[0]+.5,b[1]+.5
    for y in range(min(a[1],b[1])-1,max(a[1],b[1])+2):
        for x in range(min(a[0],b[0])-1,max(a[0],b[0])+2):
            if 0<=x<grid.width and 0<=y<grid.height and 0<=grid.value(x,y)<=25: continue
            lo,hi=0.,1.
            for origin,delta,lower in ((ax,bx-ax,x),(ay,by-ay,y)):
                if delta==0:
                    if not lower<=origin<=lower+1: lo,hi=1.,0.;break
                else:
                    t0,t1=(lower-origin)/delta,(lower+1-origin)/delta
                    lo=max(lo,min(t0,t1));hi=min(hi,max(t0,t1))
            if lo<=hi+1e-12: return False
    return True


def frontier_cells(grid):
    return [(x,y) for y in range(grid.height) for x in range(grid.width)
            if 0<=grid.value(x,y)<=25 and any(grid.value(*n)<0 for n in grid.neighbors((x,y)))]
