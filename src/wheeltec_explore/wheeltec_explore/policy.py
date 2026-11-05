"""Task outcome and retry bookkeeping independent of ROS and scene geometry."""
import math
from .defaults import DEFAULTS


class RetryBook:
    def __init__(self, cooldown=DEFAULTS['retry_cooldown'],max_attempts=DEFAULTS['max_attempts'],radius=DEFAULTS['retry_radius']):
        self.cooldown, self.max_attempts, self.radius = cooldown, max_attempts, radius
        self.entries = []

    def _entry(self, point):
        return next((e for e in self.entries if math.dist(e['point'], point) <= self.radius), None)

    def failed(self, point, now):
        entry = self._entry(point)
        if entry is None:
            entry = {'point': point, 'attempts': 0, 'until': now}
            self.entries.append(entry)
        entry['attempts'] += 1
        entry['until'] = now+self.cooldown

    def available(self, point, now):
        entry = self._entry(point)
        return entry is None or (now >= entry['until'] and entry['attempts'] < self.max_attempts)

    def exhausted(self, point):
        entry = self._entry(point)
        return entry is not None and entry['attempts'] >= self.max_attempts


def local_known_ratio(grid, center, radius):
    """Known cells in a fixed metric disk, including occupied but not out-of-map.

    The denominator includes the WHOLE disk: clipping it to the map would make
    a poorly observed map edge look complete. This is observation, not clearance.
    """
    cx, cy = grid.world_to_cell(*center)
    extent = math.ceil(radius/grid.resolution)+1
    known = total = 0
    for y in range(cy-extent, cy+extent+1):
        for x in range(cx-extent, cx+extent+1):
            if math.dist(grid.cell_to_world(x,y),center) > radius:
                continue
            total += 1
            if 0 <= x < grid.width and 0 <= y < grid.height and grid.value(x,y) >= 0:
                known += 1
    return known/total if total else 0.


class ObservationProgress:
    """Bound one navigation attempt; local observation never means goal reached."""
    def __init__(self, now, distance, revision, config, position=None):
        self.config = config
        self.progress_at, self.best_distance = now, distance
        self.progress_position = tuple(position) if position is not None else None
        self.revision, self.sufficient_maps = revision, 0

    def update(self, now, distance, revision, ratio, position=None):
        if self.progress_position is not None:
            # Runtime supplies fresh poses: real displacement also counts on a
            # detour. Distance to the goal alone wrongly cancels obstacle bypasses.
            if position is not None and math.dist(self.progress_position,position) >= self.config['goal_progress_distance']:
                self.progress_position, self.progress_at = tuple(position), now
        elif self.best_distance-distance >= self.config['goal_progress_distance']:
            # Preserve distance-only callers; live navigation always supplies pose.
            self.best_distance, self.progress_at = distance, now
        if revision != self.revision:
            self.revision = revision
            if (distance <= self.config['local_observation_distance'] and
                    ratio >= self.config['local_observation_threshold']):
                self.sufficient_maps += 1
            else:
                self.sufficient_maps = 0
        if self.sufficient_maps >= self.config['local_observation_maps']:
            return 'locally_observed'
        if now-self.progress_at >= self.config['goal_no_progress_timeout']:
            return 'goal_no_progress'
        return None


def completion_state(known_free_area, unreachable_clusters, unresolved_failures,
                     map_saved, returned, minimum_area=DEFAULTS['minimum_free_area'], residual_clusters=0):
    if not map_saved or not returned:
        return 'failed'
    if known_free_area < minimum_area or unreachable_clusters or unresolved_failures:
        return 'incomplete'
    return 'completed_with_residual_frontiers' if residual_clusters else 'completed'

def observation_fresh(last_received, now, max_age=5.0):
    return last_received is not None and 0 <= now-last_received <= max_age
