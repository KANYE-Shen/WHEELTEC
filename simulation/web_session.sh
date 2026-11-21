#!/usr/bin/env bash
set -e
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1
export ROS_DOMAIN_ID=218
export RCUTILS_LOGGING_USE_STDOUT=0
exec python3 -B "$(dirname -- "${BASH_SOURCE[0]}")/web_session.py"
