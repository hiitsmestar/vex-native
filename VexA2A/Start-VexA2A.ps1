$ErrorActionPreference='SilentlyContinue'
$port=if($env:VEX_A2A_PORT){[int]$env:VEX_A2A_PORT}else{8796}
$health="http://127.0.0.1:$port/health"
try { if((Invoke-RestMethod $health -TimeoutSec 2).ok){ exit 0 } } catch {}
$python=Join-Path $env:LOCALAPPDATA 'VexA2A\venv\Scripts\python.exe'
$server=Join-Path $env:LOCALAPPDATA 'VexA2A\server.py'
if(-not(Test-Path $python) -or -not(Test-Path $server)){ exit 2 }
$env:VEX_A2A_HOST='127.0.0.1'
$env:VEX_A2A_PORT=[string]$port
$env:VEX_A2A_MCP_URL='http://127.0.0.1:8795/mcp'
Start-Process -FilePath $python -ArgumentList @($server) -WindowStyle Hidden
$deadline=(Get-Date).AddSeconds(30)
while((Get-Date)-lt $deadline){
  Start-Sleep -Milliseconds 500
  try { if((Invoke-RestMethod $health -TimeoutSec 2).ok){ exit 0 } } catch {}
}
exit 3
