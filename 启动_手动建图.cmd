@echo off
title WHEELTEC - Room simulation
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0simulation\Start-Room.ps1"
if errorlevel 1 pause
