"""Use vendor RRT candidates with the existing exploration task and Nav2."""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    params = str(Path(get_package_share_directory('wheeltec_robot_rrt'))/'config'/'exploration_params.yaml')
    remaps = [('/clicked_point','/wheeltec_explore/vendor_boundary'),
              ('/detected_frontiers','/wheeltec_explore/vendor_detected'),
              ('/filtered_goal_points','/wheeltec_explore/vendor_points')]
    nodes = [Node(package='wheeltec_robot_rrt', executable=name, name=name,
                  parameters=[params, {'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool)}],
                  remappings=remaps, output='screen') for name in ('global_rrt','local_rrt','filter')]
    nodes.append(Node(package='wheeltec_explore', executable='explore', name='wheeltec_explore',
                      parameters=[{'frontier_backend':'vendor',
                                   'vendor_bounds':ParameterValue(LaunchConfiguration('bounds'), value_type=str),
                                   'map_output':ParameterValue(LaunchConfiguration('map_output'), value_type=str),
                                   'use_sim_time':ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool),
                                   'base_frame':ParameterValue(LaunchConfiguration('base_frame'), value_type=str),
                                   'odom_frame':ParameterValue(LaunchConfiguration('odom_frame'), value_type=str),
                                   'robot_radius':ParameterValue(LaunchConfiguration('robot_radius'), value_type=float),
                                   'footprint_exclusion_radius':ParameterValue(LaunchConfiguration('footprint_exclusion_radius'), value_type=float),
                                   'update_latest':False}], output='screen'))
    guards = [RegisterEventHandler(OnProcessExit(target_action=node, on_exit=[
        EmitEvent(event=Shutdown(reason='Vendor exploration process exited'))])) for node in nodes]
    return LaunchDescription([DeclareLaunchArgument('bounds', description='xmin,ymin,xmax,ymax in map frame'),
                              DeclareLaunchArgument('map_output', description='New output path prefix for this task'),
                              DeclareLaunchArgument('use_sim_time'), DeclareLaunchArgument('base_frame'),
                              DeclareLaunchArgument('odom_frame'), DeclareLaunchArgument('robot_radius'),
                              DeclareLaunchArgument('footprint_exclusion_radius')] + guards + nodes)
