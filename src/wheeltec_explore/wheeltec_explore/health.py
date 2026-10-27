"""ROS-independent, estimate-only map/stream health; faults are never truth-driven."""
import math
from .defaults import DEFAULTS


class MapUnstableError(RuntimeError):
    pass


class MapHealth:
    def __init__(self, jump_translation=DEFAULTS['map_jump_translation'],
                 jump_rotation=DEFAULTS['map_jump_rotation'],map_timeout=DEFAULTS['map_update_timeout'],
                 scan_timeout=DEFAULTS['scan_max_age'],tf_timeout=DEFAULTS['tf_max_age'],
                 future_tolerance=DEFAULTS['future_tolerance'],require_slam_alive=True,
                 tf_future_offset=DEFAULTS['slam_transform_timeout']):
        self.limits=dict(jump_translation=jump_translation,jump_rotation=jump_rotation,
                         map_timeout=map_timeout,scan_timeout=scan_timeout,
                         tf_timeout=tf_timeout,future_tolerance=future_tolerance,tf_future_offset=tf_future_offset)
        if any(not math.isfinite(v) or v <= 0 for v in self.limits.values()):
            raise ValueError('Health limits must be positive and finite')
        self.require_slam_alive=require_slam_alive
        self.streams={}
        self.previous_transform=None
        self.slam_alive=None
        self.last_now=None
        self.faults={}
        self.max_translation_jump=0.
        self.max_rotation_jump=0.

    def _stream(self, name, stamp, received):
        previous=self.streams.get(name)
        allowance=self.limits['future_tolerance']+(self.limits['tf_future_offset'] if name=='tf' else 0.)
        if not math.isfinite(stamp) or stamp <= 0 or stamp > received+allowance:
            self.faults[name+'_stamp_invalid']={'stamp':stamp,'received':received}
            return
        if previous and stamp < previous[0]:
            self.faults[name+'_stamp_backwards']={'previous':previous[0],'stamp':stamp}
        if previous is None or stamp > previous[0]:
            self.streams[name]=(stamp,received)

    def map(self, stamp, received): self._stream('map',stamp,received)
    def scan(self, stamp, received): self._stream('scan',stamp,received)
    def slam(self, alive): self.slam_alive=alive

    def transform(self, stamp, received, pose):
        if not all(math.isfinite(v) for v in pose):
            self.faults['nonfinite_transform']={'stamp':stamp}
            return
        previous=self.previous_transform
        if previous and stamp > previous[0]:
            delta=math.dist(pose[:2],previous[1][:2])
            angle=abs(math.atan2(math.sin(pose[2]-previous[1][2]),math.cos(pose[2]-previous[1][2])))
            self.max_translation_jump=max(self.max_translation_jump,delta)
            self.max_rotation_jump=max(self.max_rotation_jump,angle)
            for key,value,limit in (('map_to_odom_translation_jump',delta,'jump_translation'),
                                    ('map_to_odom_rotation_jump',angle,'jump_rotation')):
                if value > self.limits[limit]:
                    self.faults.setdefault(key,{'stamp':stamp,'magnitude':value,'limit':self.limits[limit]})
        self._stream('tf',stamp,received)
        if previous is None or stamp > previous[0]: self.previous_transform=(stamp,pose)

    def snapshot(self, now):
        if self.last_now is not None and now < self.last_now:
            self.faults.setdefault('ros_time_moved_backwards',{'previous':self.last_now,'now':now})
        self.last_now=now
        issues=list(self.faults)
        ages={}
        for name in ('map','scan','tf'):
            item=self.streams.get(name)
            if item is None:
                issues.append(name+'_missing')
                continue
            stamp,received=item
            ages[name]={'stamp_age_s':now-stamp,'update_age_s':now-received}
            # Map header may describe an older scan; update gaps use distinct map
            # arrivals. Scan/TF need both source and arrival freshness.
            age=now-received if name=='map' else max(now-stamp,now-received)
            if age > self.limits[name+'_timeout']:
                issues.append('map_update_timeout' if name=='map' else name+'_stale')
        if self.require_slam_alive and self.slam_alive is not True:
            issues.append('slam_not_alive')
        return dict(healthy=not issues,issues=sorted(set(issues)),ages=ages,
                    faults=self.faults.copy(),limits=self.limits.copy(),
                    max_translation_jump_m=self.max_translation_jump,
                    max_rotation_jump_rad=self.max_rotation_jump,
                    slam_alive=self.slam_alive,
                    slam_liveness_verified=self.require_slam_alive)
