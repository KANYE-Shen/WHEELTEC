"""Validate vendor frontier samples against the current robot-clearance grid."""
import math
from pathlib import Path
from .frontiers import FrontierGoal, reachable_free_space




def validate_vendor_output(output):
    if not output.strip():
        raise ValueError('Vendor task requires a new map output path')
    path = Path(output).expanduser().resolve()
    if path.exists() or any(path.with_suffix(suffix).exists() for suffix in
            ('.yaml','.pgm','.posegraph','.data','.metadata.json','.exploration.json')):
        raise ValueError('Vendor task output already exists; choose a new map path')
    return path


def validate_vendor_geometry(radius, exclusion_radius):
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError('Vendor planning radius must be finite and positive')
    if not math.isfinite(exclusion_radius) or not 0 <= exclusion_radius <= radius:
        raise ValueError('Vendor exclusion radius must be within the planning radius')


def safe_vendor_goals(grid, robot, samples, robot_radius, start_snap_distance,
                      approach_radius, min_goal_distance, visited, visited_radius):
    """Build reachable known-free approach goals; samples are not safety evidence."""
    free, _, distances = reachable_free_space(grid, robot, robot_radius, start_snap_distance)
    goals = []
    extent = math.ceil(approach_radius / grid.resolution)
    for sx, sy in samples:
        if not math.isfinite(sx) or not math.isfinite(sy):
            continue
        cx, cy = grid.world_to_cell(sx, sy)
        if not (0 <= cx < grid.width and 0 <= cy < grid.height):
            continue
        # RRT's x_new can lie inside unknown, rather than on the boundary itself.
        # Confirm an actual free/unknown edge nearby in the current map.
        frontier = {(x, y) for y in range(max(0, cy-extent), min(grid.height, cy+extent+1))
                    for x in range(max(0, cx-extent), min(grid.width, cx+extent+1))
                    if (x, y) in free and math.dist(grid.cell_to_world(x, y), (sx, sy)) <= approach_radius
                    and any(grid.value(*n) < 0 for n in grid.neighbors((x, y)))}
        if not frontier:
            continue
        edge = min(frontier, key=lambda p: math.dist(grid.cell_to_world(*p), (sx, sy)))
        ex, ey = grid.cell_to_world(*edge)
        valid = [p for p in distances if math.dist(grid.cell_to_world(*p), (ex, ey)) <= approach_radius
                 and math.dist(grid.cell_to_world(*p), robot) >= min_goal_distance
                 and all(math.dist(grid.cell_to_world(*p), v) >= visited_radius for v in visited)]
        if not valid:
            continue
        point = min(valid, key=lambda p: (math.dist(grid.cell_to_world(*p), (ex, ey)), distances[p], p))
        x, y = grid.cell_to_world(*point)
        distance = distances[point]*grid.resolution
        goals.append(FrontierGoal(x, y, math.atan2(ey-y, ex-x), distance, 1, -distance))
    return sorted(goals, key=lambda g: (g.distance, g.x, g.y))
