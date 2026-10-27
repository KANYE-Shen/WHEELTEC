"""Read-only TF diagnostic. Run in the target ROS environment, same domain."""
import json
import time
import rclpy
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener
from tf2_msgs.msg import TFMessage
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy, ReliabilityPolicy
rclpy.init()
n=Node('console_tf_diagnostic')
b=Buffer(); listener=TransformListener(b,n)
edges={}
def receive(m,static=False):
 for t in m.transforms:
  edges[t.header.frame_id+' -> '+t.child_frame_id]={'static':static,'stamp':t.header.stamp.sec+t.header.stamp.nanosec/1e9,'received':time.monotonic()}
subs=[n.create_subscription(TFMessage,'/tf',receive,qos_profile_sensor_data),n.create_subscription(TFMessage,'/tf_static',lambda m:receive(m,True),QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE))]
end=time.monotonic()+5
while time.monotonic()<end:rclpy.spin_once(n,timeout_sec=.1)
result={'edges':{k:dict(v,receipt_age=time.monotonic()-v['received']) for k,v in edges.items()}}
for target,source in [('map','base_link'),('odom','base_link'),('base_link','laser')]:
 try:
  t=b.lookup_transform(target,source,rclpy.time.Time()); result[target+' <- '+source]={'stamp':t.header.stamp.sec+t.header.stamp.nanosec/1e9}
 except Exception as exc:result[target+' <- '+source]=str(exc)
print(json.dumps(result,indent=2));n.destroy_node();rclpy.shutdown()
