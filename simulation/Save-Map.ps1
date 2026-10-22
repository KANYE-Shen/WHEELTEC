$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$linuxRoot = (& wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --exec wslpath -u (Split-Path -Parent $PSScriptRoot)).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the project directory in WSL.' }
& wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --exec bash -lc 'source /opt/ros/humble/setup.bash; export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=77; exec python3 "$1/simulation/save_map.py"' 'wheeltec-save' $linuxRoot
exit $LASTEXITCODE
