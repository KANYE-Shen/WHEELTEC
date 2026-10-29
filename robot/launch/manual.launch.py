"""Gated manual safety stack; sensor drivers remain externally managed."""
import json
import sys
import tempfile
from pathlib import Path
import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, ExecuteProcess, RegisterEventHandler, EmitEvent
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preflight import validate, calibrated_geometry


def configure(context):
    gate = int(LaunchConfiguration('gate').perform(context))
    hardware = LaunchConfiguration('hardware').perform(context)
    config = validate(json.loads(Path(hardware).read_text(
        encoding='utf-8')), required_gate=gate)
    calibration = json.loads(
        Path(config['calibration_file']).read_text(encoding='utf-8'))
    footprint, radius = calibrated_geometry(calibration)
    safety = config['safety']
    runtime = Path(tempfile.mkdtemp(prefix='wheeltec-manual-'))
    nav = yaml.safe_load((ROOT/'config/nav2.yaml').read_text(encoding='utf-8'))
    smoother = nav['velocity_smoother']['ros__parameters']
    smoother['odom_topic'] = config['odom_topic']
    smoother['use_sim_time'] = False
    smoother['max_velocity'] = [
        safety['max_linear_m_s'], 0., safety['max_yaw_rad_s']]
    smoother['min_velocity'] = [-safety['max_linear_m_s'],
                                0., -safety['max_yaw_rad_s']]
    collision = yaml.safe_load(
        (ROOT/'config/collision_monitor.yaml').read_text(encoding='utf-8'))
    c = collision['collision_monitor']['ros__parameters']
    c.update(base_frame_id=config['base_frame'],
             odom_frame_id=config['odom_frame'], use_sim_time=False)
    c['scan']['topic'] = config['scan_topic']
    # Stage-one braking is still being measured; this margin is not a stopping-distance claim.
    braking = config.get('measured_braking_distance_m') or 0.
    margin = braking+safety['obstacle_margin_m']
    x = max(abs(v[0]) for v in footprint)+margin
    y = max(abs(v[1]) for v in footprint)+margin
    c['StopZone']['points'] = [x, y, x, -y, -x, -y, -x, y]
    params = runtime/'smoother.yaml'
    params.write_text(yaml.safe_dump(
        {'velocity_smoother': {'ros__parameters': smoother}}))
    collision_path = runtime/'collision.yaml'
    collision_path.write_text(yaml.safe_dump(collision))
    actions = [Node(package='nav2_velocity_smoother', executable='velocity_smoother', name='velocity_smoother', parameters=[str(params)], remappings=[('cmd_vel', '/safety/nav_cmd_vel'), ('cmd_vel_smoothed', '/safety/smoothed_cmd_vel')], output='screen'),
               Node(package='nav2_collision_monitor', executable='collision_monitor',
                    name='collision_monitor', parameters=[str(collision_path)], output='screen'),
               Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager_manual', parameters=[
                    {'use_sim_time': False, 'autostart': True, 'node_names': ['velocity_smoother', 'collision_monitor']}], output='screen'),
               ExecuteProcess(cmd=['python3', str(ROOT/'watchdog.py'), '--config', hardware, '--gate', str(gate)], output='screen')]
    for action in list(actions):
        actions.insert(0, RegisterEventHandler(OnProcessExit(target_action=action, on_exit=[EmitEvent(
            event=Shutdown(reason='Manual safety process exited; driver expiry must stop wheels'))])))
    return actions


def generate_launch_description():
    return LaunchDescription([DeclareLaunchArgument('hardware', default_value=str(ROOT/'config/robot.json')), DeclareLaunchArgument('gate', default_value='1', choices=['1', '2']), OpaqueFunction(function=configure)])
