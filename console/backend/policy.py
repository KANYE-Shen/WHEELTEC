"""Independent control lease; polling never renews motion authority."""
import base64
import hashlib
import math
from urllib.parse import urlsplit
from console.settings import CONTROL


def fingerprint(key):
    return 'SHA256:'+base64.b64encode(hashlib.sha256(key).digest()).decode().rstrip('=')


def check_origin(origin, host):
    try:
        u = urlsplit(origin or '')
        return u.scheme == 'http' and u.netloc == host and u.hostname in ('127.0.0.1', 'localhost') and not u.path
    except ValueError:
        return False


class Lease:
    def __init__(self, timeout=None):
        self.timeout = CONTROL['command_timeout_s'] if timeout is None else timeout
        self.owner = None
        self.deadline = 0.
        self.target = (0., 0.)
        self.reason = 'boot_hold'

    def release(self, reason='operator_hold'):
        self.owner = None
        self.target = (0., 0.)
        self.reason = reason
        self.deadline = 0.

    def output(self, now):
        if self.owner and now >= self.deadline:
            self.release('operator_timeout')
        return self.target if self.owner else (0., 0.)

    def claim(self, owner, now):
        self.output(now)
        if self.owner and self.owner != owner:
            raise ValueError('Control held by another operator')
        self.owner = owner
        self.target = (0., 0.)
        self.deadline = now+self.timeout
        self.reason = 'manual_zero'

    def command(self, owner, v, w, now):
        self.output(now)
        if not self.owner or self.owner != owner:
            raise ValueError('No active control lease; claim again')
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (v, w)):
            self.release('invalid_command')
            raise ValueError('Finite velocity required')
        self.target = (max(-CONTROL['max_linear_m_s'], min(CONTROL['max_linear_m_s'], v)),
                       max(-CONTROL['max_yaw_rad_s'], min(CONTROL['max_yaw_rad_s'], w)))
        self.deadline = now+self.timeout
        self.reason = 'manual'


def simulation_authorized(environment, machine):
    return machine in ('x86_64', 'AMD64') and environment.get('WSL_DISTRO_NAME') == 'WHEELTEC-Ubuntu-22.04' and environment.get('ROS_LOCALHOST_ONLY') == '1'


class ArmHandshake:
    """Await the final gate acknowledgment; never automatically recover a lost arm."""

    def __init__(self):
        self.state = 'idle'
        self.deadline = 0.

    @property
    def ready(self): return self.state == 'active'
    @property
    def pending(self): return self.state == 'pending'
    def start(self, now): self.state = 'pending'; self.deadline = now+1.
    def reset(self): self.state = 'idle'

    def observe(self, armed, now):
        if self.state == 'pending':
            if now >= self.deadline:
                self.state = 'watchdog_arm_failed'
            elif armed:
                self.state = 'active'
        elif self.state == 'active' and not armed:
            self.state = 'final_watchdog_hold'
        return self.state if self.state in ('watchdog_arm_failed', 'final_watchdog_hold') else None
