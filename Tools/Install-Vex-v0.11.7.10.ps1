$ErrorActionPreference = 'Stop'

$package = Split-Path -Parent $MyInvocation.MyCommand.Path
$bridgeSrc = Join-Path $package 'VexBridge.exe'
$remoteSrc = Join-Path $package 'VexRemoteSupport.exe'

if (!(Test-Path $bridgeSrc)) { throw "Package VexBridge.exe is missing" }
if (!(Test-Path $remoteSrc)) { throw "Package VexRemoteSupport.exe is missing" }

# Find the existing user-owned Vex folder. Never target Program Files and never request elevation.
$downloads = Join-Path $env:USERPROFILE 'Downloads'
$candidates = Get-ChildItem $downloads -Directory -ErrorAction SilentlyContinue | Where-Object {
    Test-Path (Join-Path $_.FullName 'START-VEX-SELF-HEAL.cmd') -and Test-Path (Join-Path $_.FullName 'VexBridge.exe')
}

$preferred = $candidates | Where-Object { $_.Name -like 'VexBridge-v0.11.0-Personal-Memory-Star-Seeded*' } | Select-Object -First 1
if (-not $preferred) { $preferred = $candidates | Select-Object -First 1 }
if (-not $preferred) { throw "Could not find the current user-owned Vex folder under Downloads." }

$dest = $preferred.FullName
Write-Host "Installing into: $dest"
Write-Host "Close the black self-heal watchdog window before continuing."

# Refuse to fight a live watchdog; this keeps replacement deterministic and avoids locked-file loops.
$running = Get-CimInstance Win32_Process -Filter "Name='VexBridge.exe'" -ErrorAction SilentlyContinue
if ($running) {
    Stop-Process -Name VexBridge -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

$bridgeDst = Join-Path $dest 'VexBridge.exe'
$remoteDst = Join-Path $dest 'VexRemoteSupport.exe'

Unblock-File $bridgeSrc -ErrorAction SilentlyContinue
Unblock-File $remoteSrc -ErrorAction SilentlyContinue
Copy-Item $bridgeSrc $bridgeDst -Force
Copy-Item $remoteSrc $remoteDst -Force

$bridgeA = (Get-FileHash $bridgeSrc -Algorithm SHA256).Hash
$bridgeB = (Get-FileHash $bridgeDst -Algorithm SHA256).Hash
$remoteA = (Get-FileHash $remoteSrc -Algorithm SHA256).Hash
$remoteB = (Get-FileHash $remoteDst -Algorithm SHA256).Hash
if ($bridgeA -ne $bridgeB) { throw 'Bridge copy verification failed' }
if ($remoteA -ne $remoteB) { throw 'Remote Support copy verification failed' }

Write-Host ''
Write-Host 'Installed and SHA256 verified.'
Write-Host 'Now run START-VEX-SELF-HEAL.cmd once, then start VexRemoteSupport.exe and begin a fresh 2-hour session.'
