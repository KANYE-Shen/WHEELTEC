param(
    [ValidateSet('mapping','localization','interfaces')][string]$Mode = 'mapping',
    [switch]$Explore
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$projectRoot = Split-Path -Parent $PSScriptRoot
$linuxRoot = (& wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --exec wslpath -u $projectRoot).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the project directory in WSL.' }
$launchArguments = @("mode:=$Mode")
if ($Explore) { $launchArguments += 'explore:=true' }
& wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --cd /home/wheeltec/wheeltec_sim_ws --exec python3 "$linuxRoot/simulation/run_room.py" @launchArguments
exit $LASTEXITCODE
