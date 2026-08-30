$ErrorActionPreference = 'Stop'

$version = '0.11.7.66'
$installRoot = Join-Path $env:LOCALAPPDATA 'VexNative\PeerCoordinator'
$sourceDir = Join-Path $PSScriptRoot 'VexPeerCoordinator'
$destDir = Join-Path $installRoot 'VexPeerCoordinator'
$destExe = Join-Path $destDir 'VexPeerCoordinator.exe'
$startup = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startup 'Vex Peer Coordinator.lnk'
$logPath = Join-Path $env:APPDATA 'VexPeerCoordinator\coordinator.log'

if (!(Test-Path $sourceDir)) { throw 'VexPeerCoordinator folder is missing beside this installer.' }
if (!(Test-Path (Join-Path $sourceDir 'VexPeerCoordinator.exe'))) { throw 'VexPeerCoordinator.exe is missing from packaged folder.' }

Get-Process -Name 'VexPeerCoordinator' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
if (Test-Path $destDir) { Remove-Item -Recurse -Force $destDir }
Copy-Item -Recurse -Force $sourceDir $destDir

$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $destExe
$shortcut.WorkingDirectory = $destDir
$shortcut.Description = "VexNative dual-PC coordinator v$version"
$shortcut.Save()

$p = Start-Process $destExe -WorkingDirectory $destDir -PassThru
Start-Sleep -Seconds 8
if ($p.HasExited) {
  $tail = ''
  if (Test-Path $logPath) { $tail = (Get-Content $logPath -Tail 8 | Out-String) }
  throw "Vex Peer Coordinator exited during startup. Recent log:`n$tail"
}

Write-Host "Vex Peer Coordinator v$version installed and is still running after startup verification."
Write-Host "Role: upstairs-primary. Peer: downstairs node vex-8d8b20e0."
Write-Host "Startup diagnostics: $logPath"
