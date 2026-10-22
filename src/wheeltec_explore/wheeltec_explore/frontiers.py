"""Occupancy-grid frontiers and safe approach goals, independent of ROS."""
from collections import deque
from dataclasses import dataclass
import math
from typing import List, Sequence, Tuple


@dataclass
class Grid:
    width: int
    height: int
    resolution: float
    origin_x: float
    origin_y: float
    origin_yaw: float
    data: Sequence[int]

    def __post_init__(self):
        if (self.width <= 0 or self.height <= 0 or self.resolution <= 0
                or len(self.data) != self.width * self.height):
            raise ValueError('Invalid occupancy grid dimensions or resolution')

    def value(self, x, y):
        return self.data[y * self.width + x]

    def world_to_cell(self, x, y):
        dx, dy = x-self.origin_x, y-self.origin_y
        c, s = math.cos(self.origin_yaw), math.sin(self.origin_yaw)
        return (math.floor((c*dx+s*dy)/self.resolution),
                math.floor((-s*dx+c*dy)/self.resolution))

    def cell_to_world(self, x, y):
        lx, ly = (x+0.5)*self.resolution, (y+0.5)*self.resolution
        c, s = math.cos(self.origin_yaw), math.sin(self.origin_yaw)
        return self.origin_x+c*lx-s*ly, self.origin_y+s*lx+c*ly

    def neighbors(self, cell):
        x, y = cell
        for nx, ny in ((x-1,y), (x+1,y), (x,y-1), (x,y+1)):
            if 0 <= nx < self.width and 0 <= ny < self.height:
                yield nx, ny


@dataclass(frozen=True)
class FrontierGoal:
    x: float
    y: float
    yaw: float
    distance: float
    frontier_size: int
    score: float


@dataclass
class FrontierResult:
    goals: List[FrontierGoal]
    known_free_area: float
    frontier_clusters: int
    unreachable_clusters: int
    ignored_small_clusters: int


def select_frontiers(grid: Grid, robot: Tuple[float, float], robot_radius=0.35,
                     min_frontier_size=0.25, min_goal_distance=0.2, visited=()) -> FrontierResult:
    """Return frontier approach cells reachable through inflated known-free space.

    A frontier is a known-free cell beside unknown space. Unknown cells are never
    navigation targets or traversed by the reachability search. The whole robot
    footprint must fit in observed free cells. Four-connected
    travel deliberately refuses diagonal shortcuts through occupied corners.
    """
    free = {(i % grid.width, i // grid.width) for i, v in enumerate(grid.data) if 0 <= v <= 25}
    unsafe = [(i % grid.width, i // grid.width) for i, v in enumerate(grid.data) if not 0 <= v <= 25]
    radius = math.ceil(robot_radius / grid.resolution)
    offsets = [(dx,dy) for dy in range(-radius,radius+1) for dx in range(-radius,radius+1)
               if math.hypot(dx,dy)*grid.resolution <= robot_radius+grid.resolution*0.5]
    blocked = {(x+dx,y+dy) for x,y in unsafe for dx,dy in offsets}
    # A center is safe only when the full reference footprint is observed free.
    # Treat the map extent as unknown even if its last raster cell says free.
    safe = {p for p in free-blocked if min((p[0]+0.5)*grid.resolution,
            (p[1]+0.5)*grid.resolution,(grid.width-p[0]-0.5)*grid.resolution,
            (grid.height-p[1]-0.5)*grid.resolution) >= robot_radius}
    start = grid.world_to_cell(*robot)
    if start not in safe:
        # Quantization can put a valid footprint center one cell into inflation.
        nearby = [p for p in safe if math.hypot(p[0]-start[0], p[1]-start[1])*grid.resolution <= 0.15]
        start = min(nearby, key=lambda p: math.hypot(p[0]-start[0],p[1]-start[1])) if nearby else None
    distances = {}
    if start is not None:
        distances[start] = 0
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for nxt in grid.neighbors(current):
                if nxt in safe and nxt not in distances:
                    distances[nxt] = distances[current]+1
                    queue.append(nxt)
    frontiers = {p for p in free if any(grid.value(*n) < 0 for n in grid.neighbors(p))}
    goals, total, unreachable, small = [], 0, 0, 0
    approach_radius = max(0.6, robot_radius+2*grid.resolution)
    approach_cells = math.ceil(approach_radius/grid.resolution)
    approach_offsets = [(dx,dy) for dy in range(-approach_cells,approach_cells+1)
                        for dx in range(-approach_cells,approach_cells+1)
                        if math.hypot(dx,dy)*grid.resolution <= approach_radius]
    while frontiers:
        seed = min(frontiers)
        frontiers.remove(seed)
        cluster, queue = [seed], deque([seed])
        while queue:
            for nxt in grid.neighbors(queue.popleft()):
                if nxt in frontiers:
                    frontiers.remove(nxt)
                    cluster.append(nxt)
                    queue.append(nxt)
        if len(cluster)*grid.resolution < min_frontier_size:
            small += 1
            continue
        total += 1
        candidates = {(x+dx,y+dy) for x,y in cluster for dx,dy in approach_offsets}
        candidates.intersection_update(distances)
        if not candidates:
            unreachable += 1
            continue
        # Prefer an interior approach near the frontier center, then short travel.
        cx = sum(p[0] for p in cluster)/len(cluster)
        cy = sum(p[1] for p in cluster)/len(cluster)
        candidates = [p for p in candidates if math.dist(grid.cell_to_world(*p),robot) >= min_goal_distance
                      and all(math.dist(grid.cell_to_world(*p),v) >= 0.30 for v in visited)]
        if not candidates:
            # No unvisited approach remains; retain it as unresolved instead of looping.
            unreachable += 1
            continue
        goal = min(candidates, key=lambda p: math.hypot(p[0]-cx,p[1]-cy) + 0.1*distances[p])
        x, y = grid.cell_to_world(*goal)
        fx, fy = grid.cell_to_world(cx,cy)
        distance = distances[goal]*grid.resolution
        score = len(cluster)*grid.resolution / (0.5+distance)
        goals.append(FrontierGoal(x, y, math.atan2(fy-y,fx-x), distance, len(cluster), score))
    goals.sort(key=lambda g: (-g.score,g.distance,g.x,g.y))
    return FrontierResult(goals, len(free)*grid.resolution**2, total, unreachable, small)