param(
    [string]$DropboxRoot = (Join-Path $HOME "Dropbox\VexRemoteBridge")
)
$ErrorActionPreference = "Stop"
$ParityRoot = Join-Path $env:LOCALAPPDATA "VexNative\DesktopParity"
$RepoAgent = Join-Path $PSScriptRoot "VexDropboxParityAgent.py"
$RepoHelper = Join-Path $PSScriptRoot "VexDropboxParityCall.mjs"
$Agent = Join-Path $ParityRoot "VexDropboxParityAgent.py"
$Helper = Join-Path $ParityRoot "dropbox-call.mjs"

if (!(Test-Path (Join-Path $ParityRoot "install-config.json"))) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Install-VexDesktopParity.ps1") -Mode Both -NoLan
}
New-Item -ItemType Directory -Force -Path $DropboxRoot | Out-Null
foreach ($name in @("commands","results","processing","failed")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $DropboxRoot $name) | Out-Null
}
Copy-Item -Force $RepoAgent $Agent
Copy-Item -Force $RepoHelper $Helper

$python = (Get-Command python.exe -ErrorAction Stop).Source
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$cmd = 'cmd.exe /c set "VEX_DROPBOX_PARITY_ROOT=' + $DropboxRoot + '" ^&^& "' + $python + '" "' + $Agent + '"'
New-Item -Path $runKey -Force | Out-Null
New-ItemProperty -Path $runKey -Name "VexDropboxParity" -Value $cmd -PropertyType String -Force | Out-Null

Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*VexDropboxParityAgent.py*" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
$env:VEX_DROPBOX_PARITY_ROOT = $DropboxRoot
Start-Process -FilePath $python -ArgumentList @($Agent) -WindowStyle Hidden
Start-Sleep -Seconds 2
$state = Join-Path $DropboxRoot "state.json"
if (!(Test-Path $state)) { throw "Dropbox parity agent did not create state.json" }
Write-Host "Vex Dropbox Desktop Parity bridge installed."
Write-Host "Bridge root: $DropboxRoot"
