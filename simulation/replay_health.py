"""Replay recorded estimate streams into MapHealth; never reads simulator truth."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/wheeltec_explore'))
from wheeltec_explore.health import MapHealth


def replay(bag):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('',''))
    types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()
           if t.name in ('/clock','/scan','/map','/tf')}
    reader.set_filter(rosbag2_py.StorageFilter(topics=list(types)))
    health=MapHealth(require_slam_alive=False)
    now=last_check=0.
    counts={name:0 for name in types}
    issues={}
    first={}
    checks=healthy=0
    max_map_gap=0.
    previous_map=None
    def stamp(s): return s.sec+s.nanosec/1e9
    while reader.has_next():
        topic,data,_=reader.read_next()
        msg=deserialize_message(data,types[topic]); counts[topic]+=1
        if topic=='/clock': now=stamp(msg.clock)
        if now <= 0: continue
        if topic=='/scan': health.scan(stamp(msg.header.stamp),now)
        elif topic=='/map':
            old=health.streams.get('map')
            health.map(stamp(msg.header.stamp),now)
            if health.streams.get('map') != old:
                if previous_map is not None: max_map_gap=max(max_map_gap,now-previous_map)
                previous_map=now
        elif topic=='/tf':
            for t in msg.transforms:
                if t.header.frame_id.lstrip('/')=='map' and t.child_frame_id.lstrip('/')=='odom':
                    q=t.transform.rotation; v=t.transform.translation
                    yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
                    health.transform(stamp(t.header.stamp),now,(v.x,v.y,yaw))
        if now-last_check >= .1 and len(health.streams)==3:
            snapshot=health.snapshot(now); checks+=1; healthy+=snapshot['healthy']; last_check=now
            for issue in snapshot['issues']:
                issues[issue]=issues.get(issue,0)+1
                first.setdefault(issue,now)
    return dict(bag=str(bag),counts=counts,checks=checks,healthy_checks=healthy,
                issue_check_counts=issues,first_issue_sim_s=first,
                maximum_map_update_gap_s=max_map_gap,final=health.snapshot(now),
                slam_liveness='unverified: node graph/process events not recorded',
                no_truth_inputs=True,
                metadata_sha256=hashlib.sha256((Path(bag)/'metadata.yaml').read_bytes()).hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag',type=Path); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Output exists; preserve previous replay')
    result=replay(args.bag)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
