param(
    [ValidateSet('mapping','localization','interfaces')][string]$Mode = 'mapping',
    [switch]$Explore,
    [ValidateSet('baseline','l_shape','clutter','bent_passage','recess')][string]$Scenario,
    [ValidateRange(0,2)][int]$Spawn = 0
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$projectRoot = Split-Path -Parent $PSScriptRoot
$interactiveScene = $Explore -and -not $PSBoundParameters.ContainsKey('Scenario')
if ($interactiveScene) {
    Write-Host ''
    Write-Host '自主探索建图：选择陌生房间布局'
    Write-Host '  1 原房间    2 L形房间    3 家具房间    4 弯通道    5 凹角房间'
    $scenes = @('baseline','l_shape','clutter','bent_passage','recess')
    do {
        $choice = Read-Host '布局编号（回车选择 1）'
        if ([string]::IsNullOrWhiteSpace($choice)) { $choice = '1' }
    } while ($choice -notmatch '^[1-5]$')
    $Scenario = $scenes[[int]$choice - 1]
}
if ($Explore -and -not $Scenario) { $Scenario = 'baseline' }
if ($interactiveScene -and -not $PSBoundParameters.ContainsKey('Spawn')) {
    $scenePath = Join-Path $PSScriptRoot "scenarios\$Scenario.json"
    $scene = Get-Content -LiteralPath $scenePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Host ''
    Write-Host '选择小车起点（位置与方向使用仿真房间坐标）'
    for ($i=0; $i -lt 3; $i++) {
        $pose = $scene.spawns[$i].pose
        $degrees = [Math]::Round([double]$pose[2] * 180 / [Math]::PI)
        Write-Host ("  起点 {0}：x={1} m，y={2} m，车头={3}°" -f $i,$pose[0],$pose[1],$degrees)
    }
    do {
        $choice = Read-Host '起点编号（回车选择 0）'
        if ([string]::IsNullOrWhiteSpace($choice)) { $choice = '0' }
    } while ($choice -notmatch '^[0-2]$')
    $Spawn = [int]$choice
}
if ($PSBoundParameters.ContainsKey('Spawn') -and -not $Scenario) {
    throw '-Spawn requires -Scenario.'
}
$linuxRoot = (& wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --exec wslpath -u $projectRoot).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the project directory in WSL.' }
$launchArguments = @("mode:=$Mode")
if ($Explore) { $launchArguments += 'explore:=true' }
if ($Scenario) { $launchArguments += @("scenario:=$Scenario","spawn:=$Spawn") }
& wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --cd /home/wheeltec/wheeltec_sim_ws --exec python3 "$linuxRoot/simulation/run_room.py" @launchArguments
exit $LASTEXITCODE
