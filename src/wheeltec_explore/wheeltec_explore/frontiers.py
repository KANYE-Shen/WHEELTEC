"""Occupancy-grid frontiers and safe approach goals, independent of ROS."""
from .defaults import DEFAULTS
from .viewpoints import choose_viewpoint
from collections import deque
from dataclasses import dataclass, field
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

    def neighbors(self, cell, diagonal=False):
        x, y = cell
        offsets = [(-1,0),(1,0),(0,-1),(0,1)]
        if diagonal:
            offsets += [(-1,-1),(-1,1),(1,-1),(1,1)]
        for dx, dy in offsets:
            nx, ny = x+dx, y+dy
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
    residual_counts: dict = field(default_factory=dict)
    residual_frontiers: list = field(default_factory=list)
    viewpoint_diagnostics: list = field(default_factory=list)


def select_frontiers(grid: Grid, robot: Tuple[float, float], robot_radius=DEFAULTS['robot_radius'],
                     min_frontier_size=DEFAULTS['min_frontier_size'],
                     min_goal_distance=DEFAULTS['min_goal_distance'],visited=(),observations=(),
                     visited_radius=DEFAULTS['visited_radius'],
                     observation_min_separation=DEFAULTS['observation_min_separation'],
                     frontier_approach_radius=DEFAULTS['frontier_approach_radius'],
                     start_snap_distance=DEFAULTS['start_snap_distance'],
                     distance_score_bias=DEFAULTS['distance_score_bias'],
                     score_distance_offset=DEFAULTS['score_distance_offset'],
                     frontier_viewpoint_strategy=DEFAULTS['frontier_viewpoint_strategy'],
                     viewpoint_candidate_budget=DEFAULTS['viewpoint_candidate_budget'],
                     viewpoint_frontier_budget=DEFAULTS['viewpoint_frontier_budget']) -> FrontierResult:
    """Return frontier approach cells reachable through inflated known-free space.

    A frontier is a known-free cell beside unknown space. Unknown cells are never
    navigation targets or traversed by the reachability search. The whole robot
    footprint must fit in observed free cells. Four-connected
    travel deliberately refuses diagonal shortcuts through occupied corners.
    Frontier clustering uses eight neighbours to retain slanted visible edges.
    """
    if frontier_viewpoint_strategy not in ('centroid','visibility'):
        raise ValueError('unknown frontier viewpoint strategy')
    if viewpoint_candidate_budget<1 or viewpoint_frontier_budget<1:
        raise ValueError('positive viewpoint budgets required')
    viewpoint_diagnostics = []
    free = {(i % grid.width, i // grid.width) for i, v in enumerate(grid.data) if 0 <= v <= 25}
    unsafe = [(i % grid.width, i // grid.width) for i, v in enumerate(grid.data) if not 0 <= v <= 25]
    occupied = [(i % grid.width, i // grid.width) for i, v in enumerate(grid.data) if v > 25]
    residual_counts = {'reachable_unexplored': 0, 'footprint_excluded': 0,
                       'multiview_observed': 0}
    residual_frontiers = []
    radius = math.ceil(robot_radius / grid.resolution)
    offsets = [(dx,dy) for dy in range(-radius,radius+1) for dx in range(-radius,radius+1)
               if math.hypot(dx,dy)*grid.resolution <= robot_radius+grid.resolution*0.5]
    blocked = {(x+dx,y+dy) for x,y in unsafe for dx,dy in offsets}
    # Diagnostics only: optimistic clearance ignores unknown, never used as a goal.
    solid_blocked = {(x+dx,y+dy) for x,y in occupied for dx,dy in offsets}

    def visible(a, b):
        # Sample at half-cell spacing. Unknown cannot support a visibility claim.
        ax, ay = grid.world_to_cell(a[0], a[1])
        steps = max(1, math.ceil(math.hypot(b[0]-ax,b[1]-ay)*2))
        for i in range(steps+1):
            x, y = round(ax+(b[0]-ax)*i/steps), round(ay+(b[1]-ay)*i/steps)
            if (x,y) not in free:
                return False
        return True

    def multiview(cluster, approaches):
        # Old proximity bookkeeping, or two messages from one map/view, is insufficient.
        if not approaches or not all(any(math.dist(grid.cell_to_world(*p),v) < visited_radius
                                        for v in visited) for p in approaches):
            return False
        views = [o for o in observations if len(o) == 3
                 and grid.world_to_cell(o[0],o[1]) in free]
        for a in views:
            for b in views:
                if a[2] != b[2] and math.dist(a[:2], b[:2]) >= observation_min_separation:
                    if all(visible(a,p) and visible(b,p) for p in cluster):
                        return True
        return False

    def residual(cluster, kind, approaches):
        residual_counts[kind] += 1
        residual_frontiers.append({'classification':kind, 'frontier_cells':len(cluster),
                                   'centroid':list(grid.cell_to_world(
                                       sum(p[0] for p in cluster)/len(cluster),
                                       sum(p[1] for p in cluster)/len(cluster))),
                                   'reachable_approach_cells':len(approaches)})
    # A center is safe only when the full reference footprint is observed free.
    # Treat the map extent as unknown even if its last raster cell says free.
    safe = {p for p in free-blocked if min((p[0]+0.5)*grid.resolution,
            (p[1]+0.5)*grid.resolution,(grid.width-p[0]-0.5)*grid.resolution,
            (grid.height-p[1]-0.5)*grid.resolution) >= robot_radius}
    start = grid.world_to_cell(*robot)
    if start not in safe:
        # Quantization can put a valid footprint center one cell into inflation.
        nearby = [p for p in safe if math.hypot(p[0]-start[0], p[1]-start[1])*grid.resolution <= start_snap_distance]
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
    approach_radius = max(frontier_approach_radius, robot_radius+2*grid.resolution)
    approach_cells = math.ceil(approach_radius/grid.resolution)
    approach_offsets = [(dx,dy) for dy in range(-approach_cells,approach_cells+1)
                        for dx in range(-approach_cells,approach_cells+1)
                        if math.hypot(dx,dy)*grid.resolution <= approach_radius]
    while frontiers:
        seed = min(frontiers)
        frontiers.remove(seed)
        cluster, queue = [seed], deque([seed])
        while queue:
            for nxt in grid.neighbors(queue.popleft(), diagonal=True):
                if nxt in frontiers:
                    frontiers.remove(nxt)
                    cluster.append(nxt)
                    queue.append(nxt)
        if len(cluster)*grid.resolution < min_frontier_size:
            small += 1
            continue
        total += 1
        neighborhood = {(x+dx,y+dy) for x,y in cluster for dx,dy in approach_offsets}
        candidates = neighborhood.intersection(distances)
        if not candidates:
            # Exclusion requires measured solids to block EVERY possible center
            # nearby, even if unknown cells are optimistically allowed as centers.
            optimistic = {p for p in neighborhood if 0 <= p[0] < grid.width
                          and 0 <= p[1] < grid.height and p not in solid_blocked}
            kind = 'reachable_unexplored' if optimistic else 'footprint_excluded'
            residual(cluster,kind,candidates)
            unreachable += int(kind == 'reachable_unexplored')
            continue
        approaches = candidates.copy()
        # Prefer an interior approach near the frontier center, then short travel.
        cx = sum(p[0] for p in cluster)/len(cluster)
        cy = sum(p[1] for p in cluster)/len(cluster)
        candidates = [p for p in candidates if math.dist(grid.cell_to_world(*p),robot) >= min_goal_distance
                      and all(math.dist(grid.cell_to_world(*p),v) >= visited_radius for v in visited)]
        if not candidates:
            kind = 'multiview_observed' if multiview(cluster, approaches) else 'reachable_unexplored'
            residual(cluster,kind,approaches)
            unreachable += int(kind == 'reachable_unexplored')
            continue
        goal = min(candidates, key=lambda p: math.hypot(p[0]-cx,p[1]-cy) + distance_score_bias*distances[p])
        visible_size = len(cluster)
        if frontier_viewpoint_strategy == 'visibility':
            selected,diagnostics = choose_viewpoint(candidates,cluster,free,distances,
                grid.resolution,score_distance_offset,distance_score_bias,
                viewpoint_candidate_budget,viewpoint_frontier_budget)
            viewpoint_diagnostics.append(diagnostics)
            if selected is None:
                residual(cluster,'reachable_unexplored',approaches)
                unreachable += 1
                continue
            goal,aim,visible_size = selected
            fx,fy = grid.cell_to_world(*aim)
        else:
            fx,fy = grid.cell_to_world(cx,cy)
        x, y = grid.cell_to_world(*goal)
        distance = distances[goal]*grid.resolution
        score = visible_size*grid.resolution / (score_distance_offset+distance)
        goals.append(FrontierGoal(x, y, math.atan2(fy-y,fx-x), distance, len(cluster), score))
    goals.sort(key=lambda g: (-g.score,g.distance,g.x,g.y))
    return FrontierResult(goals, len(free)*grid.resolution**2, total, unreachable, small, residual_counts, residual_frontiers, viewpoint_diagnostics)