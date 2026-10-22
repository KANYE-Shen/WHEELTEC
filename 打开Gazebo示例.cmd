@echo off
title WHEELTEC - Gazebo Fortress example
wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --cd /home/wheeltec/wheeltec_sim_ws --exec ign gazebo --render-engine-gui ogre -r shapes.sdf
if errorlevel 1 pause
