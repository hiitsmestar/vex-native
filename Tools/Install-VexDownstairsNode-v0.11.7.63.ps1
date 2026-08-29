$ErrorActionPreference = 'Stop'

$bundleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$installRoot = Join-Path $env:LOCALAPPDATA 'VexNative\DownstairsNode'
$bridgeSrc = Join-Path $bundleRoot 'VexBridge'
$nodeSrc = Join-Path $bundleRoot 'VexNodeAgent'
$bridgeDst = Join-Path $installRoot 'VexBridge'
$nodeDst = Join-Path $installRoot 'VexNodeAgent'

Write-Host 'VexNative Downstairs Node v0.11.7.63 upgrade'
Write-Host 'Preserving existing AppData configuration and node identity.'

if (!(Test-Path $bridgeSrc)) { throw "Missing VexBridge folder" }
if (!(Test-Path $nodeSrc)) { throw "Missing VexNodeAgent folder" }

New-Item -ItemType Directory -Force $installRoot | Out-Null

Get-Process VexBridge,VexNodeAgent -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

if (Test-Path $bridgeDst) { Remove-Item -Recurse -Force $bridgeDst }
if (Test-Path $nodeDst) { Remove-Item -Recurse -Force $nodeDst }
Copy-Item -Recurse $bridgeSrc $bridgeDst
Copy-Item -Recurse $nodeSrc $nodeDst

$bridgeExe = Join-Path $bridgeDst 'VexBridge.exe'
$nodeExe = Join-Path $nodeDst 'VexNodeAgent.exe'
if (!(Test-Path $bridgeExe)) { throw "Installed VexBridge.exe missing" }
if (!(Test-Path $nodeExe)) { throw "Installed VexNodeAgent.exe missing" }

$startup = [Environment]::GetFolderPath('Startup')
$ws = New-Object -ComObject WScript.Shell

$bridgeLink = Join-Path $startup 'Vex Downstairs Bridge.lnk'
$sc = $ws.CreateShortcut($bridgeLink)
$sc.TargetPath = $bridgeExe
$sc.WorkingDirectory = $bridgeDst
$sc.Save()

$nodeLink = Join-Path $startup 'Vex Downstairs Node.lnk'
$sc = $ws.CreateShortcut($nodeLink)
$sc.TargetPath = $nodeExe
$sc.WorkingDirectory = $nodeDst
$sc.Save()

Start-Process $bridgeExe -WorkingDirectory $bridgeDst
Start-Sleep -Seconds 3
Start-Process $nodeExe -WorkingDirectory $nodeDst

Write-Host ''
Write-Host 'Installed and started:'
Write-Host "  Bridge: $bridgeExe"
Write-Host "  Node:   $nodeExe"
Write-Host ''
Write-Host 'Existing %APPDATA%\VexBridge and %APPDATA%\VexNode state was not deleted.'
Write-Host 'Leave both processes running for mesh discovery/verification.'
