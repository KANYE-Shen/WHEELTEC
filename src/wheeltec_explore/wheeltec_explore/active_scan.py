"""Conservative active-observation policy. Only estimated occupancy is an input."""
from dataclasses import dataclass
import math


def rotation_clearance(grid, pose, radius):
    """Prove the full circular envelope free, for every rotation angle.

    A cell is included if its closed square could intersect the disc. The extra
    half-diagonal is conservative for arbitrary map origins and rotations.
    """
    if not math.isfinite(radius) or radius <= 0 or not all(math.isfinite(x) for x in pose):
        raise ValueError('Finite pose and positive rotation envelope required')
    cx, cy = grid.world_to_cell(*pose[:2])
    padding = grid.resolution / math.sqrt(2)
    reach = math.ceil((radius+padding)/grid.resolution)+1
    checked = 0
    for y in range(cy-reach, cy+reach+1):
        for x in range(cx-reach, cx+reach+1):
            wx, wy = grid.cell_to_world(x,y)
            if math.hypot(wx-pose[0],wy-pose[1]) > radius+padding:
                continue
            checked += 1
            if not (0 <= x < grid.width and 0 <= y < grid.height):
                return dict(safe=False,reason='sweep_outside_map',checked_cells=checked,blocking_cell=[x,y])
            value = grid.value(x,y)
            if value != 0:
                return dict(safe=False,reason='unknown_swept_space' if value < 0 else 'occupied_or_uncertain_swept_space',
                            checked_cells=checked,blocking_cell=[x,y])
    return dict(safe=True,reason='known_free_full_rotation_envelope',checked_cells=checked)


def _angle_delta(a,b):
    return math.atan2(math.sin(a-b),math.cos(a-b))


def choose_scan(grid, pose, radius, angle_deg, fov_deg, horizon=2., *, assume_start_safe=False):
    """Choose one finite rotation by newly exposed unknown-ray directions.

    This predicts opportunity, never map completion or physical resolution.
    """
    if not 0 < angle_deg <= 360 or not 0 < fov_deg <= 360 or horizon <= 0:
        raise ValueError('Invalid observation angle/FOV/horizon')
    if assume_start_safe:
        if not math.isfinite(radius) or radius <= 0 or not all(math.isfinite(x) for x in pose):
            raise ValueError('Finite pose and positive radius required')
        # User-declared simulation initial condition, never measured free space.
        return dict(safe=True, reason='initial_rotation_assumed_safe',
                    clearance_source='assumed_start', clearance_proven=False,
                    checked_cells=0, angle_rad=2*math.pi, expected_new_directions=None)
    report=rotation_clearance(grid,pose,radius)
    report.update(clearance_source='estimated_map',clearance_proven=report['safe'])
    report.update(angle_rad=None,expected_new_directions=0)
    if not report['safe']:
        return report
    missing=[]
    half=math.radians(fov_deg)/2
    for beam in range(72):
        angle=2*math.pi*beam/72
        if abs(_angle_delta(angle,pose[2])) <= half:
            continue
        for step in range(1,math.ceil(horizon/(grid.resolution/2))+1):
            distance=step*grid.resolution/2
            x,y=grid.world_to_cell(pose[0]+distance*math.cos(angle),pose[1]+distance*math.sin(angle))
            if not (0 <= x < grid.width and 0 <= y < grid.height):
                break
            value=grid.value(x,y)
            if value < 0:
                missing.append(angle)
                break
            if value >= 50:
                break
    best=(0,0.)
    angle=math.radians(angle_deg)
    steps=max(1,math.ceil(angle_deg/10))
    for signed in (angle,-angle):
        headings=[pose[2]+signed*i/steps for i in range(1,steps+1)]
        gain=sum(any(abs(_angle_delta(direction,heading)) <= half for heading in headings)
                 for direction in missing)
        if gain > best[0]:
            best=(gain,signed)
    if best[0]:
        report.update(angle_rad=best[1],expected_new_directions=best[0],reason='new_direction_opportunity')
    else:
        report['reason']='no_expected_gain'
    return report


@dataclass
class ScanBudget:
    maximum: int
    used: int = 0

    def __post_init__(self):
        if self.maximum < 0:
            raise ValueError('Nonnegative observation budget required')

    def take(self):
        if self.used >= self.maximum:
            return False
        self.used += 1
        return True


def simulation_observation_allowed(use_sim_time, localhost_only, board_model):
    return bool(use_sim_time and localhost_only == '1' and not board_model.strip('\x00\n '))


def startup_assumption_allowed(initial, enabled, previous_scans, navigation_goals):
    """One startup-only exception; runtime additionally enforces simulation isolation."""
    return bool(initial and enabled and not previous_scans and not navigation_goals)
