#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source /opt/ros/humble/setup.bash
args=(--kind robot --token-file "${WHEELTEC_CONSOLE_TOKEN_FILE:?Set a private token path}" --scan-topic "${WHEELTEC_SCAN_TOPIC:-/scan}" --odom-topic "${WHEELTEC_ODOM_TOPIC:-/odom}" --camera-topic "${WHEELTEC_CAMERA_TOPIC:-/image_raw}")
if [[ -n "${WHEELTEC_CONSOLE_ROBOT_CONFIG:-}" ]]; then
  args+=(--robot-config "$WHEELTEC_CONSOLE_ROBOT_CONFIG" --gate "${WHEELTEC_CONSOLE_GATE:?Explicit approved gate required}")
fi
exec python3 -m console.target.adapter "${args[@]}"
