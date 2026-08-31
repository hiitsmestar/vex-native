$ErrorActionPreference = 'Stop'
$version = '0.11.7.69'
$installRoot = Join-Path $env:LOCALAPPDATA 'VexNative\RemoteSupport'
$sourceDir = Join-Path $PSScriptRoot 'VexRemoteSupport'
$destDir = Join-Path $installRoot 'VexRemoteSupport'
$sourceExe = Join-Path $sourceDir 'VexRemoteSupport.exe'
$destExe = Join-Path $destDir 'VexRemoteSupport.exe'
$startup = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startup 'Vex Remote Support.lnk'

if (!(Test-Path $sourceExe)) { throw 'VexRemoteSupport.exe is missing beside this installer.' }
Get-Process -Name 'VexRemoteSupport' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
if (Test-Path $destDir) { Remove-Item -Recurse -Force $destDir }
Copy-Item -Recurse -Force $sourceDir $destDir

$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $destExe
$shortcut.WorkingDirectory = $destDir
$shortcut.Description = "Vex Remote Support persistent relay v$version"
$shortcut.Save()

Start-Process $destExe -WorkingDirectory $destDir
Write-Host "Vex Remote Support v$version installed and started."
Write-Host 'Persistent-session preference and node identity are preserved in AppData.'
Write-Host 'Adds read-only sanitized self-improvement inspection for the upstairs adaptive worker.'
