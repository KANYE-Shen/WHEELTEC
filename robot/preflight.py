"""Static admission checks; never creates approvals or accesses a driver."""
import math
import json
from pathlib import Path

def calibrated_geometry(profile):
    geometry=profile['parameters']['geometry']
    for key in ('length_m','width_m'):
        entry=geometry[key]
        if entry.get('source')!='measured' or not entry.get('evidence') or not isinstance(entry.get('value'),(int,float)) or not math.isfinite(entry['value']) or entry['value']<=0:
            raise ValueError('Measured full-body dimensions in shared calibration required')
    length,width=geometry['length_m']['value'],geometry['width_m']['value']
    margin=geometry['safety_margin_m']['value']
    if not math.isfinite(margin) or margin<0: raise ValueError('Invalid shared safety margin')
    polygon=[[length/2,width/2],[length/2,-width/2],[-length/2,-width/2],[-length/2,width/2]]
    return polygon,math.hypot(length,width)/2+margin


def planning_geometry(profile, config):
    """Existing StopZone plus a separate planning margin; physical body is unchanged.

    The circular explorer must clear every corner of the planning polygon at
    every heading. Nav2 uses the same radius; collision_monitor keeps its original
    stop envelope. No braking measurement is manufactured by the fallback.
    """
    body, _ = calibrated_geometry(profile)
    safety = config['safety']
    braking = config.get('measured_braking_distance_m')
    margin = (braking if braking is not None else
              safety['max_linear_m_s']*safety['command_timeout_s'])+safety['obstacle_margin_m']
    x = max(abs(p[0]) for p in body)+margin
    y = max(abs(p[1]) for p in body)+margin
    stop = [[x,y],[x,-y],[-x,-y],[-x,y]]
    extra = profile['parameters']['geometry']['safety_margin_m']['value']
    footprint = [[x+extra,y+extra],[x+extra,-y-extra],
                 [-x-extra,-y-extra],[-x-extra,y+extra]]
    return stop, footprint, math.hypot(x+extra,y+extra)


ADMISSION_PROTOCOL = 'three-stage-20261029'
STAGE_NAMES = {1:'一',2:'二',3:'三'}


def validate(config,required_gate=1):
    if type(required_gate) is not int or required_gate not in STAGE_NAMES:
        raise ValueError('Only stages 1, 2 and 3 exist in the current admission protocol')
    if config.get('admission_protocol') != ADMISSION_PROTOCOL:
        raise ValueError('Explicit three-stage admission protocol required; legacy approvals are not migrated')
    if config.get('hardware_verified') is not True: raise ValueError('Stage-one hardware/interface check is unverified')
    if config.get('measured_kinematics')!='differential': raise ValueError('This launch requires verified differential kinematics; other chassis need a reviewed model')
    for key in ('base_frame','odom_frame','scan_frame','scan_topic','odom_topic','driver_command_topic'):
        if not isinstance(config.get(key),str) or not config[key]: raise ValueError('Missing measured '+key)
    if config.get('driver_command_type')!='geometry_msgs/msg/Twist': raise ValueError('Unverified command type')
    calibration=config.get('calibration_file')
    if not calibration or not Path(calibration).is_file(): raise ValueError('Shared calibration JSON required')
    profile=json.loads(Path(calibration).read_text(encoding='utf-8'))
    calibrated_geometry(profile)
    if required_gate>=2 and (profile.get('calibration_complete') is not True or profile.get('physical_data_collected') is not True):
        raise ValueError('Mapping/navigation requires completed stage-one calibration and physical evidence')
    if config['driver_command_topic'].startswith('/safety/'):
        raise ValueError('Driver output must not loop into the safety chain')
    safety=config['safety']
    for key in ('operator_timeout_s','command_timeout_s','max_linear_m_s','max_yaw_rad_s'):
        v=safety.get(key)
        if not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0: raise ValueError('Explicit safety value required: '+key)
    if safety['max_linear_m_s']>.1: raise ValueError('Initial robot launch speed exceeds 0.1 m/s')
    braking=config.get('measured_braking_distance_m')
    if required_gate>=2 and (not isinstance(braking,(int,float)) or not math.isfinite(braking) or braking<0): raise ValueError('Measured braking distance required')
    if not isinstance(safety.get('obstacle_margin_m'),(int,float)) or not math.isfinite(safety['obstacle_margin_m']) or safety['obstacle_margin_m']<=0: raise ValueError('Positive obstacle margin required')
    timeout=config.get('driver_timeout_verified_s')
    if not isinstance(timeout,(int,float)) or not 0<timeout<=safety['command_timeout_s']: raise ValueError('Driver-level command expiry must be verified')
    record=config.get('approval_record')
    if not record or not Path(record).is_file():
        raise ValueError('Human stage approval record is missing; an agent must never create it')
    lines = {line.strip() for line in Path(record).read_text(encoding='utf-8').splitlines()}
    required = {'流程版本:'+ADMISSION_PROTOCOL,'允许阶段'+STAGE_NAMES[required_gate]+'实测'}
    if not required.issubset(lines):
        raise ValueError('Explicit current-protocol human stage approval is missing')
    return config


def validate_runtime(config, required_gate=1):
    """Explicit supervised use does not certify calibration or measured braking."""
    if config.get('admission_protocol') != 'supervised-live-session-v1':
        return validate(config, required_gate)
    if type(required_gate) is not int or required_gate not in STAGE_NAMES:
        raise ValueError('Invalid runtime stage')
    authorization = config.get('operator_authorization', {})
    scope = 'autonomy' if required_gate == 3 else 'manual'
    if not authorization.get('request') or scope not in authorization.get('scope', []):
        raise ValueError('Explicit operator runtime authorization required')
    if config.get('measured_kinematics') != 'differential':
        raise ValueError('Differential chassis confirmation required')
    for key in ('base_frame','odom_frame','scan_frame','scan_topic','odom_topic','driver_command_topic'):
        if not isinstance(config.get(key),str) or not config[key]:
            raise ValueError('Missing live ROS interface: '+key)
    if config.get('driver_command_type') != 'geometry_msgs/msg/Twist' or config['driver_command_topic'].startswith('/safety/'):
        raise ValueError('Invalid final driver command interface')
    calibration=Path(config.get('calibration_file',''))
    if not calibration.is_file():
        raise ValueError('Reported full-body dimensions required')
    calibrated_geometry(json.loads(calibration.read_text(encoding='utf-8')))
    safety=config.get('safety',{})
    bounds={'max_linear_m_s':.1,'max_yaw_rad_s':.3,'command_timeout_s':.5,'operator_timeout_s':1.,'obstacle_margin_m':.5}
    for key,upper in bounds.items():
        value=safety.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or not 0 < value <= upper:
            raise ValueError('Invalid live safety value: '+key)
    expiry=config.get('driver_command_expiry_s')
    if type(expiry) not in (int,float) or not 0 < expiry <= safety['command_timeout_s']:
        raise ValueError('Driver command expiry required')
    if safety['obstacle_margin_m'] < safety['max_linear_m_s']*safety['command_timeout_s']+.05-1e-9:
        raise ValueError('Live obstacle margin too small')
    return config
