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


def completion_state(known_free_area, unreachable_clusters, unresolved_failures,
                     map_saved, returned, minimum_area=DEFAULTS['minimum_free_area'], residual_clusters=0):
    if not map_saved or not returned:
        return 'failed'
    if known_free_area < minimum_area or unreachable_clusters or unresolved_failures:
        return 'incomplete'
    return 'completed_with_residual_frontiers' if residual_clusters else 'completed'

def observation_fresh(last_received, now, max_age=5.0):
    return last_received is not None and 0 <= now-last_received <= max_age
