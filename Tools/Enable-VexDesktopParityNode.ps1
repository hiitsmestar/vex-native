param()
$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "VexNative\DesktopParity"
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Root "node-disabled.flag")
& powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File (Join-Path $Root "Start-VexDesktopParity.ps1")
Write-Host "Vex Desktop Parity node enabled."
