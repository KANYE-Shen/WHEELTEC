#!/bin/bash
set -euo pipefail
source /opt/ros/humble/setup.bash
exec python3 /opt/wheeltec/robot/operator_bridge.py
