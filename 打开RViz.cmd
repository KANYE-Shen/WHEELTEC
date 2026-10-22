@echo off
title WHEELTEC - RViz
wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --cd /home/wheeltec/wheeltec_sim_ws --exec bash -lc "source /opt/ros/humble/setup.bash && export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=77 && exec rviz2"
if errorlevel 1 pause
