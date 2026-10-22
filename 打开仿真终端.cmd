@echo off
title WHEELTEC Simulation - Ubuntu 22.04
wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --cd /home/wheeltec/wheeltec_sim_ws
if errorlevel 1 pause
