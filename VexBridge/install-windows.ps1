param([int]$Port = 8795, [int]$A2APort = 8800, [switch]$SkipRelay, [switch]$SkipA2A)
$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallRoot = Join-Path $env:LOCALAPPDATA 'VexBridgeMCP'
$McpSource = Join-Path $SourceRoot 'VexBridgeMCP'
$RelaySource = Join-Path $SourceRoot 'VexBridgeRelay'
$ClientSource = Join-Path $SourceRoot 'VexBridgeRelayClient'
$A2ASource = Join-Path $SourceRoot 'VexA2A'

if(-not (Test-Path (Join-Path $McpSource 'VexBridgeMCP.exe'))){
  throw 'VexBridgeMCP packaged folder is missing.'
}
if(-not $SkipRelay -and -not (Test-Path (Join-Path $RelaySource 'VexBridgeRelay.exe'))){
  throw 'VexBridgeRelay packaged folder is missing.'
}
if(-not (Test-Path (Join-Path $ClientSource 'VexBridgeRelayClient.exe'))){
  throw 'VexBridgeRelayClient packaged folder is missing.'
}
if(-not $SkipA2A -and -not (Test-Path (Join-Path $A2ASource 'VexA2A.exe'))){
  throw 'VexA2A packaged folder is missing.'
}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -eq 'VexBridgeMCP.exe' -and $_.ExecutablePath -like "$InstallRoot*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
if(-not $SkipA2A){
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq 'VexA2A.exe' -and $_.ExecutablePath -like "$InstallRoot*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
if(-not $SkipRelay){
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq 'VexBridgeRelay.exe' -or $_.CommandLine -like '*relay_worker.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
Start-Sleep -Milliseconds 500
$Stage = Join-Path $env:TEMP ("VexBridgeMCP-install-" + $PID)
Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
Copy-Item $McpSource (Join-Path $Stage 'MCP') -Recurse -Force
Copy-Item $ClientSource (Join-Path $Stage 'Client') -Recurse -Force
if(-not $SkipA2A){ Copy-Item $A2ASource (Join-Path $Stage 'A2A') -Recurse -Force }
if(-not $SkipRelay){ Copy-Item $RelaySource (Join-Path $Stage 'Relay') -Recurse -Force }

Remove-Item $InstallRoot -Recurse -Force -ErrorAction SilentlyContinue
Move-Item $Stage $InstallRoot

$ConfigDir = Join-Path $env:APPDATA 'VexBridgeDC'
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
$Roots = @(Get-PSDrive -PSProvider FileSystem | ForEach-Object { $_.Root } | Where-Object { $_ })
$Config = @{
  allowedDirectories = $Roots
  allowedRoots = $Roots
  fileReadLineLimit = 1000
  fileWriteLineLimit = 30
  searchResultLimit = 500
  blockedCommands = @()
  defaultShell = ''
  telemetryEnabled = $false
} | ConvertTo-Json -Depth 5
Set-Content -Path (Join-Path $ConfigDir 'config.json') -Value $Config -Encoding UTF8

$Startup = [Environment]::GetFolderPath('Startup')
$McpStartup = Join-Path $Startup 'VexBridgeMCP.cmd'
$McpLines = @(
  '@echo off',
  'set VEXBRIDGE_HOST=127.0.0.1',
  ('set VEXBRIDGE_PORT=' + $Port),
  ('start "" /min "' + (Join-Path $InstallRoot 'MCP\VexBridgeMCP.exe') + '"')
)
Set-Content -Path $McpStartup -Value $McpLines -Encoding ASCII

$env:VEXBRIDGE_HOST = '127.0.0.1'
$env:VEXBRIDGE_PORT = [string]$Port
$McpExe = Join-Path $InstallRoot 'MCP\VexBridgeMCP.exe'
Start-Process -FilePath $McpExe -WindowStyle Hidden

$Ready = $false
for($i=0;$i -lt 30;$i++){
  Start-Sleep -Milliseconds 500
  try {
    $tcp=[Net.Sockets.TcpClient]::new('127.0.0.1',$Port)
    $tcp.Close(); $Ready=$true; break
  } catch {}
}
if(-not $Ready){ throw "VexBridgeMCP did not listen on port $Port" }

$A2AStarted = $false
if(-not $SkipA2A){
  $A2AExe = Join-Path $InstallRoot 'A2A\VexA2A.exe'
  $A2AStartup = Join-Path $Startup 'VexA2A.cmd'
  $A2ALines = @(
    '@echo off',
    'set VEX_A2A_HOST=127.0.0.1',
    ('set VEX_A2A_PORT=' + $A2APort),
    ('set VEX_A2A_BASE_URL=http://127.0.0.1:' + $A2APort),
    ('set VEXBRIDGE_MCP_URL=http://127.0.0.1:' + $Port + '/mcp'),
    ('start "" /min "' + $A2AExe + '"')
  )
  Set-Content -Path $A2AStartup -Value $A2ALines -Encoding ASCII
  $env:VEX_A2A_HOST='127.0.0.1'
  $env:VEX_A2A_PORT=[string]$A2APort
  $env:VEX_A2A_BASE_URL="http://127.0.0.1:$A2APort"
  $env:VEXBRIDGE_MCP_URL="http://127.0.0.1:$Port/mcp"
  Start-Process -FilePath $A2AExe -WindowStyle Hidden
  $deadline=(Get-Date).AddSeconds(30)
  while((Get-Date)-lt $deadline){
    Start-Sleep -Milliseconds 500
    try {
      $r=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$A2APort/health" -TimeoutSec 2
      if($r.StatusCode -eq 200){ $A2AStarted=$true; break }
    } catch {}
  }
  if(-not $A2AStarted){ throw "VexA2A did not become healthy on port $A2APort" }
}

$RelayStarted = $false
if(-not $SkipRelay){
  $GhCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\GitHubCLI\bin\gh.exe'),
    (Join-Path $env:LOCALAPPDATA 'VexBridgeBootstrap\gh\bin\gh.exe'),
    'C:\Program Files\GitHub CLI\gh.exe'
  )
  $Gh = $GhCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
  if($Gh){
    & $Gh auth status 1>$null 2>$null
    if($LASTEXITCODE -eq 0){
      $RelayExe = Join-Path $InstallRoot 'Relay\VexBridgeRelay.exe'
      $RelayStartup = Join-Path $Startup 'VexBridgeRelay.cmd'
      Set-Content -Path $RelayStartup -Value @('@echo off',('start "" /min "'+$RelayExe+'"')) -Encoding ASCII
      Start-Process -FilePath $RelayExe -WindowStyle Hidden
      $RelayStatus = Join-Path $ConfigDir 'relay-status.json'
      $RelayDeadline = (Get-Date).AddSeconds(30)
      while((Get-Date) -lt $RelayDeadline){
        Start-Sleep -Milliseconds 500
        if(Test-Path $RelayStatus){
          try {
            $Status = Get-Content $RelayStatus -Raw | ConvertFrom-Json
            if($Status.running -eq $true -and $Status.ok -eq $true -and $Status.node){
              $RelayStarted = $true
              break
            }
          } catch {}
        }
      }
      if(-not $RelayStarted){
        throw 'Encrypted relay launched but did not report healthy status within 30 seconds.'
      }
    }
  }
}

Write-Host "VexBridgeMCP installed: $McpExe"
Write-Host "Local MCP endpoint: http://127.0.0.1:$Port/mcp"
Write-Host ("Relay client: " + (Join-Path $InstallRoot 'Client\VexBridgeRelayClient.exe'))
Write-Host ("Allowed roots: " + ($Roots -join ', '))
if($SkipRelay){ Write-Host 'Encrypted relay skipped by request.' }
elseif($RelayStarted){ Write-Host 'Encrypted GitHub relay started and persisted.' }
else { Write-Host 'Encrypted relay packaged but not started because authenticated GitHub CLI was not found.' }
