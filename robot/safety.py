"""Fail-closed command policy. Time is the local steady clock, not ROS time."""
import math
class MotionGate:
    def __init__(self,command_timeout,heartbeat_timeout,linear_limit,yaw_limit):
        if not all(math.isfinite(x) and x>0 for x in (command_timeout,heartbeat_timeout,linear_limit,yaw_limit)):
            raise ValueError('positive finite safety limits required')
        self.command_timeout=command_timeout; self.heartbeat_timeout=heartbeat_timeout
        self.limits=(linear_limit,yaw_limit); self.last_command=self.last_heartbeat=None
        self.target=(0.,0.); self.armed=False; self.estop=False; self.reason='boot_hold'; self.last_now=None
        self.timeout_detail=None
    def stop(self,reason): self.armed=False; self.target=(0.,0.); self.reason=reason
    def emergency(self,asserted):
        self.estop=bool(asserted)
        if self.estop: self.stop('emergency_stop')
    def heartbeat(self,now):
        if math.isfinite(now): self.last_heartbeat=now
    def command(self,command,now):
        if not math.isfinite(now) or len(command)!=2 or not all(math.isfinite(x) for x in command):
            self.stop('invalid_command'); return
        self.last_command=now
        self.target=tuple(max(-limit,min(limit,float(x))) for x,limit in zip(command,self.limits))
    def fresh(self,now):
        return (self.last_command is not None and 0<=now-self.last_command<=self.command_timeout
                and self.last_heartbeat is not None and 0<=now-self.last_heartbeat<=self.heartbeat_timeout)
    def arm(self,now):
        if self.estop or not self.fresh(now) or self.target!=(0.,0.): return False
        self.armed=True; self.reason='armed'; self.last_now=now; self.timeout_detail=None; return True
    def status(self,now):
        return {'armed':self.armed,'reason':self.reason,
                'command_age_s':None if self.last_command is None else now-self.last_command,
                'operator_age_s':None if self.last_heartbeat is None else now-self.last_heartbeat,
                'timeout_detail':self.timeout_detail}
    def output(self,now):
        if not math.isfinite(now) or (self.last_now is not None and now<self.last_now): self.stop('clock_invalid')
        self.last_now=now
        if self.estop: self.stop('emergency_stop')
        if self.armed and not self.fresh(now):
            ages=self.status(now)
            self.timeout_detail={'command_age_s':ages['command_age_s'],
                                 'operator_age_s':ages['operator_age_s'],
                                 'expired':[name for name,age,limit in (
                                     ('command',ages['command_age_s'],self.command_timeout),
                                     ('operator',ages['operator_age_s'],self.heartbeat_timeout))
                                     if age is None or not 0<=age<=limit]}
            self.stop('command_or_operator_timeout')
        return self.target if self.armed else (0.,0.)


class CommandSelector:
    """Select one velocity source; manual release/expiry never resumes autonomy."""
    def __init__(self, timeout, linear_limit=.1, yaw_limit=.3):
        if not all(math.isfinite(x) and x > 0 for x in (linear_limit, yaw_limit)):
            raise ValueError('Positive speed limits required')
        self.limits = (linear_limit, yaw_limit)
        self.gear = 1
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Positive source timeout required')
        self.timeout = timeout
        self.mode = 'hold'
        self.latest = {}

    def set_gear(self, gear):
        if type(gear) is not int or gear not in (0, 1, 2):
            raise ValueError('Gear must be 0, 1 or 2')
        self.gear = gear

    def select(self, mode):
        self.latest.clear()
        self.mode = mode if mode in ('hold', 'manual', 'autonomy') else 'hold'
        if mode != self.mode:
            raise ValueError('Unknown command source')

    def command(self, source, value, now):
        if (source not in ('manual', 'autonomy') or len(value) != 2
                or not math.isfinite(now) or not all(math.isfinite(x) for x in value)):
            self.select('hold')
            return
        self.latest[source] = (tuple(value), now)

    def output(self, now):
        if not math.isfinite(now):
            self.select('hold')
            return (0., 0.)
        value, stamp = self.latest.get(self.mode, ((0., 0.), None))
        if stamp is None:
            return (0., 0.)
        if now < stamp:
            self.select('hold')
            return (0., 0.)
        if now - stamp >= self.timeout:
            if self.mode == 'manual':
                self.select('hold')
            return (0., 0.)
        ratio = (.3, .6, 1.)[self.gear]
        return tuple(max(-limit*ratio, min(limit*ratio, x)) for x, limit in zip(value, self.limits))


class StatusCadence:
    """Bound repeated telemetry while reporting each state transition immediately."""
    def __init__(self, interval):
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError('Positive status interval required')
        self.interval=interval;self.last_time=None;self.last_state=None

    def due(self, state, now):
        if (self.last_time is None or state != self.last_state
                or now < self.last_time or now-self.last_time >= self.interval-1e-9):
            self.last_time=now;self.last_state=state
            return True
        return False
