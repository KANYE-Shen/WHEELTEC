"""Validate temporary obstacle avoidance and bounded blocked-route observation.

Run against a saved map with an independent ROS domain and Gazebo partition.
Simulator truth is recorded only by this test, never provided to Nav2 / AMCL.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def rectangle(x, y, hx, hy, yaw=0.0):
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + c*dx - s*dy, y + s*dx + c*dy)
            for dx, dy in [(-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy)]]


def polygon_distance(a, b):
    """Euclidean separation; negative SAT penetration when rectangles overlap."""
    overlap = math.inf
    separated = False
    for polygon in (a, b):
        for i, p in enumerate(polygon):
            q = polygon[(i+1) % len(polygon)]
            axis = (-(q[1]-p[1]), q[0]-p[0])
            length = math.hypot(*axis)
            axis = (axis[0]/length, axis[1]/length)
            pa = [v[0]*axis[0]+v[1]*axis[1] for v in a]
            pb = [v[0]*axis[0]+v[1]*axis[1] for v in b]
            amount = min(max(pa),max(pb))-max(min(pa),min(pb))
            separated |= amount < 0
            overlap = min(overlap, amount)
    if not separated:
        return -overlap

    def point_segment(p, start, end):
        dx, dy = end[0]-start[0], end[1]-start[1]
        t = max(0.0,min(1.0,((p[0]-start[0])*dx+(p[1]-start[1])*dy)/(dx*dx+dy*dy)))
        return math.hypot(p[0]-start[0]-t*dx,p[1]-start[1]-t*dy)

    return min(point_segment(p,poly[i],poly[(i+1)%len(poly)])
               for points,poly in ((a,b),(b,a)) for p in points for i in range(len(poly)))


def hashes(path):
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (path,path.with_suffix('.pgm'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--domain', type=int, default=81)
    args = parser.parse_args()
    map_path = args.map.expanduser().resolve()
    before = hashes(map_path)
    run_dir = Path.home()/'wheeltec_sim_ws/data/runs'/(time.strftime('%Y%m%d-%H%M%S')+'_obstacles')
    run_dir.mkdir(parents=True,exist_ok=False)
    partition = 'wheeltec-obstacles-'+str(os.getpid())
    os.environ.update(ROS_DOMAIN_ID=str(args.domain),ROS_LOCALHOST_ONLY='1',IGN_PARTITION=partition)
    result = {'success':False,'run_dir':str(run_dir),'map':str(map_path),'domain':args.domain,
              'partition':partition,'saved_map_sha256_before':before}
    config_bytes = (ROOT/'simulation/config/nav2.yaml').read_bytes()
    (run_dir/'nav2.yaml').write_bytes(config_bytes)
    result['nav2_config_sha256'] = hashlib.sha256(config_bytes).hexdigest()
    process = node = log = handle = None
    latest, trajectories, commands = {}, {'avoidance':[],'blocked':[],'resumed':[],'canceled':[]}, []
    phase = 'initialization'
    try:
        import rclpy
        from rclpy.action import ActionClient
        from rclpy.parameter import Parameter
        from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
        from tf2_msgs.msg import TFMessage
        from rosgraph_msgs.msg import Clock
        from nav2_msgs.action import NavigateToPose
        from lifecycle_msgs.srv import GetState
        from action_msgs.msg import GoalStatusArray
        from rclpy.qos import QoSProfile, DurabilityPolicy
        from tf2_ros import Buffer, TransformListener

        rclpy.init()
        node = rclpy.create_node('wheeltec_obstacle_check',
                                parameter_overrides=[Parameter('use_sim_time',value=True)])
        buffer = Buffer(node=node)
        listener = TransformListener(buffer,node)
        wait_status = node.create_subscription(GoalStatusArray,'/wait/_action/status',
            lambda m:latest.update(wait_active=any(g.status==2 for g in m.status_list)),
            QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))

        def truth(message):
            for item in message.transforms:
                if item.child_frame_id != 'wheeltec_reference':
                    continue
                p,q = item.transform.translation,item.transform.rotation
                yaw = math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
                row = {'wall_time':time.monotonic(),'world_x':p.x,'world_y':p.y,'yaw':yaw,
                       'map_x':p.x+1.7,'map_y':p.y+1.5}
                latest['truth'] = row
                if phase in trajectories:
                    trajectories[phase].append(row)

        def command(message):
            row = (time.monotonic(),message.linear.x,message.angular.z)
            commands.append(row)
            latest['command'] = row

        subs = [node.create_subscription(TFMessage,'/simulation/ground_truth',truth,10),
                node.create_subscription(Twist,'/cmd_vel',command,10),
                node.create_subscription(Clock,'/clock',lambda m:latest.update(clock=m),10)]
        client = ActionClient(node,NavigateToPose,'navigate_to_pose')
        active = node.create_client(GetState,'/bt_navigator/get_state')
        initial_pub = node.create_publisher(PoseWithCovarianceStamped,'/initialpose',10)
        log = (run_dir/'launch.log').open('w')
        process = subprocess.Popen(['python3',str(ROOT/'simulation/run_room.py'),
            'gui:=false','rviz:=false','mode:=localization','map:='+str(map_path),
            'ros_domain_id:='+str(args.domain),'partition:='+partition],
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)

        def wait(predicate,seconds,reason):
            deadline = time.monotonic()+seconds
            while time.monotonic()<deadline:
                rclpy.spin_once(node,timeout_sec=.05)
                if process.poll() is not None:
                    raise RuntimeError('Launch exited; see launch.log')
                if predicate():
                    return
            raise RuntimeError('Timeout: '+reason)

        def future(value,seconds=15):
            wait(value.done,seconds,'ROS future')
            return value.result()

        def settle(seconds):
            end = time.monotonic()+seconds
            wait(lambda:time.monotonic()>=end,seconds+2,'settle')

        wait(lambda:initial_pub.get_subscription_count()>0 and 'clock' in latest,65,'AMCL initialization')
        initial = PoseWithCovarianceStamped()
        initial.header.frame_id = 'map'
        initial.pose.pose.orientation.w = 1.0
        initial.pose.covariance[0] = initial.pose.covariance[7] = .10
        initial.pose.covariance[35] = .05
        for _ in range(5):
            initial.header.stamp = node.get_clock().now().to_msg()
            initial_pub.publish(initial)
            settle(.25)
        wait(lambda:client.server_is_ready() and active.service_is_ready() and
             'truth' in latest and buffer.can_transform('map','base_link',rclpy.time.Time()),65,'localized active navigation')
        for _ in range(50):
            state = future(active.call_async(GetState.Request()))
            if state.current_state.id == 3:
                break
            settle(.25)
        else:
            raise RuntimeError('Nav2 lifecycle never activated')
        result['initial_physics_pose'] = latest['truth']

        def spawn(name,x,y,sx,sy,sz):
            sdf = (f'<sdf version="1.8"><model name="{name}"><static>true</static>'
                   f'<pose>{x} {y} {sz/2} 0 0 0</pose><link name="link">'
                   f'<collision name="collision"><geometry><box><size>{sx} {sy} {sz}</size>'
                   '</box></geometry></collision><visual name="visual"><geometry><box>'
                   f'<size>{sx} {sy} {sz}</size></box></geometry><material>'
                   '<ambient>0.9 0.15 0.1 1</ambient><diffuse>0.9 0.15 0.1 1</diffuse>'
                   '</material></visual></link></model></sdf>')
            (run_dir/(name+'.sdf')).write_text(sdf)
            request = 'sdf: '+json.dumps(sdf)+' allow_renaming: false'
            answer = subprocess.run(['ign','service','-s','/world/wheeltec_room/create',
                '--reqtype','ignition.msgs.EntityFactory','--reptype','ignition.msgs.Boolean',
                '--timeout','5000','--req',request],capture_output=True,text=True,timeout=12)
            (run_dir/(name+'-create.log')).write_text(answer.stdout+answer.stderr)
            if answer.returncode or 'data: true' not in answer.stdout:
                raise RuntimeError('Could not create '+name+': '+answer.stdout+answer.stderr)
            settle(2.0)

        def send_goal(x,y):
            goal = NavigateToPose.Goal()
            goal.pose.header.frame_id = 'map'
            goal.pose.header.stamp = node.get_clock().now().to_msg()
            goal.pose.pose.position.x,goal.pose.pose.position.y = float(x),float(y)
            goal.pose.pose.orientation.w = 1.0
            value = future(client.send_goal_async(goal))
            if not value.accepted:
                raise RuntimeError('Navigation goal rejected')
            return value

        box = rectangle(-.8,-1.4,.2,.3)
        spawn('temporary_box',-.8,-1.4,.4,.6,.8)
        phase = 'avoidance'
        begin = time.monotonic()
        handle = send_goal(1.8,.2)
        answer = future(handle.get_result_async(),150)
        settle(.5)
        final = latest['truth']
        error = math.hypot(final['map_x']-1.8,final['map_y']-.2)
        clearance = min(polygon_distance(rectangle(p['world_x'],p['world_y'],.18,.195,p['yaw']),box)
                        for p in trajectories['avoidance'])
        deviation = max(abs(p['map_y']-(.2/1.8)*p['map_x'])/math.sqrt(1+(.2/1.8)**2)
                        for p in trajectories['avoidance'])
        result['avoidance'] = {'status':answer.status,'gazebo_truth_error_m':error,
            'minimum_physical_footprint_clearance_m':clearance,
            'maximum_distance_from_original_line_m':deviation,
            'wall_seconds':time.monotonic()-begin,'samples':len(trajectories['avoidance'])}
        print(json.dumps(result['avoidance']),flush=True)
        assert answer.status == 4, result['avoidance']
        assert error < .22, result['avoidance']
        assert clearance > 0.0 and deviation > .30, result['avoidance']

        phase = 'transition'
        wall = rectangle(-.8,0,.075,2.6)
        spawn('temporary_blocking_wall',-.8,0,.15,5.2,.8)
        phase = 'blocked'
        begin = time.monotonic()
        handle = send_goal(0.0,0.0)
        pending = handle.get_result_async()
        wait(lambda:latest.get('wait_active',False) or pending.done(),90,'blocked route reaches waiting recovery')
        assert not pending.done(), 'Blocked task ended before waiting'
        wait_begin = time.monotonic()
        # Allow cancellation/deceleration of the previous controller action.
        settle(.8)
        anchor = latest['truth']
        settle(3.0)
        rows = [p for p in trajectories['blocked'] if p['wall_time']>=anchor['wall_time']]
        assert rows, 'No blocked-route physics samples'
        movement = max(math.hypot(p['world_x']-anchor['world_x'],p['world_y']-anchor['world_y']) for p in rows)
        heading_change = max(abs(math.atan2(math.sin(p['yaw']-anchor['yaw']),math.cos(p['yaw']-anchor['yaw']))) for p in rows)
        wall_clearance = min(polygon_distance(rectangle(p['world_x'],p['world_y'],.18,.195,p['yaw']),wall)
                             for p in trajectories['blocked'])
        result['blocked_route'] = {'task_still_active':not pending.done(),
            'observation_wall_seconds':time.monotonic()-begin,
            'wait_reached_after_wall_seconds':wait_begin-begin,
            'measured_waiting_wall_seconds':3.0,
            'minimum_physical_wall_clearance_m':wall_clearance,
            'crossed_wall':any(p['world_x']<-.8 for p in trajectories['blocked']),
            'waiting_translation_m':movement,'waiting_heading_change_rad':heading_change}
        print(json.dumps(result['blocked_route']),flush=True)
        assert not pending.done(), result['blocked_route']
        assert wall_clearance>0 and not result['blocked_route']['crossed_wall'], result['blocked_route']
        assert movement<.02 and heading_change<.04, result['blocked_route']

        phase = 'resumed'
        answer = subprocess.run(['ign','service','-s','/world/wheeltec_room/remove',
            '--reqtype','ignition.msgs.Entity','--reptype','ignition.msgs.Boolean',
            '--timeout','5000','--req','name: "temporary_blocking_wall" type: MODEL'],
            capture_output=True,text=True,timeout=12)
        (run_dir/'blocking-wall-remove.log').write_text(answer.stdout+answer.stderr)
        assert answer.returncode==0 and 'data: true' in answer.stdout, answer.stdout+answer.stderr
        resumed_begin = time.monotonic()
        answer = future(pending,120)
        settle(.5)
        final = latest['truth']
        error = math.hypot(final['map_x'],final['map_y'])
        result['obstacle_removal_resume'] = {'same_goal_status':answer.status,
            'new_goal_submitted':False,'gazebo_truth_error_m':error,
            'wall_seconds_after_removal':time.monotonic()-resumed_begin}
        assert answer.status==4 and error<.22, result['obstacle_removal_resume']

        phase = 'canceled'
        handle = send_goal(3.0,3.3)
        pending = handle.get_result_async()
        settle(1.0)
        cancel = future(handle.cancel_goal_async(),10)
        answer = future(pending,15)
        end_position = (latest['truth']['world_x'],latest['truth']['world_y'])
        settle(2.0)
        final_position = (latest['truth']['world_x'],latest['truth']['world_y'])
        final_command = commands[-1] if commands else None
        stable_rows = [p for p in trajectories['canceled']
                       if p['wall_time']>latest['truth']['wall_time']-1.0]
        stable_displacement = max(math.hypot(p['world_x']-final_position[0],
                                             p['world_y']-final_position[1]) for p in stable_rows)
        stopped = (final_command is not None and abs(final_command[1])<.01 and
                   abs(final_command[2])<.02 and stable_displacement<.01)
        result['cancellation'] = {'status':answer.status,'cancel_response_goal_count':len(cancel.goals_canceling),
            'final_zero_velocity':stopped,'last_command':final_command,
            'stationary_last_second_displacement_m':stable_displacement,
            'displacement_after_result_m':math.dist(end_position,final_position)}
        assert answer.status==5 and stopped, result['cancellation']
        assert result['cancellation']['displacement_after_result_m']<.12, result['cancellation']
        result['success'] = True
    except Exception as exc:
        result['error'] = repr(exc)
    finally:
        if handle is not None and node is not None:
            try:
                cancel = handle.cancel_goal_async()
                deadline = time.monotonic()+2
                while not cancel.done() and time.monotonic()<deadline:
                    rclpy.spin_once(node,timeout_sec=.05)
            except Exception:
                pass
        if process is not None:
            try:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=25)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait(timeout=5)
        if log:
            log.close()
        if node:
            node.destroy_node()
            rclpy.shutdown()
        after = hashes(map_path)
        result['saved_map_sha256_after'] = after
        result['saved_map_unchanged'] = before == after
        if before != after:
            result['success'] = False
            result['error'] = 'Saved map changed during dynamic obstacle test'
        (run_dir/'commands.json').write_text(json.dumps(commands,indent=2))
        for name,rows in trajectories.items():
            (run_dir/(name+'-trajectory.json')).write_text(json.dumps(rows,indent=2))
        (run_dir/'result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2),flush=True)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())