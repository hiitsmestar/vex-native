$ErrorActionPreference = 'Stop'

$package = Split-Path -Parent $MyInvocation.MyCommand.Path
$bridgeSrc = Join-Path $package 'VexBridge.exe'
$remoteSrc = Join-Path $package 'VexRemoteSupport.exe'

if (!(Test-Path -LiteralPath $bridgeSrc)) { throw 'Package VexBridge.exe is missing' }
if (!(Test-Path -LiteralPath $remoteSrc)) { throw 'Package VexRemoteSupport.exe is missing' }

$downloads = Join-Path $env:USERPROFILE 'Downloads'
$candidates = Get-ChildItem -LiteralPath $downloads -Directory -ErrorAction SilentlyContinue | Where-Object {
    $hasLauncher = Test-Path -LiteralPath (Join-Path $_.FullName 'START-VEX-SELF-HEAL.cmd')
    $hasBridge = Test-Path -LiteralPath (Join-Path $_.FullName 'VexBridge.exe')
    ($hasLauncher -and $hasBridge)
}

$preferred = $candidates | Where-Object { $_.Name -like 'VexBridge-v0.11.0-Personal-Memory-Star-Seeded*' } | Select-Object -First 1
if (-not $preferred) { $preferred = $candidates | Select-Object -First 1 }
if (-not $preferred) { throw 'Could not find the current user-owned Vex folder under Downloads.' }

$dest = $preferred.FullName
$bridgeDst = Join-Path $dest 'VexBridge.exe'
$remoteDst = Join-Path $dest 'VexRemoteSupport.exe'

Write-Host "Installing Vex v0.11.7.13 into $dest"
Write-Host 'Stopping only Vex-owned Bridge/Remote Support/watchdog; no elevation is requested.'

$watchdogs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -like '*VexBridgeWatchdog.ps1*'
}
foreach ($p in $watchdogs) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Stop-Process -Name VexBridge,VexRemoteSupport -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Unblock-File -LiteralPath $bridgeSrc -ErrorAction SilentlyContinue
Unblock-File -LiteralPath $remoteSrc -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $bridgeSrc -Destination $bridgeDst -Force
Copy-Item -LiteralPath $remoteSrc -Destination $remoteDst -Force

$bridgeA = (Get-FileHash -LiteralPath $bridgeSrc -Algorithm SHA256).Hash
$bridgeB = (Get-FileHash -LiteralPath $bridgeDst -Algorithm SHA256).Hash
$remoteA = (Get-FileHash -LiteralPath $remoteSrc -Algorithm SHA256).Hash
$remoteB = (Get-FileHash -LiteralPath $remoteDst -Algorithm SHA256).Hash
if ($bridgeA -ne $bridgeB) { throw 'Bridge copy verification failed' }
if ($remoteA -ne $remoteB) { throw 'Remote Support copy verification failed' }

Write-Host 'SHA256 verified. Restarting one watchdog and Remote Support.'
$startHeal = Join-Path $dest 'START-VEX-SELF-HEAL.cmd'
if (Test-Path -LiteralPath $startHeal) {
    Start-Process -FilePath $startHeal -WorkingDirectory $dest
}
Start-Sleep -Seconds 3
Start-Process -FilePath $remoteDst -WorkingDirectory $dest

Write-Host ''
Write-Host 'Installed v0.11.7.13 without admin elevation.'
Write-Host 'Remote Support will verify the Bridge listener and perform one bounded recovery if needed.'
