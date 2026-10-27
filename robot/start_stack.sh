#!/bin/bash
set -euo pipefail
source /opt/ros/humble/setup.bash
source /opt/wheeltec_ws/install/setup.bash
exec ros2 launch /opt/wheeltec/robot/launch/robot.launch.py hardware:=/etc/wheeltec/robot.json explore:=false
