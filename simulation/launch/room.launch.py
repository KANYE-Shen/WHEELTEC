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
                                     launch_arguments={'use_sim_time': 'true', 'slam_params_file': str(simulation/'config/slam.yaml')}.items()),
            Node(package='nav2_map_server', executable='map_saver_server', name='map_saver',
                 parameters=[{'use_sim_time': True, 'save_map_timeout': 10.0, 'free_thresh_default': .25,
                              'occupied_thresh_default': .65, 'map_subscribe_transient_local': True}], output='screen'),
            Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager_map_saver',
                 parameters=[{'use_sim_time': True, 'autostart': True, 'node_names': ['map_saver']}], output='screen'),
        ]
    if mode != 'interfaces' and navigation:
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(simulation/'launch/navigation.launch.py')),
            launch_arguments={'mode': mode, 'map': LaunchConfiguration('map').perform(context)}.items()))
    if explore:
        actions.append(Node(package='wheeltec_explore', executable='explore', name='wheeltec_explore',
                            parameters=[{'use_sim_time': True}], output='screen'))
    return actions


def generate_launch_description():
    simulation = Path(__file__).resolve().parents[1]
    common = ['ign', 'gazebo', '-r', '-v', '3', '--render-engine', 'ogre']
    world = str(simulation/'worlds/room_25m2.sdf')
    gui = ExecuteProcess(cmd=common+[world], output='screen', condition=IfCondition(LaunchConfiguration('gui')))
    server = ExecuteProcess(cmd=common+['-s',world], output='screen', condition=UnlessCondition(LaunchConfiguration('gui')))
    bridge = Node(package='ros_gz_bridge', executable='parameter_bridge', name='room_bridge',
                  parameters=[{'config_file': str(simulation/'config/bridge.yaml'), 'use_sim_time': True}], output='screen')
    laser_tf = Node(package='tf2_ros', executable='static_transform_publisher', name='reference_laser_tf',
                    arguments=['--x','0','--y','0','--z','0.25','--frame-id','base_link',
                               '--child-frame-id','wheeltec_reference/base_link/laser'],
                    parameters=[{'use_sim_time': True}], output='screen')
    rviz = Node(package='rviz2', executable='rviz2', arguments=['-d',str(simulation/'config/room.rviz'), '-f',
                           PythonExpression(["'odom' if '",LaunchConfiguration('mode'),"' == 'interfaces' else 'map'"])],
                parameters=[{'use_sim_time': True}], condition=IfCondition(LaunchConfiguration('rviz')), output='screen')
    handlers = [RegisterEventHandler(OnProcessExit(target_action=a,
                on_exit=[EmitEvent(event=Shutdown(reason='A required simulation process exited.'))])) for a in (gui,server,bridge)]
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('mode', default_value='mapping'),
        DeclareLaunchArgument('navigation', default_value='true'),
        DeclareLaunchArgument('explore', default_value='false'),
        DeclareLaunchArgument('map', default_value=''),
        DeclareLaunchArgument('ros_domain_id', default_value='77'),
        DeclareLaunchArgument('partition', default_value='wheeltec-room'),
        SetEnvironmentVariable('ROS_LOCALHOST_ONLY','1'),
        SetEnvironmentVariable('ROS_DOMAIN_ID',LaunchConfiguration('ros_domain_id')),
        SetEnvironmentVariable('IGN_PARTITION',LaunchConfiguration('partition')),
        SetEnvironmentVariable('QT_QPA_PLATFORM','xcb'),
        SetEnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH',str(simulation/'models')+os.pathsep+os.environ.get('IGN_GAZEBO_RESOURCE_PATH','')),
        *handlers, gui, server, bridge, laser_tf,
        OpaqueFunction(function=algorithms, kwargs={'simulation':simulation}), rviz,
    ])
