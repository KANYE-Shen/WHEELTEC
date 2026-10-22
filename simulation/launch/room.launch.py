"""Launch the reference room and the ROS interfaces used by later SLAM/Nav2."""
import os
from pathlib import Path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, RegisterEventHandler, SetEnvironmentVariable
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    simulation = Path(__file__).resolve().parents[1]
    common = ['ign', 'gazebo', '-r', '-v', '3', '--render-engine', 'ogre']
    world = str(simulation / 'worlds/room_25m2.sdf')
    gui = ExecuteProcess(cmd=common + [world], output='screen',
                         condition=IfCondition(LaunchConfiguration('gui')))
    server = ExecuteProcess(cmd=common + ['-s', world], output='screen',
                            condition=UnlessCondition(LaunchConfiguration('gui')))
    bridge = Node(package='ros_gz_bridge', executable='parameter_bridge', name='room_bridge',
                  parameters=[{'config_file': str(simulation / 'config/bridge.yaml'),
                               'use_sim_time': True}], output='screen')
    laser_tf = Node(package='tf2_ros', executable='static_transform_publisher',
                    name='reference_laser_tf',
                    arguments=['--x', '0', '--y', '0', '--z', '0.25',
                               '--frame-id', 'base_link',
                               '--child-frame-id', 'wheeltec_reference/base_link/laser'],
                    parameters=[{'use_sim_time': True}], output='screen')
    rviz = Node(package='rviz2', executable='rviz2',
                arguments=['-d', str(simulation / 'config/room.rviz')],
                parameters=[{'use_sim_time': True}],
                condition=IfCondition(LaunchConfiguration('rviz')), output='screen')
    stop_handlers = [
        RegisterEventHandler(OnProcessExit(
            target_action=action,
            on_exit=[EmitEvent(event=Shutdown(reason='A required simulation process exited.'))]))
        for action in [gui, server, bridge]
    ]
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('partition', default_value='wheeltec-room'),
        SetEnvironmentVariable('ROS_LOCALHOST_ONLY', '1'),
        SetEnvironmentVariable('ROS_DOMAIN_ID', '77'),
        SetEnvironmentVariable('IGN_PARTITION', LaunchConfiguration('partition')),
        SetEnvironmentVariable('QT_QPA_PLATFORM', 'xcb'),
        SetEnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH',
                               str(simulation / 'models') + os.pathsep +
                               os.environ.get('IGN_GAZEBO_RESOURCE_PATH', '')),
        *stop_handlers, gui, server, bridge, laser_tf, rviz,
    ])
