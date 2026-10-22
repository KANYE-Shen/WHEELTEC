@echo off
title WHEELTEC - Keyboard control
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0simulation\Start-Teleop.ps1"
if errorlevel 1 pause