"""Read-only static laser/odom bag statistics and explicitly scoped gap reports."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics


def scan_statistics(frames,stamps,minimum,maximum):
    if len(frames)!=len(stamps) or len(stamps)<2 or any(not math.isfinite(x) for x in stamps) or any(b<=a for a,b in zip(stamps,stamps[1:])):
        raise ValueError('At least two strictly increasing finite measurement stamps required')
    lengths={len(frame) for frame in frames}
    if len(lengths)!=1 or not next(iter(lengths)): raise ValueError('Changed/empty beam geometry')
    valid=lambda x:math.isfinite(x) and minimum<=x<=maximum
    columns=[[frame[i] for frame in frames if valid(frame[i])] for i in range(len(frames[0]))]
    sigmas=[statistics.stdev(column) for column in columns if len(column)>=3]
    intervals=[b-a for a,b in zip(stamps,stamps[1:])]
    total=sum(map(len,frames)); usable=sum(len(c) for c in columns)
    return {'frames':len(frames),'beams':len(frames[0]),'duration_s':stamps[-1]-stamps[0],
        'invalid_fraction':1-usable/total,'median_temporal_sigma_m':statistics.median(sigmas) if sigmas else None,
        'beams_with_three_valid_samples':len(sigmas),'measurement_hz':(len(stamps)-1)/(stamps[-1]-stamps[0]),
        'interval_std_s':statistics.stdev(intervals) if len(intervals)>1 else None,
        'interval_max_s':max(intervals),'range_min_m':minimum,'range_max_m':maximum}


def motion_drift(odometry,annotations):
    if len(odometry)<2 or any(b[0]<=a[0] for a,b in zip(odometry,odometry[1:])): raise ValueError('Increasing odometry stamps required')
    samples=[]
    for annotation in annotations:
        keys=('start_s','end_s','expected_forward_m','expected_lateral_m','expected_yaw_rad','uncertainty_m','uncertainty_rad')
        if not annotation.get('evidence') or any(not isinstance(annotation.get(k),(int,float)) or not math.isfinite(annotation[k]) for k in keys): raise ValueError('Independent displacement/yaw evidence and uncertainty required')
        if annotation['start_s']>=annotation['end_s'] or min(annotation['uncertainty_m'],annotation['uncertainty_rad'])<0: raise ValueError('Invalid annotated interval/uncertainty')
        start=min(range(len(odometry)),key=lambda i:abs(odometry[i][0]-annotation['start_s']))
        end=min(range(len(odometry)),key=lambda i:abs(odometry[i][0]-annotation['end_s']))
        if end<=start or max(abs(odometry[start][0]-annotation['start_s']),abs(odometry[end][0]-annotation['end_s']))>.1: raise ValueError('Odometry does not bracket annotated endpoints within 0.1s')
        a,b=odometry[start],odometry[end]; dx,dy=b[1]-a[1],b[2]-a[2]
        forward=math.cos(a[3])*dx+math.sin(a[3])*dy; lateral=-math.sin(a[3])*dx+math.cos(a[3])*dy
        heading=sum(math.atan2(math.sin(q[3]-p[3]),math.cos(q[3]-p[3])) for p,q in zip(odometry[start:end],odometry[start+1:end+1]))
        sample={**annotation,'measured_forward_m':forward,'measured_lateral_m':lateral,'measured_yaw_rad':heading,
            'forward_error_m':forward-annotation['expected_forward_m'],'lateral_error_m':lateral-annotation['expected_lateral_m'],'yaw_error_rad':heading-annotation['expected_yaw_rad']}
        samples.append(sample)
    distributions={}
    for key in ('forward_error_m','lateral_error_m','yaw_error_rad'):
        values=[row[key] for row in samples]
        if values: distributions[key]={'count':len(values),'mean':statistics.mean(values),'std':statistics.stdev(values) if len(values)>1 else None,'min':min(values),'max':max(values)}
    return {'samples':samples,'distributions':distributions,'segment_count_ge_five':len(samples)>=5}


def compare(real,simulation):
    if real.get('kind')!='real' or simulation.get('kind')!='simulation': raise ValueError('Distinct real/simulation provenance required')
    a,b=real.get('scan',{}),simulation.get('scan',{})
    result={'definition':'simulation minus real','scan_difference':{key:b[key]-a[key] for key in ('measurement_hz','invalid_fraction','median_temporal_sigma_m','interval_std_s') if isinstance(a.get(key),(int,float)) and isinstance(b.get(key),(int,float))},
        'odometry_drift_comparison':'unverified: independent displacement annotations required',
        'calibration_complete':False,'acceptance_thresholds_changed':False}
    if real.get('motion_drift') and simulation.get('motion_drift'):
        result['odometry_drift_comparison']={'real':real['motion_drift'],'simulation':simulation['motion_drift']}
    result['scan_geometry_equal']=all(a.get(key)==b.get(key) for key in ('beams','range_min_m','range_max_m','angle_min_rad','angle_max_rad'))
    if not result['scan_geometry_equal']: result['limitation']='Different angular/range geometry; aggregate noise differences are diagnostic only'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bag',type=Path)
    parser.add_argument('--kind',choices=['real','simulation'])
    parser.add_argument('--motion-annotations',type=Path,help='Independent tape/angle evidence and ROS-time segment endpoints')
    parser.add_argument('--stationary',action='store_true',help='Explicitly attest no sensor/scene motion during this recording')
    parser.add_argument('--scan-topic',default='/scan'); parser.add_argument('--odom-topic',default='/odom')
    parser.add_argument('--real-stats',type=Path); parser.add_argument('--sim-stats',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Choose a new output; historical results are immutable')
    if args.real_stats or args.sim_stats:
        if not args.real_stats or not args.sim_stats: parser.error('Both stats files required')
        result=compare(json.loads(args.real_stats.read_text()),json.loads(args.sim_stats.read_text()))
    else:
        if not args.bag or not args.kind or not (args.stationary or args.motion_annotations): parser.error('Requires --bag --kind and stationary attestation or independent motion annotations')
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from sensor_msgs.msg import LaserScan
        from nav_msgs.msg import Odometry
        import yaml
        metadata=yaml.safe_load((args.bag/'metadata.yaml').read_text())['rosbag2_bagfile_information']
        reader=rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(args.bag),storage_id=metadata['storage_identifier']),rosbag2_py.ConverterOptions('',''))
        frames=[]; stamps=[]; odom=[]; geometry=None
        while reader.has_next():
            topic,data,_=reader.read_next()
            if topic==args.scan_topic:
                message=deserialize_message(data,LaserScan)
                current=(message.range_min,message.range_max,message.angle_min,message.angle_max)
                if geometry is not None and current!=geometry: raise ValueError('Laser geometry changed')
                geometry=current; frames.append(list(message.ranges)); stamps.append(message.header.stamp.sec+message.header.stamp.nanosec/1e9)
            elif topic==args.odom_topic:
                m=deserialize_message(data,Odometry); q=m.pose.pose.orientation; p=m.pose.pose.position
                odom.append([m.header.stamp.sec+m.header.stamp.nanosec/1e9,p.x,p.y,math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))])
        if geometry is None: raise ValueError('No laser measurements')
        result={'kind':args.kind,'stationary_attested':args.stationary,'bag':str(args.bag.resolve()),
            'source_sha256':{str(p.relative_to(args.bag)):hashlib.sha256(p.read_bytes()).hexdigest() for p in args.bag.rglob('*') if p.is_file()},
            'scan':scan_statistics(frames,stamps,*geometry[:2]),'calibration_complete':False}
        if not args.stationary:
            result['scan']['median_temporal_sigma_m']=None
            result['scan']['noise_estimation']='unverified: moving sensor/scene'
        if args.motion_annotations:
            result['motion_drift']=motion_drift(odom,json.loads(args.motion_annotations.read_text())['segments'])
        result['scan'].update(angle_min_rad=geometry[2],angle_max_rad=geometry[3])
        if odom and args.stationary:
            start=odom[0]; end=odom[-1]
            result['stationary_odom']={'messages':len(odom),'duration_s':end[0]-start[0],'endpoint_translation_m':math.dist(start[1:3],end[1:3]),'endpoint_yaw_rad':math.atan2(math.sin(end[3]-start[3]),math.cos(end[3]-start[3])),
                'maximum_translation_m':max(math.dist(start[1:3],p[1:3]) for p in odom)}
        result['limitations']=['Invalid returns include no-echo; not equal to packet loss.','Temporal beam spread requires a stationary sensor and unchanged scene.','Stamp interval variation is not hardware timestamp error without an independent time reference.','Moving odometry drift requires independently measured displacement/yaw annotations; unverified.']
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream: json.dump(result,stream,indent=2,allow_nan=False); stream.write('\n')
    print(str(args.output))
if __name__=='__main__': main()
