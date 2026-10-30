"""Passive scan/camera statistics; no odom/TF retry, no motion publishers."""
import argparse,json,math,time,statistics
from pathlib import Path
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan,Image
p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
rclpy.init();node=rclpy.create_node('wheeltec_stationary_sensor_statistics')
records={'scan':[],'camera':[]};last_scan={};counts=[];means=[];m2=[];invalid={'nan':0,'infinity':0,'outside_declared_range':0,'samples':0}
def receive(kind,msg):
 now=time.time();stamp=msg.header.stamp.sec+msg.header.stamp.nanosec/1e9
 records[kind].append([time.monotonic(),stamp,now-stamp])
 if kind!='scan':return
 last_scan.update(frame=msg.header.frame_id,beams=len(msg.ranges),angle_min_rad=msg.angle_min,angle_max_rad=msg.angle_max,angle_increment_rad=msg.angle_increment,range_min=msg.range_min,range_max=msg.range_max,scan_time=msg.scan_time,time_increment=msg.time_increment)
 if len(counts)!=len(msg.ranges):counts[:]=[0]*len(msg.ranges);means[:]=[0.]*len(msg.ranges);m2[:]=[0.]*len(msg.ranges)
 for i,x in enumerate(msg.ranges):
  invalid['samples']+=1
  if math.isnan(x):invalid['nan']+=1;continue
  if math.isinf(x):invalid['infinity']+=1;continue
  if not msg.range_min<=x<=msg.range_max:invalid['outside_declared_range']+=1;continue
  counts[i]+=1;delta=x-means[i];means[i]+=delta/counts[i];m2[i]+=delta*(x-means[i])
subs=[node.create_subscription(LaserScan,'/scan',lambda m:receive('scan',m),qos_profile_sensor_data),node.create_subscription(Image,'/image_raw',lambda m:receive('camera',m),qos_profile_sensor_data)]
start=time.monotonic()
while time.monotonic()-start<65:rclpy.spin_once(node,timeout_sec=.05)
result={'read_only':True,'motion_published':False,'stationarity_confirmed_by_operator':False,'per_beam_noise_is_diagnostic_only':True,'scan_header':last_scan,'invalid_range_values':invalid,'streams':{},'raw_samples':records}
for kind,rows in records.items():
 elapsed=rows[-1][0]-rows[0][0] if len(rows)>1 else 0
 result['streams'][kind]={'messages':len(rows),'effective_seconds':elapsed,'hz':(len(rows)-1)/elapsed if elapsed else None,'future_samples_over_150ms':sum(x[2]<-.15 for x in rows),'stale_samples_over_1s':sum(x[2]>1 for x in rows),'backwards_stamps':sum(b[1]<a[1] for a,b in zip(rows,rows[1:])),'duplicate_stamps':sum(b[1]==a[1] for a,b in zip(rows,rows[1:])),'age_min_s':min((x[2] for x in rows),default=None),'age_max_s':max((x[2] for x in rows),default=None)}
result['beam_statistics']=[{'beam':i,'valid_samples':n,'mean_m':means[i] if n else None,'std_m':math.sqrt(m2[i]/(n-1)) if n>1 else None} for i,n in enumerate(counts)]
result['graph_nodes']=node.get_node_names();result['topics_and_types']=dict(node.get_topic_names_and_types())
result['command_topic_publishers']={t:[{'node':x.node_name,'namespace':x.node_namespace} for x in node.get_publishers_info_by_topic(t)] for t in ['/cmd_vel','/safety/nav_cmd_vel','/safety/operator_heartbeat']}
Path(args.output).write_text(json.dumps(result,allow_nan=False,indent=2))
node.destroy_node();rclpy.shutdown()
