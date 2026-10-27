"""Nav2 navigation, with optional map-server / AMCL localization.

The room launch owns Gazebo, sensor bridging and (during mapping) SLAM.
"""
from pathlib import Path
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnShutdown
from launch.conditions import LaunchConfigurationEquals
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from nav2_common.launch import RewrittenYaml


def remove_generated(context, filename):
    Path(filename).unlink(missing_ok=True)
    return []

def generate_launch_description():
    bringup = Path(get_package_share_directory('nav2_bringup')) / 'launch'
    config = Path(__file__).resolve().parents[1] / 'config'
    # Humble rewrites YAML with ASCII escapes; its C++ parameter reader loses
    # Unicode path characters. Keep the source in the project and stage only
    # this generated runtime file under an ASCII /tmp path.
    with tempfile.NamedTemporaryFile(prefix='wheeltec-nav-', suffix='.xml', delete=False) as temporary:
        temporary.write((config/'navigate_wait.xml').read_bytes())
        behavior_tree = temporary.name
    params = RewrittenYaml(
        source_file=LaunchConfiguration('params_file'), root_key='',
        param_rewrites={'default_nav_to_pose_bt_xml': behavior_tree},
        convert_types=True)
    common = {
        'params_file': params,
        'use_sim_time': 'true',
        'autostart': 'true',
        'use_composition': 'False',
    }
    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(bringup / 'localization_launch.py')),
        launch_arguments={**common, 'map': LaunchConfiguration('map')}.items(),
        condition=LaunchConfigurationEquals('mode', 'localization'),
    )
    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(bringup / 'navigation_launch.py')),
        launch_arguments=common.items(),
    )
    return LaunchDescription([
        RegisterEventHandler(OnShutdown(on_shutdown=[
            OpaqueFunction(function=remove_generated, kwargs={'filename': behavior_tree})])),
        DeclareLaunchArgument('params_file',default_value=str(config/'nav2.yaml')),
        DeclareLaunchArgument('mode', default_value='mapping',
                              choices=['mapping', 'localization']),
        DeclareLaunchArgument('map', default_value='',
                              description='Absolute saved map YAML; required for localization.'),
        localization,
        navigation,
    ])
