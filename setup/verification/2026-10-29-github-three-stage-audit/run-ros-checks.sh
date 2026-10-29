#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
source /home/wheeltec/wheeltec_sim_ws/install/setup.bash
cd /mnt/d/虚拟c盘/WHEELTEC
report=setup/verification/2026-10-29-github-three-stage-audit
export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=94
python3 -m unittest discover -s robot -v > "$report/robot-tests.log" 2>&1
PYTHONPATH=src/wheeltec_explore python3 -m unittest discover -s src/wheeltec_explore/test -v > "$report/explorer-tests.log" 2>&1
python3 -m unittest discover -s simulation -v > "$report/simulation-tests.log" 2>&1
ros2 launch robot/launch/manual.launch.py --show-args > "$report/launch-help.log" 2>&1
ros2 launch robot/launch/robot.launch.py --show-args >> "$report/launch-help.log" 2>&1
python3 robot/watchdog.py --help >> "$report/launch-help.log" 2>&1
python3 -m console.target.adapter --help >> "$report/launch-help.log" 2>&1
for file in "$report/robot-tests.log" "$report/explorer-tests.log" "$report/simulation-tests.log"; do tail -n 5 "$file"; done
