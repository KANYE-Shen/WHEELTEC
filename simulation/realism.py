"""Seeded sensor/odometry/actuator errors and generated simulation assets.

No model here reads /simulation/ground_truth or evaluator geometry. Numeric
parameters retain provenance; this profile is NOT a real-robot calibration.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import yaml
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
DEFAULT_PROFILE=ROOT/'config/realism.yaml'


def records(parameters, prefix=''):
    for key,entry in parameters.items():
        name=prefix+key
        if 'value' in entry:
            yield name,entry
        else:
            yield from records(entry,name+'.')


def value(profile, name):
    part=profile['parameters']
    for key in name.split('.'): part=part[key]
    return part['value']


def validate_profile(profile):
    for name,entry in records(profile['parameters']):
        source=entry.get('source'); v=entry['value']
        if source not in ('measured','assumed') or not entry.get('basis'):
            raise ValueError('Missing provenance: '+name)
        if source=='measured' and not entry.get('evidence'):
            raise ValueError('Measured parameter requires evidence: '+name)
        if isinstance(v,(float,int)) and not isinstance(v,bool):
            if not math.isfinite(v): raise ValueError('Nonfinite parameter: '+name)
            if source=='assumed':
                interval=entry.get('interval')
                if not interval or len(interval)!=2 or not interval[0] <= v <= interval[1]:
                    raise ValueError('Assumed number requires containing interval: '+name)
    if not 0 < value(profile,'laser.fov_deg') <= 360: raise ValueError('Invalid laser FOV')
    if not 0 <= value(profile,'laser.dropout_probability') <= 1: raise ValueError('Invalid dropout')
    if value(profile,'laser.range_max_m') <= value(profile,'laser.range_min_m'): raise ValueError('Invalid laser range')
    for key in ('geometry.length_m','geometry.width_m','geometry.wheel_radius_m',
                'geometry.wheel_separation_m','laser.frequency_hz','laser.beams',
                'actuator.linear_accel_m_s2','actuator.linear_decel_m_s2',
                'actuator.yaw_accel_rad_s2','actuator.yaw_decel_rad_s2'):
        if value(profile,key) <= 0: raise ValueError('Positive parameter required: '+key)
    if value(profile,'actuator.delay_min_s') > value(profile,'actuator.delay_max_s'):
        raise ValueError('Reversed actuator delay range')
    return profile


def load_profile(path=DEFAULT_PROFILE):
    return validate_profile(yaml.safe_load(Path(path).read_text(encoding='utf-8-sig')))


def generate_profile(calibration, output):
    calibration=Path(calibration)
    profile=json.loads(calibration.read_text(encoding='utf-8-sig'))
    profile['calibration_source']=str(calibration)
    profile['calibration_sha256']=hashlib.sha256(calibration.read_bytes()).hexdigest()
    validate_profile(profile)
    Path(output).write_text(yaml.safe_dump(profile,sort_keys=False,allow_unicode=True),encoding='utf-8')
    return profile


class ErrorModel:
    def __init__(self, profile, seed, scale, stream):
        if not math.isfinite(scale) or scale < 0: raise ValueError('Invalid noise scale')
        self.profile=validate_profile(profile); self.scale=scale
        self.rng=np.random.default_rng(np.random.SeedSequence([int(seed),stream]))
    def p(self, name): return value(self.profile,name)


class ScanModel(ErrorModel):
    def __init__(self, profile, seed, scale):
        super().__init__(profile,seed,scale,1); self.last_stamp=None
    def apply(self, ranges, stamp, minimum, maximum):
        a=np.asarray(ranges,dtype=float).copy()
        valid=np.isfinite(a)&(a>=minimum)&(a<=maximum)
        a[~valid]=np.inf
        if self.scale:
            a[valid]+=self.rng.normal(0,self.p('laser.noise_sigma_m')*self.scale,int(valid.sum()))
            drop=self.rng.random(len(a)) < min(1,self.p('laser.dropout_probability')*self.scale)
            a[drop|~np.isfinite(a)|(a<minimum)|(a>maximum)]=np.inf
            stamp+=float(self.rng.normal(0,self.p('laser.timestamp_jitter_s')*self.scale))
        if self.last_stamp is not None: stamp=max(stamp,self.last_stamp+1e-9)
        self.last_stamp=stamp
        return a.tolist(),stamp


class OdomModel(ErrorModel):
    def __init__(self, profile, seed, scale):
        super().__init__(profile,seed,scale,2)
        self.previous=None; self.estimated=None; self.bias=np.zeros(2)
        self.variance=np.zeros(3)
    def update(self, raw, stamp):
        raw=np.asarray(raw,dtype=float)
        if not np.isfinite(raw).all() or not math.isfinite(stamp): return None
        if self.previous is None:
            self.previous=(raw.copy(),stamp); self.estimated=raw.copy()
            return {'pose':self.estimated.tolist(),'twist':[0.,0.],'variance':[0.,0.,0.]}
        previous,last_stamp=self.previous; dt=stamp-last_stamp
        if dt <= 0: return None
        delta=raw-previous
        delta[2]=math.atan2(math.sin(delta[2]),math.cos(delta[2]))
        c,s=math.cos(previous[2]),math.sin(previous[2])
        longitudinal=c*delta[0]+s*delta[1]
        lateral=-s*delta[0]+c*delta[1]
        separation=self.p('geometry.wheel_separation_m')
        dl=longitudinal-delta[2]*separation/2
        dr=longitudinal+delta[2]*separation/2
        radius_error=self.p('odom.wheel_radius_scale_error')*self.scale
        asymmetry=self.p('odom.left_right_scale_error')*self.scale
        dl*=1+radius_error-asymmetry/2; dr*=1+radius_error+asymmetry/2
        ds=(dl+dr)/2
        da=(dr-dl)/(separation*(1+self.p('odom.wheel_separation_scale_error')*self.scale))
        white=np.array([self.p('odom.linear_white_sigma_m_s'),self.p('odom.yaw_white_sigma_rad_s')])*self.scale
        walk=np.array([self.p('odom.linear_walk_sigma'),self.p('odom.yaw_walk_sigma')])*self.scale
        self.bias+=self.rng.normal(0,walk*math.sqrt(dt))
        disturbance=(self.bias+self.rng.normal(0,white))*dt
        ds+=disturbance[0]; da+=disturbance[1]
        lateral+=float(self.rng.normal(0,self.p('odom.turn_slip_sigma_m_rad')*self.scale*abs(delta[2])))
        c,s=math.cos(self.estimated[2]),math.sin(self.estimated[2])
        self.estimated+=np.array([c*ds-s*lateral,s*ds+c*lateral,da])
        self.previous=(raw.copy(),stamp)
        self.variance+=np.array([(white[0]*dt)**2,(white[0]*dt)**2,(white[1]*dt)**2])
        return {'pose':self.estimated.tolist(),'twist':[ds/dt,da/dt],
                'variance':self.variance.tolist()}


class ActuatorModel(ErrorModel):
    def __init__(self, profile, seed, scale):
        super().__init__(profile,seed,scale,3)
        self.pending=[]; self.last_received=None; self.last_update=None
        self.output=np.zeros(2); self.target=np.zeros(2)
    def submit(self, command, now):
        if not math.isfinite(now) or not all(math.isfinite(x) for x in command): return
        delay=float(self.rng.uniform(self.p('actuator.delay_min_s'),self.p('actuator.delay_max_s')))*self.scale
        release=max(now+delay,self.pending[-1][0]+1e-9 if self.pending else now)
        self.pending.append((release,np.array(command,dtype=float)))
        self.last_received=now
        if self.last_update is None: self.last_update=now
    def update(self, now):
        if self.last_update is None: self.last_update=now
        dt=max(0,now-self.last_update); self.last_update=now
        if self.last_received is None or now-self.last_received>self.p('actuator.command_timeout_s'):
            # Fail closed: expired buffered commands must never restart motion.
            self.pending.clear(); self.target=np.zeros(2)
        while self.pending and self.pending[0][0] <= now:
            _,self.target=self.pending.pop(0)
        limits=np.array([self.p('actuator.max_linear_m_s'),self.p('actuator.max_yaw_rad_s')])
        target=np.clip(self.target,-limits,limits)
        dead=np.array([self.p('actuator.linear_deadzone_m_s'),self.p('actuator.yaw_deadzone_rad_s')])*self.scale
        target[np.abs(target)<dead]=0
        accelerating=(target*self.output>=0)&(np.abs(target)>np.abs(self.output))
        accel=np.array([self.p('actuator.linear_accel_m_s2'),self.p('actuator.yaw_accel_rad_s2')])
        decel=np.array([self.p('actuator.linear_decel_m_s2'),self.p('actuator.yaw_decel_rad_s2')])
        step=np.where(accelerating,accel,decel)*dt
        self.output+=np.clip(target-self.output,-step,step)
        return tuple(float(v) for v in self.output)


def prepare_assets(world_path, directory, profile, seed, scale):
    validate_profile(profile)
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=False)
    p=lambda name:value(profile,name)
    model_tree=ET.parse(ROOT/'models/wheeltec_reference/model.sdf')
    model=model_tree.getroot().find('model')
    length,width=p('geometry.length_m'),p('geometry.width_m')
    for size in model.findall("link[@name='base_link']/*/geometry/box/size"):
        # The short front marker remains cosmetic; update only the body boxes.
        if size.text=='0.36 0.28 0.12': size.text=f'{length} {width} 0.12'
    for side,sign in (('left',1),('right',-1)):
        link=model.find(f"link[@name='{side}_wheel']")
        radius=p('geometry.wheel_radius_m')
        link.find('pose').text=f'0 {sign*p("geometry.wheel_separation_m")/2} {radius} 0 0 0'
        for element in link.findall('.//cylinder/radius'): element.text=str(radius)
    lidar=model.find("link[@name='base_link']/sensor/lidar")
    horizontal=lidar.find('scan/horizontal')
    half=math.radians(p('laser.fov_deg'))/2
    horizontal.find('samples').text=str(int(p('laser.beams')))
    horizontal.find('min_angle').text=str(-half); horizontal.find('max_angle').text=str(half)
    lidar.find('range/min').text=str(p('laser.range_min_m'))
    lidar.find('range/max').text=str(p('laser.range_max_m'))
    sensor=model.find("link[@name='base_link']/sensor")
    sensor.find('update_rate').text=str(p('laser.frequency_hz'))
    sensor.find('topic').text='/simulation/raw_scan'
    plugin=model.find("plugin[@name='gz::sim::systems::DiffDrive']")
    for name,text in {'topic':'/simulation/actuator_cmd_vel','odom_topic':'/simulation/raw_odom',
                      'tf_topic':'/simulation/raw_tf','wheel_radius':str(p('geometry.wheel_radius_m')),
                      'wheel_separation':str(p('geometry.wheel_separation_m'))}.items():
        plugin.find(name).text=text
    model_path=directory/'model.sdf'; model_tree.write(model_path,encoding='utf-8',xml_declaration=True)
    world_tree=ET.parse(world_path); world=world_tree.getroot().find('world')
    include=world.find('include'); instance=copy.deepcopy(model)
    ET.SubElement(instance,'pose').text=include.findtext('pose','0 0 0 0 0 0')
    world.remove(include); world.append(instance)
    world_path=directory/'world.sdf'; world_tree.write(world_path,encoding='utf-8',xml_declaration=True)
    bridge=yaml.safe_load((ROOT/'config/bridge.yaml').read_text())
    output=[]
    for entry in bridge:
        entry=entry.copy(); topic=entry['ros_topic_name']
        if topic=='/tf': continue
        for old,new in (('/scan','/simulation/raw_scan'),('/odom','/simulation/raw_odom'),('/cmd_vel','/simulation/actuator_cmd_vel')):
            if topic==old: entry['ros_topic_name']=entry['gz_topic_name']=new
        output.append(entry)
    bridge_path=directory/'bridge.yaml'; bridge_path.write_text(yaml.safe_dump(output,sort_keys=False))
    nav=yaml.safe_load((ROOT/'config/nav2.yaml').read_text())
    footprint=json.dumps([[length/2,width/2],[length/2,-width/2],[-length/2,-width/2],[-length/2,width/2]])
    for name in ('local_costmap','global_costmap'):
        nav[name][name]['ros__parameters']['footprint']=footprint
    for node,key in (('amcl','laser_max_range'),): nav[node]['ros__parameters'][key]=float(p('laser.range_max_m'))
    for name in ('local_costmap','global_costmap'):
        scan=nav[name][name]['ros__parameters']['obstacle_layer']['scan']
        scan.update(raytrace_max_range=p('laser.range_max_m')-.1,obstacle_max_range=p('laser.range_max_m')-.5)
    nav_path=directory/'nav2.yaml'; nav_path.write_text(yaml.safe_dump(nav,sort_keys=False))
    slam=yaml.safe_load((ROOT/'config/slam.yaml').read_text())
    slam['slam_toolbox']['ros__parameters']['max_laser_range']=float(p('laser.range_max_m'))
    slam_path=directory/'slam.yaml'; slam_path.write_text(yaml.safe_dump(slam,sort_keys=False))
    radius=math.hypot(length,width)/2+p('geometry.safety_margin_m')
    result={'world':str(world_path),'model':str(model_path),'bridge':str(bridge_path),
            'nav2':str(nav_path),'slam':str(slam_path),'robot_radius':radius,'seed':int(seed),'noise_scale':scale,
            'calibration_complete':profile.get('calibration_complete',False),'profile':profile,
            'native_noise':False,'randomness':'postprocessing streams seeded; native physics scheduling not controlled'}
    (directory/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
