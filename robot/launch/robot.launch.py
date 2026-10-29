"""Board-only mapping/navigation. Preconditions intentionally block unverified hardware."""
import json,math,sys,tempfile
from pathlib import Path
import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument,OpaqueFunction,ExecuteProcess,RegisterEventHandler,EmitEvent
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from preflight import validate,calibrated_geometry


def configure(context):
    explore=LaunchConfiguration('explore').perform(context)=='true'
    config=validate(json.loads(Path(LaunchConfiguration('hardware').perform(context)).read_text()),required_gate=3 if explore else 2)
    nav=yaml.safe_load((ROOT/'config/nav2.yaml').read_text())
    calibration=json.loads(Path(config['calibration_file']).read_text())
    footprint,radius=calibrated_geometry(calibration); polygon=json.dumps(footprint)
    for name in ('local_costmap','global_costmap'):
        params=nav[name][name]['ros__parameters']; params['footprint']=polygon
        params['robot_base_frame']=config['base_frame']
        params['obstacle_layer']['scan']['topic']=config['scan_topic']
    nav['local_costmap']['local_costmap']['ros__parameters']['global_frame']=config['odom_frame']
    smoother=nav['velocity_smoother']['ros__parameters']; safety=config['safety']
    controller=nav['controller_server']['ros__parameters']['FollowPath']
    controller['desired_linear_vel']=safety['max_linear_m_s']
    controller['rotate_to_heading_angular_vel']=safety['max_yaw_rad_s']
    smoother['odom_topic']=config['odom_topic']
    smoother['max_velocity']=[safety['max_linear_m_s'],0.,safety['max_yaw_rad_s']]
    smoother['min_velocity']=[-safety['max_linear_m_s'],0.,-safety['max_yaw_rad_s']]
    # Stage the behavior tree under ASCII, as Humble rewrites Unicode paths.
    runtime=Path(tempfile.mkdtemp(prefix='wheeltec-robot-'))
    tree=runtime/'navigate_wait.xml'; tree.write_bytes((ROOT/'config/navigate_wait.xml').read_bytes())
    nav['bt_navigator']['ros__parameters']['default_nav_to_pose_bt_xml']=str(tree)
    nav['bt_navigator']['ros__parameters']['robot_base_frame']=config['base_frame']
    nav['bt_navigator']['ros__parameters']['odom_topic']=config['odom_topic']
    collision=yaml.safe_load((ROOT/'config/collision_monitor.yaml').read_text())
    c=collision['collision_monitor']['ros__parameters']; c['base_frame_id']=config['base_frame']; c['odom_frame_id']=config['odom_frame']
    c['scan']['topic']=config['scan_topic']
    margin=config['measured_braking_distance_m']+config['safety']['obstacle_margin_m']
    # Conservative expanded bounding box from the measured full footprint.
    xs=[p[0] for p in footprint]; ys=[p[1] for p in footprint]
    x0,x1,y0,y1=min(xs)-margin,max(xs)+margin,min(ys)-margin,max(ys)+margin
    c['StopZone']['points']=[x1,y1,x1,y0,x0,y0,x0,y1]
    params=runtime/'nav2.yaml'; params.write_text(yaml.safe_dump(nav,sort_keys=False))
    collision_path=runtime/'collision.yaml'; collision_path.write_text(yaml.safe_dump(collision,sort_keys=False))
    slam=yaml.safe_load((ROOT/'config/slam.yaml').read_text()); sp=slam['slam_toolbox']['ros__parameters']
    sp.update(base_frame=config['base_frame'],odom_frame=config['odom_frame'],scan_topic=config['scan_topic'])
    slam_path=runtime/'slam.yaml'; slam_path.write_text(yaml.safe_dump(slam,sort_keys=False))
    actions=[]; names=[]
    for package,executable in [('nav2_controller','controller_server'),('nav2_smoother','smoother_server'),('nav2_planner','planner_server'),('nav2_behaviors','behavior_server'),('nav2_bt_navigator','bt_navigator'),('nav2_waypoint_follower','waypoint_follower'),('nav2_velocity_smoother','velocity_smoother')]:
        remaps=[]
        if executable in ('controller_server','behavior_server'): remaps=[('cmd_vel','/safety/nav_cmd_vel')]
        if executable=='velocity_smoother': remaps=[('cmd_vel','/safety/nav_cmd_vel'),('cmd_vel_smoothed','/safety/smoothed_cmd_vel')]
        actions.append(Node(package=package,executable=executable,name=executable,parameters=[str(params)],remappings=remaps,output='screen'))
        names.append(executable)
    actions.append(Node(package='nav2_collision_monitor',executable='collision_monitor',name='collision_monitor',parameters=[str(collision_path)],output='screen')); names.append('collision_monitor')
    actions.append(Node(package='nav2_lifecycle_manager',executable='lifecycle_manager',name='lifecycle_manager_robot',parameters=[{'use_sim_time':False,'autostart':True,'node_names':names}],output='screen'))
    actions.append(Node(package='slam_toolbox',executable='async_slam_toolbox_node',name='slam_toolbox',parameters=[str(slam_path)],output='screen'))
    actions.append(Node(package='nav2_map_server',executable='map_saver_server',name='map_saver',parameters=[{'use_sim_time':False,'free_thresh_default':.19,'occupied_thresh_default':.65}],output='screen'))
    actions.append(Node(package='nav2_lifecycle_manager',executable='lifecycle_manager',name='lifecycle_manager_map_saver',parameters=[{'use_sim_time':False,'autostart':True,'node_names':['map_saver']}],output='screen'))
    if LaunchConfiguration('explore').perform(context)=='true':
        actions.append(Node(package='wheeltec_explore',executable='explore',parameters=[{'use_sim_time':False,'base_frame':config['base_frame'],'odom_frame':config['odom_frame'],'robot_radius':radius}],output='screen'))
    watchdog=ExecuteProcess(cmd=['python3',str(ROOT/'watchdog.py'),'--config',LaunchConfiguration('hardware').perform(context),'--gate','3' if explore else '2'],output='screen')
    actions.append(watchdog)
    # A critical process exit shuts down this owned stack; independent driver expiry
    # remains mandatory because SIGKILL/power loss cannot publish a final zero.
    for action in [a for a in actions if isinstance(a,(Node,ExecuteProcess))]:
        actions.insert(0,RegisterEventHandler(OnProcessExit(target_action=action,on_exit=[EmitEvent(event=Shutdown(reason='Robot stack process exited; driver watchdog must hold stop'))])))
    return actions


def generate_launch_description():
    return LaunchDescription([DeclareLaunchArgument('hardware',default_value=str(ROOT/'config/robot.json')),DeclareLaunchArgument('explore',default_value='false',choices=['true','false']),OpaqueFunction(function=configure)])
