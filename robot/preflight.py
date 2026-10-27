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


def validate(config,required_gate=1):
    if config.get('hardware_verified') is not True: raise ValueError('G0 hardware is unverified')
    if config.get('measured_kinematics')!='differential': raise ValueError('This launch requires verified differential kinematics; other chassis need a reviewed model')
    for key in ('base_frame','odom_frame','scan_frame','scan_topic','odom_topic','driver_command_topic'):
        if not isinstance(config.get(key),str) or not config[key]: raise ValueError('Missing measured '+key)
    if config.get('driver_command_type')!='geometry_msgs/msg/Twist': raise ValueError('Unverified command type')
    calibration=config.get('calibration_file')
    if not calibration or not Path(calibration).is_file(): raise ValueError('Shared calibration JSON required')
    profile=json.loads(Path(calibration).read_text(encoding='utf-8'))
    calibrated_geometry(profile)
    if required_gate>=3 and (profile.get('calibration_complete') is not True or profile.get('physical_data_collected') is not True):
        raise ValueError('Ground navigation requires completed G0-G2 calibration and physical evidence')
    if config['driver_command_topic'].startswith('/safety/'):
        raise ValueError('Driver output must not loop into the safety chain')
    safety=config['safety']
    for key in ('operator_timeout_s','command_timeout_s','max_linear_m_s','max_yaw_rad_s'):
        v=safety.get(key)
        if not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0: raise ValueError('Explicit safety value required: '+key)
    if safety['max_linear_m_s']>.1: raise ValueError('Initial robot launch speed exceeds 0.1 m/s')
    braking=config.get('measured_braking_distance_m')
    if required_gate>=3 and (not isinstance(braking,(int,float)) or not math.isfinite(braking) or braking<0): raise ValueError('Measured braking distance required')
    if not isinstance(safety.get('obstacle_margin_m'),(int,float)) or not math.isfinite(safety['obstacle_margin_m']) or safety['obstacle_margin_m']<=0: raise ValueError('Positive obstacle margin required')
    timeout=config.get('driver_timeout_verified_s')
    if not isinstance(timeout,(int,float)) or not 0<timeout<=safety['command_timeout_s']: raise ValueError('Driver-level command expiry must be verified')
    record=config.get('approval_record')
    if not record or not Path(record).is_file() or ('通过关卡'+str(required_gate)) not in Path(record).read_text(encoding='utf-8'):
        raise ValueError('Human gate approval record is missing; an agent must never create it')
    return config
