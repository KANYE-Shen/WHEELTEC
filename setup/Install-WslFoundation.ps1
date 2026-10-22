param(
    [string]$SetupRoot = 'D:\WSL\wheeltec-setup-20261022'
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell process.'
}

$installer = Join-Path $SetupRoot 'wsl.3.0.3.0.x64.msi'
$expectedHash = 'ae977286974255bd26bf925f00f40f5692c6b2084155cbc0563c09aea091f211'
$actualHash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) { throw 'WSL installer SHA256 mismatch.' }
$signature = Get-AuthenticodeSignature -LiteralPath $installer
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
    throw 'The installer must have a valid Microsoft Corporation signature.'
}

$resultPath = Join-Path $SetupRoot 'foundation-result.json'
$result = [ordered]@{
    Started = (Get-Date).ToString('o')
    MsiExitCode = $null
    FeatureStateBefore = $null
    FeatureStateAfter = $null
    RestartRequired = $false
    Success = $false
    Error = $null
}

try {
    $feature = Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
    $result.FeatureStateBefore = $feature.State.ToString()
    $msiLog = Join-Path $SetupRoot 'wsl-msi.log'
    $process = Start-Process -FilePath "$env:WINDIR\System32\msiexec.exe" -WindowStyle Hidden -Wait -PassThru -ArgumentList @(
        '/i', ('"' + $installer + '"'), '/passive', '/norestart', '/L*v', ('"' + $msiLog + '"')
    )
    $result.MsiExitCode = $process.ExitCode
    if ($process.ExitCode -notin @(0, 3010)) { throw "WSL MSI returned $($process.ExitCode). See $msiLog" }
    if ($process.ExitCode -eq 3010) { $result.RestartRequired = $true }

    if ($feature.State -ne 'Enabled') {
        $change = Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -All -NoRestart
        if ($change.RestartNeeded) { $result.RestartRequired = $true }
    }
    $result.FeatureStateAfter = (Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform).State.ToString()
    if ($result.FeatureStateAfter -eq 'EnablePending') { $result.RestartRequired = $true }
    $result.Success = $true
}
catch {
    $result.Error = $_.Exception.Message
}
finally {
    $result.Completed = (Get-Date).ToString('o')
    $result | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
}

if (-not $result.Success) { exit 1 }
if ($result.RestartRequired) { exit 3010 }
exit 0
