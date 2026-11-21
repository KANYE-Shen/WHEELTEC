"""Clearance and independent map census for an exploration task."""
from .defaults import DEFAULTS
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


@dataclass
class FrontierCensus:
    approaches: List[Tuple[float, float]]
    known_free_area: float
    frontier_clusters: int
    unreachable_clusters: int
    ignored_small_clusters: int
    residual_counts: dict = field(default_factory=dict)
    residual_frontiers: list = field(default_factory=list)


def _bounded_dilate(points, offsets, width, height):
    """Inflate grid cells exactly, retaining only coordinates inside the grid.

    Each integer represents one row of cells. The original unbounded inflation
    is only queried at in-grid free cells, so clipping does not alter clearance.
    """
    if not points or not offsets:
        return set()
    rows = [0] * height
    for x, y in points:
        rows[y] |= 1 << x
    inflated = [0] * height
    mask = (1 << width) - 1
    for dx, dy in offsets:
        if abs(dx) >= width:
            continue
        for y in range(max(0, -dy), min(height, height-dy)):
            bits = rows[y]
            if bits:
                inflated[y+dy] |= (bits << dx if dx >= 0 else bits >> -dx) & mask
    cells = set()
    for y, bits in enumerate(inflated):
        while bits:
            bit = bits & -bits
            cells.add((bit.bit_length()-1, y))
            bits ^= bit
    return cells



def reachable_free_space(grid, robot, robot_radius, start_snap_distance):
    """Return free cells, inflation offsets and reachable safe cells for this grid."""
    free = {(i % grid.width, i // grid.width) for i, v in enumerate(grid.data) if 0 <= v <= 25}
    unsafe = [(i % grid.width, i // grid.width) for i, v in enumerate(grid.data) if not 0 <= v <= 25]
    radius = math.ceil(robot_radius / grid.resolution)
    offsets = [(dx,dy) for dy in range(-radius,radius+1) for dx in range(-radius,radius+1)
               if math.hypot(dx,dy)*grid.resolution <= robot_radius+grid.resolution*0.5]
    blocked = _bounded_dilate(unsafe, offsets, grid.width, grid.height)
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
    return free, offsets, distances


def census_frontiers(grid: Grid, robot: Tuple[float, float], robot_radius=DEFAULTS['robot_radius'],
                     min_frontier_size=DEFAULTS['min_frontier_size'],
                     min_goal_distance=DEFAULTS['min_goal_distance'],visited=(),observations=(),
                     visited_radius=DEFAULTS['visited_radius'],
                     observation_min_separation=DEFAULTS['observation_min_separation'],
                     frontier_approach_radius=DEFAULTS['frontier_approach_radius'],
                     start_snap_distance=DEFAULTS['start_snap_distance'],
                     footprint_exclusion_radius=DEFAULTS['footprint_exclusion_radius']) -> FrontierCensus:
    """Collect residual evidence and possible approach positions for exhaustion checks.

    A frontier is a known-free cell beside unknown space. Unknown cells are never
    navigation targets or traversed by the reachability search. The whole robot
    footprint must fit in observed free cells. Four-connected
    travel deliberately refuses diagonal shortcuts through occupied corners.
    Frontier clustering uses eight neighbours to retain slanted visible edges.
    """
    if not math.isfinite(footprint_exclusion_radius) or not 0 <= footprint_exclusion_radius <= robot_radius:
        raise ValueError('Exclusion proof radius must be within the planning radius')
    free, offsets, distances = reachable_free_space(grid, robot, robot_radius, start_snap_distance)
    occupied = [(i % grid.width, i // grid.width) for i, v in enumerate(grid.data) if v > 25]
    residual_counts = {'reachable_unexplored': 0, 'footprint_excluded': 0,
                       'multiview_observed': 0}
    residual_frontiers = []
    # Diagnostics only: optimistic clearance ignores unknown, never used as a goal.
    # More conservative navigation clearance does NOT prove physical exclusion.
    # Live launch explicitly retains the old calibrated reference for this proof;
    # existing callers omitting the new argument keep their original meaning.
    proof_radius = footprint_exclusion_radius or robot_radius
    extent = math.ceil(proof_radius/grid.resolution)
    proof_offsets = (offsets if proof_radius == robot_radius else
        [(dx,dy) for dy in range(-extent,extent+1) for dx in range(-extent,extent+1)
         if math.hypot(dx,dy)*grid.resolution <= proof_radius+grid.resolution*0.5])
    solid_blocked = {(x+dx,y+dy) for x,y in occupied for dx,dy in proof_offsets}

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
    frontiers = {p for p in free if any(grid.value(*n) < 0 for n in grid.neighbors(p))}
    eligible_positions = set()
    total, unreachable, small = 0, 0, 0
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
        positions = [grid.cell_to_world(*cell) for cell in candidates]
        eligible = {position for position in positions
                    if math.dist(position, robot) >= min_goal_distance
                    and all(math.dist(position, v) >= visited_radius for v in visited)}
        if not eligible:
            kind = 'multiview_observed' if multiview(cluster, candidates) else 'reachable_unexplored'
            residual(cluster,kind,candidates)
            unreachable += int(kind == 'reachable_unexplored')
            continue
        eligible_positions.update(eligible)
    return FrontierCensus(sorted(eligible_positions), len(free)*grid.resolution**2,
                          total, unreachable, small, residual_counts, residual_frontiers)
