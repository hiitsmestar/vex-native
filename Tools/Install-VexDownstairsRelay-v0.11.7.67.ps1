$ErrorActionPreference = 'Stop'

$bundleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$installRoot = Join-Path $env:LOCALAPPDATA 'VexNative\DownstairsNode'
$remoteSrc = Join-Path $bundleRoot 'VexRemoteSupport'
$remoteDst = Join-Path $installRoot 'VexRemoteSupport'

Write-Host 'VexNative Downstairs Relay Stability v0.11.7.67'
Write-Host 'Installing Remote Support v0.11.7.67 with a 24-hour opt-in session window.'
Write-Host 'Existing Remote Support state/node identity will be preserved.'

if (!(Test-Path $remoteSrc)) { throw 'Missing VexRemoteSupport folder' }
New-Item -ItemType Directory -Force $installRoot | Out-Null

Get-Process VexRemoteSupport -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
if (Test-Path $remoteDst) { Remove-Item -Recurse -Force $remoteDst }
Copy-Item -Recurse $remoteSrc $remoteDst

$remoteExe = Join-Path $remoteDst 'VexRemoteSupport.exe'
if (!(Test-Path $remoteExe)) { throw 'Installed VexRemoteSupport.exe missing' }

# Keep the downstairs desktop awake while plugged in so it can serve as a secondary node.
& powercfg.exe /change standby-timeout-ac 0 | Out-Null
& powercfg.exe /change hibernate-timeout-ac 0 | Out-Null

$startup = [Environment]::GetFolderPath('Startup')
$ws = New-Object -ComObject WScript.Shell
$remoteLink = Join-Path $startup 'Vex Downstairs Remote Support.lnk'
$sc = $ws.CreateShortcut($remoteLink)
$sc.TargetPath = $remoteExe
$sc.WorkingDirectory = $remoteDst
$sc.Save()

Start-Process $remoteExe -WorkingDirectory $remoteDst
Start-Sleep -Seconds 5
$p = Get-Process VexRemoteSupport -ErrorAction SilentlyContinue
if (!$p) { throw 'VexRemoteSupport did not remain running after install' }

Write-Host ''
Write-Host 'Installed and started Remote Support v0.11.7.67.'
Write-Host 'AC sleep and AC hibernate timeout are now set to Never.'
Write-Host 'Bridge and NodeAgent were left untouched.'
Write-Host 'Start the Remote Support session once; the session window is now 24 hours.'
