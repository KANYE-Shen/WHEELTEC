"""Start the project's room simulation from any working directory."""
import os
from pathlib import Path
import sys

launch_file = Path(__file__).resolve().parent / 'launch/room.launch.py'
os.execv('/bin/bash', ['bash', '-lc',
                      'source /opt/ros/humble/setup.bash && exec ros2 launch "$@"',
                      'wheeltec-room', str(launch_file), *sys.argv[1:]])
