"""Fail-closed command policy. Time is the local steady clock, not ROS time."""
import math
class MotionGate:
    def __init__(self,command_timeout,heartbeat_timeout,linear_limit,yaw_limit):
        if not all(math.isfinite(x) and x>0 for x in (command_timeout,heartbeat_timeout,linear_limit,yaw_limit)):
            raise ValueError('positive finite safety limits required')
        self.command_timeout=command_timeout; self.heartbeat_timeout=heartbeat_timeout
        self.limits=(linear_limit,yaw_limit); self.last_command=self.last_heartbeat=None
        self.target=(0.,0.); self.armed=False; self.estop=False; self.reason='boot_hold'; self.last_now=None
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
        self.armed=True; self.reason='armed'; self.last_now=now; return True
    def output(self,now):
        if not math.isfinite(now) or (self.last_now is not None and now<self.last_now): self.stop('clock_invalid')
        self.last_now=now
        if self.estop: self.stop('emergency_stop')
        if self.armed and not self.fresh(now): self.stop('command_or_operator_timeout')
        return self.target if self.armed else (0.,0.)
