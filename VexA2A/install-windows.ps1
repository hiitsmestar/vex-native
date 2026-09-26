param(
  [int]$Port = 8796,
  [string]$InstallRoot = "$env:LOCALAPPDATA\VexA2A"
)
$ErrorActionPreference='Stop'
$SourceRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Copy-Item "$SourceRoot\server.py" "$InstallRoot\server.py" -Force
Copy-Item "$SourceRoot\requirements.txt" "$InstallRoot\requirements.txt" -Force
if(-not (Get-Command py -ErrorAction SilentlyContinue)){throw "Python launcher 'py' was not found"}
$Venv=Join-Path $InstallRoot '.venv'
if(-not(Test-Path "$Venv\Scripts\python.exe")){& py -3 -m venv $Venv}
& "$Venv\Scripts\python.exe" -m pip install -r "$InstallRoot\requirements.txt"
if($LASTEXITCODE -ne 0){throw 'VexA2A dependency install failed'}

$Launcher=Join-Path $InstallRoot 'run-vexa2a.ps1'
@(
  '$env:VEXA2A_HOST="127.0.0.1"',
  ('$env:VEXA2A_PORT="' + $Port + '"'),
  ('$env:VEXBRIDGE_MCP_URL="http://127.0.0.1:8795/mcp"'),
  ('& "' + $Venv + '\Scripts\python.exe" "' + $InstallRoot + '\server.py"')
) | Set-Content $Launcher -Encoding UTF8

$Startup=Join-Path ([Environment]::GetFolderPath('Startup')) 'VexA2A.cmd'
@(
  '@echo off',
  ('start "" /min powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $Launcher + '"')
) | Set-Content $Startup -Encoding ASCII

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*$InstallRoot\server.py*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $Launcher + '"')

$deadline=(Get-Date).AddSeconds(45)
$ok=$false
while((Get-Date)-lt $deadline){
  Start-Sleep -Milliseconds 500
  try{
    $h=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
    if($h.ok -and $h.protocol -eq '1.0'){$ok=$true;break}
  }catch{}
}
if(-not $ok){throw 'VexA2A did not become healthy'}

$manifestDir=Join-Path $env:APPDATA 'VexNative'
New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
$path=Join-Path $manifestDir 'a2a.json'
@{
  schema='vexa2a-v1'
  protocol='1.0'
  endpoint=("http://127.0.0.1:$Port")
  bind='127.0.0.1'
  agents=@('coordinator','memory','verification','renderer','phone','coding')
  authority=@{
    continuity=(Join-Path $env:USERPROFILE 'Documents\VexContinuityVault')
    rule='A2A coordinates specialists; it does not replace continuity authority.'
  }
} | ConvertTo-Json -Depth 5 | Set-Content $path -Encoding UTF8

Write-Output "VEXA2A_INSTALL=PASS"
Write-Output "VEXA2A_ENDPOINT=http://127.0.0.1:$Port"
