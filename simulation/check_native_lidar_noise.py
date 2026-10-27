"""Probe native gpu_lidar noise in installed Fortress/Ogre with a stationary model."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import numpy as np
from check_exploration import stop_owned
ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    os.environ.update(ROS_DOMAIN_ID='85',ROS_LOCALHOST_ONLY='1')
    import rclpy
    from rclpy.parameter import Parameter
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import LaserScan
    report={'render_engine':'ogre','vertical_lines':3,'no_motion_commands':True,
            'real_vehicle_contacted':False,'runs':[]}
    for sigma in (0.,.05):
        folder=args.output/str(sigma); folder.mkdir()
        tree=ET.parse(ROOT/'worlds/room_25m2.sdf'); world=tree.getroot().find('world')
        model=ET.parse(ROOT/'models/wheeltec_reference/model.sdf').getroot().find('model')
        include=world.find('include'); ET.SubElement(model,'pose').text=include.findtext('pose')
        world.remove(include); world.append(model)
        lidar=model.find("link[@name='base_link']/sensor/lidar")
        noise=ET.SubElement(lidar,'noise',type='gaussian')
        ET.SubElement(noise,'mean').text='0'; ET.SubElement(noise,'stddev').text=str(sigma)
        world_path=folder/'world.sdf'; tree.write(world_path,encoding='utf-8',xml_declaration=True)
        log=(folder/'launch.log').open('w')
        process=subprocess.Popen([sys.executable,str(ROOT/'run_room.py'),'world:='+str(world_path),
            'realism:=off','gui:=false','rviz:=false','mode:=interfaces','navigation:=false','ros_domain_id:=85',
            'partition:=wheeltec-noise-'+str(os.getpid())+'-'+str(sigma)],
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        rclpy.init(); node=rclpy.create_node('native_lidar_noise_probe',parameter_overrides=[Parameter('use_sim_time',value=True)])
        samples=[]; stamps=[]
        def receive(message):
            stamp=message.header.stamp.sec+message.header.stamp.nanosec/1e9
            if stamp >= 2:
                samples.append(list(message.ranges)); stamps.append(stamp)
        subscription=node.create_subscription(LaserScan,'/scan',receive,qos_profile_sensor_data)
        error=None
        try:
            deadline=time.monotonic()+60
            while len(samples)<80:
                if process.poll() is not None: raise RuntimeError('Simulation exited')
                if time.monotonic()>deadline: raise RuntimeError('Scan timeout')
                rclpy.spin_once(node,timeout_sec=.05)
        except Exception as exc: error=repr(exc)
        finally:
            node.destroy_node(); rclpy.shutdown(); shutdown=stop_owned(process); log.close()
        a=np.array(samples)
        temporal=None
        if len(a)>2:
            a[~np.isfinite(a)]=np.nan
            temporal=float(np.nanmedian(np.nanstd(a,axis=0)))
        report['runs'].append({'configured_sigma_m':sigma,'median_beam_temporal_sigma_m':temporal,
            'samples':len(samples),'first_stamp':stamps[0] if stamps else None,
            'last_stamp':stamps[-1] if stamps else None,'error':error,'shutdown':shutdown})
    a,b=report['runs']; measured=b['median_beam_temporal_sigma_m']
    report['native_noise_effective']=bool(not a['error'] and not b['error'] and measured is not None
                                         and .025 < measured < .075)
    report['seed_control']='Not exposed by installed ign gazebo CLI; seeded postprocessing remains available'
    (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
