$ErrorActionPreference = 'Stop'

$bundleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$installRoot = Join-Path $env:LOCALAPPDATA 'VexNative\DownstairsNode'
$remoteSrc = Join-Path $bundleRoot 'VexRemoteSupport'
$remoteDst = Join-Path $installRoot 'VexRemoteSupport'

Write-Host 'VexNative Downstairs Relay Repair v0.11.7.64'
Write-Host 'Installing Remote Support v0.11.7.62 beside the existing .63 Bridge + NodeAgent.'
Write-Host 'Existing %APPDATA% Remote Support state/node identity will be preserved.'

if (!(Test-Path $remoteSrc)) { throw 'Missing VexRemoteSupport folder' }

New-Item -ItemType Directory -Force $installRoot | Out-Null

Get-Process VexRemoteSupport -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

if (Test-Path $remoteDst) { Remove-Item -Recurse -Force $remoteDst }
Copy-Item -Recurse $remoteSrc $remoteDst

$remoteExe = Join-Path $remoteDst 'VexRemoteSupport.exe'
if (!(Test-Path $remoteExe)) { throw 'Installed VexRemoteSupport.exe missing' }

$startup = [Environment]::GetFolderPath('Startup')
$ws = New-Object -ComObject WScript.Shell
$remoteLink = Join-Path $startup 'Vex Downstairs Remote Support.lnk'
$sc = $ws.CreateShortcut($remoteLink)
$sc.TargetPath = $remoteExe
$sc.WorkingDirectory = $remoteDst
$sc.Save()

Start-Process $remoteExe -WorkingDirectory $remoteDst
Start-Sleep -Seconds 4

$p = Get-Process VexRemoteSupport -ErrorAction SilentlyContinue
if (!$p) { throw 'VexRemoteSupport did not remain running after install' }

Write-Host ''
Write-Host 'Installed and started:'
Write-Host "  Remote Support: $remoteExe"
Write-Host ''
Write-Host 'The existing .63 Bridge and NodeAgent were left untouched.'
Write-Host 'Leave this PC awake and logged in for live relay verification.'
