$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$projectRoot = Split-Path -Parent $PSScriptRoot
$linuxRoot = (& wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --exec wslpath -u $projectRoot).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the project directory in WSL.' }
& wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --cd /home/wheeltec/wheeltec_sim_ws --exec bash -lc 'source /opt/ros/humble/setup.bash && exec python3 "$1/simulation/teleop.py"' wheeltec-teleop $linuxRoot
exit $LASTEXITCODE