"""Reference simulation, SLAM/AMCL and Nav2 using the same sensor interfaces."""
import os
from pathlib import Path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction, RegisterEventHandler, SetEnvironmentVariable
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def algorithms(context, simulation):
    mode = LaunchConfiguration('mode').perform(context)
    navigation = LaunchConfiguration('navigation').perform(context).lower() == 'true'
    explore = LaunchConfiguration('explore').perform(context).lower() == 'true'
    if mode not in ('interfaces', 'mapping', 'localization'):
        raise RuntimeError('mode must be interfaces, mapping or localization')
    if explore and (mode != 'mapping' or not navigation):
        raise RuntimeError('Exploration requires mapping mode and navigation:=true')
    actions = []
    if mode == 'mapping':
        actions += [
            IncludeLaunchDescription(PythonLaunchDescriptionSource(str(Path(get_package_share_directory('slam_toolbox')) / 'launch/online_async_launch.py')),
                                     launch_arguments={'use_sim_time': 'true', 'slam_params_file': LaunchConfiguration('slam_config').perform(context)}.items()),
            Node(package='nav2_map_server', executable='map_saver_server', name='map_saver',
                 parameters=[{'use_sim_time': True, 'save_map_timeout': 10.0, 'free_thresh_default': .19,
                              'occupied_thresh_default': .65, 'map_subscribe_transient_local': True}], output='screen'),
            Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager_map_saver',
                 parameters=[{'use_sim_time': True, 'autostart': True, 'node_names': ['map_saver']}], output='screen'),
        ]
    if mode != 'interfaces' and navigation:
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(simulation/'launch/navigation.launch.py')),
            launch_arguments={'mode': mode, 'map': LaunchConfiguration('map').perform(context),
                              'params_file':LaunchConfiguration('nav2_config').perform(context)}.items()))
    if explore:
        actions.append(Node(package='wheeltec_explore', executable='explore', name='wheeltec_explore',
                            parameters=[{'use_sim_time': True, 'robot_radius':float(LaunchConfiguration('explorer_radius').perform(context)), **({'map_output': LaunchConfiguration('map_output').perform(context)} if LaunchConfiguration('map_output').perform(context) else {})}], output='screen'))
    capture_run = LaunchConfiguration('capture_run').perform(context)
    if explore and capture_run:
        actions.append(ExecuteProcess(cmd=['python3', str(simulation/'capture_process.py'),
                                           '--run', capture_run, '--metadata', LaunchConfiguration('capture_metadata').perform(context),
                                           '--open-browser', LaunchConfiguration('capture_browser').perform(context)],
                                      output='screen', sigterm_timeout='15', sigkill_timeout='20'))
    return actions


def generate_launch_description():
    simulation = Path(__file__).resolve().parents[1]
    common = ['ign', 'gazebo', '-r', '-v', '3', '--render-engine', 'ogre']
    world = LaunchConfiguration('world')
    gui = ExecuteProcess(cmd=common+[world], output='screen', condition=IfCondition(LaunchConfiguration('gui')))
    server = ExecuteProcess(cmd=common+['-s',world], output='screen', condition=UnlessCondition(LaunchConfiguration('gui')))
    bridge = Node(package='ros_gz_bridge', executable='parameter_bridge', name='room_bridge',
                  parameters=[{'config_file': LaunchConfiguration('bridge_config'), 'use_sim_time': True}], output='screen')
    realism = ExecuteProcess(cmd=['python3',str(simulation/'realism_node.py'),
            '--profile',LaunchConfiguration('realism_profile'),'--seed',LaunchConfiguration('seed'),
            '--scale',LaunchConfiguration('noise_scale'),'--ros-args','-p','use_sim_time:=true'],
            condition=IfCondition(PythonExpression(["'",LaunchConfiguration('realism'),"' == 'on'"])),output='screen')
    laser_tf = Node(package='tf2_ros', executable='static_transform_publisher', name='reference_laser_tf',
                    arguments=['--x','0','--y','0','--z','0.25','--frame-id','base_link',
                               '--child-frame-id','wheeltec_reference/base_link/laser'],
                    parameters=[{'use_sim_time': True}], output='screen')
    rviz = Node(package='rviz2', executable='rviz2', arguments=['-d',str(simulation/'config/room.rviz'), '-f',
                           PythonExpression(["'odom' if '",LaunchConfiguration('mode'),"' == 'interfaces' else 'map'"])],
                parameters=[{'use_sim_time': True}], condition=IfCondition(LaunchConfiguration('rviz')), output='screen')
    handlers = [RegisterEventHandler(OnProcessExit(target_action=a,
                on_exit=[EmitEvent(event=Shutdown(reason='A required simulation process exited.'))])) for a in (gui,server,bridge,realism)]
    return LaunchDescription([
        DeclareLaunchArgument('realism',default_value='off',choices=['on','off']),
        DeclareLaunchArgument('realism_profile',default_value=str(simulation/'config/realism.yaml')),
        DeclareLaunchArgument('seed',default_value='0'),
        DeclareLaunchArgument('noise_scale',default_value='1'),
        DeclareLaunchArgument('bridge_config',default_value=str(simulation/'config/bridge.yaml')),
        DeclareLaunchArgument('slam_config',default_value=str(simulation/'config/slam.yaml')),
        DeclareLaunchArgument('nav2_config',default_value=str(simulation/'config/nav2.yaml')),
        DeclareLaunchArgument('explorer_radius',default_value='0.35'),
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('mode', default_value='mapping'),
        DeclareLaunchArgument('navigation', default_value='true'),
        DeclareLaunchArgument('explore', default_value='false'),
        DeclareLaunchArgument('map', default_value=''),
        DeclareLaunchArgument('world', default_value=str(simulation/'worlds/room_25m2.sdf')),
        DeclareLaunchArgument('map_output', default_value=''),
        DeclareLaunchArgument('capture_run', default_value=''),
        DeclareLaunchArgument('capture_metadata', default_value='{}'),
        DeclareLaunchArgument('capture_browser', default_value='true'),
        DeclareLaunchArgument('ros_domain_id', default_value='77'),
        DeclareLaunchArgument('partition', default_value='wheeltec-room'),
        SetEnvironmentVariable('ROS_LOCALHOST_ONLY','1'),
        SetEnvironmentVariable('ROS_DOMAIN_ID',LaunchConfiguration('ros_domain_id')),
        SetEnvironmentVariable('IGN_PARTITION',LaunchConfiguration('partition')),
        SetEnvironmentVariable('QT_QPA_PLATFORM','xcb'),
        SetEnvironmentVariable('IGN_GUI_PLUGIN_PATH',str(Path.home()/'wheeltec_sim_ws/build/gui_sync')+os.pathsep+os.environ.get('IGN_GUI_PLUGIN_PATH','')),
        SetEnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH',str(simulation/'models')+os.pathsep+os.environ.get('IGN_GAZEBO_RESOURCE_PATH','')),
        *handlers, gui, server, bridge, realism, laser_tf,
        OpaqueFunction(function=algorithms, kwargs={'simulation':simulation}), rviz,
    ])
