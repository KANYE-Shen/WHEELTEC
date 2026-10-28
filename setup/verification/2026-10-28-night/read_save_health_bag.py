from pathlib import Path
import json
from collections import defaultdict
from rosbag2_py import SequentialReader,StorageOptions,ConverterOptions
from rosidl_runtime_py.utilities import get_message
from rclpy.serialization import deserialize_message
base=Path('/home/wheeltec/wheeltec_sim_ws/data/runs/20261028-active-scan-ab-v3')
run=base/'002_irregular_arc_seed0_angle180'
r=json.loads((run/'result.json').read_text())
reader=SequentialReader();reader.open(StorageOptions(uri=str(run/'bag'),storage_id='sqlite3'),ConverterOptions('',''))
types={t.name:t.type for t in reader.get_all_topics_and_types()}
samples=defaultdict(list)
while reader.has_next():
 topic,data,when=reader.read_next()
 if topic not in ('/tf','/scan','/map','/clock'):continue
 m=deserialize_message(data,get_message(types[topic]))
 if topic=='/tf':
  for t in m.transforms:
   if t.header.frame_id=='map' and t.child_frame_id=='odom':
    samples['map_to_odom'].append((when/1e9,t.header.stamp.sec+t.header.stamp.nanosec/1e9))
 elif topic=='/clock':samples[topic].append((when/1e9,m.clock.sec+m.clock.nanosec/1e9))
 else:samples[topic].append((when/1e9,m.header.stamp.sec+m.header.stamp.nanosec/1e9))
def stats(values):
 return {'messages':len(values),'first':values[0] if values else None,'last':values[-1] if values else None,'maximum_bag_stamp_gap_s':max((b[0]-a[0] for a,b in zip(values,values[1:])),default=None),'maximum_source_stamp_gap_s':max((b[1]-a[1] for a,b in zip(values,values[1:])),default=None)}
out={'scope':'Offline bag read only; source/bag timestamps, not wall latency','run':str(run),'seed':r['seed'],'pose':r['spawn']['pose'],'streams':{k:stats(v) for k,v in samples.items()},'statuses':[{'t':s['t'],'state':s.get('state'),'reason':s.get('reason'),'ages':s.get('map_health',{}).get('ages'),'slam_alive':s.get('map_health',{}).get('slam_alive')} for s in r['status_history']],'failures':r['failures']}
p=Path('/mnt/d/虚拟c盘/WHEELTEC/setup/verification/2026-10-28-night/save-tf-stale-evidence.json')
p.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'streams':out['streams'],'last_status':out['statuses'][-1]},indent=2))

