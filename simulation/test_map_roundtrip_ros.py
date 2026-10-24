"""Actual installed Nav2 PGM/YAML save/load roundtrip; domain 84, no robot motion.

Run explicitly after sourcing ROS. Artifacts stay in the Linux runtime data.
The free threshold is read from the real Explorer SaveMap request setting.
"""
import ast
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    os.environ.update(ROS_DOMAIN_ID='84',ROS_LOCALHOST_ONLY='1')
    import rclpy
    from nav_msgs.msg import OccupancyGrid
    from lifecycle_msgs.srv import ChangeState
    from rclpy.qos import QoSProfile,DurabilityPolicy
    source=Path(__file__).resolve().parents[1]/'src/wheeltec_explore/wheeltec_explore/node.py'
    module=ast.parse(source.read_text())
    threshold=next(ast.literal_eval(node.value) for node in ast.walk(module) if isinstance(node,ast.Assign)
                   and any(isinstance(target,ast.Attribute) and target.attr=='free_thresh' for target in node.targets))
    run=Path.home()/'wheeltec_sim_ws/data/runs'/(time.strftime('%Y%m%d-%H%M%S')+'_map_roundtrip')
    run.mkdir(parents=True,exist_ok=False)
    rclpy.init()
    node=rclpy.create_node('map_roundtrip_check')
    qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL)
    publisher=node.create_publisher(OccupancyGrid,'/roundtrip_input',qos)
    received=[]
    subscription=node.create_subscription(OccupancyGrid,'/map',lambda msg:received.append(list(msg.data)),qos)
    grid=OccupancyGrid()
    grid.header.frame_id='map'
    grid.info.width=3
    grid.info.height=1
    grid.info.resolution=.05
    grid.info.origin.orientation.w=1.0
    grid.data=[-1,0,100]
    processes=[]
    logs=[]
    result={'free_thresh':threshold,'expected':[-1,0,100],'run_dir':str(run),'success':False}
    def launch(command,name):
        log=(run/name).open('w')
        logs.append(log)
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        processes.append(process)
        return process
    try:
        saver=launch(['ros2','run','nav2_map_server','map_saver_cli','-t','/roundtrip_input','-f',str(run/'map'),
                      '--free',str(threshold),'--occ','.65'],'saver.log')
        deadline=time.monotonic()+20
        while saver.poll() is None and time.monotonic()<deadline:
            grid.header.stamp=node.get_clock().now().to_msg()
            publisher.publish(grid)
            rclpy.spin_once(node,timeout_sec=.1)
        if saver.poll()!=0:
            raise RuntimeError('Actual Nav2 saver did not complete')
        server=launch(['ros2','run','nav2_map_server','map_server','--ros-args','-r','__node:=roundtrip_server',
                       '-p','yaml_filename:='+str(run/'map.yaml')],'server.log')
        client=node.create_client(ChangeState,'/roundtrip_server/change_state')
        if not client.wait_for_service(timeout_sec=15):
            raise RuntimeError('Actual Nav2 map_server lifecycle unavailable')
        for transition in (1,3):
            request=ChangeState.Request()
            request.transition.id=transition
            future=client.call_async(request)
            rclpy.spin_until_future_complete(node,future,timeout_sec=15)
            if not future.done() or not future.result().success:
                raise RuntimeError('Actual Nav2 lifecycle transition failed')
        deadline=time.monotonic()+10
        while not received and time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.1)
        result['received']=received[-1] if received else None
        result['success']=result['received']==result['expected']
    except Exception as exc:
        result['error']=repr(exc)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait()
        for log in logs:
            log.close()
        node.destroy_node()
        rclpy.shutdown()
        (run/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2),flush=True)
    return 0 if result['success'] else 1


if __name__=='__main__':
    raise SystemExit(main())
