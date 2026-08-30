$ErrorActionPreference = 'Stop'

$version = '0.11.7.65'
$installRoot = Join-Path $env:LOCALAPPDATA 'VexNative\PeerCoordinator'
$sourceExe = Join-Path $PSScriptRoot 'VexPeerCoordinator.exe'
$destExe = Join-Path $installRoot 'VexPeerCoordinator.exe'
$startup = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startup 'Vex Peer Coordinator.lnk'

if (!(Test-Path $sourceExe)) { throw "VexPeerCoordinator.exe is missing beside this installer." }

Get-Process -Name 'VexPeerCoordinator' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
Copy-Item -Force $sourceExe $destExe

$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $destExe
$shortcut.WorkingDirectory = $installRoot
$shortcut.Description = "VexNative dual-PC coordinator v$version"
$shortcut.Save()

Start-Process $destExe -WorkingDirectory $installRoot
Write-Host "Vex Peer Coordinator v$version installed and started."
Write-Host "Role: upstairs-primary. Peer: preserved downstairs node vex-8d8b20e0."
Write-Host "It performs sanitized health/availability coordination through the existing Vex relay; no chat content is relayed."
