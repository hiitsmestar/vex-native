param([string]$BridgeExe = (Join-Path $PSScriptRoot 'VexBridge.exe'))
$ErrorActionPreference='Continue'
$created=$false
$mutex=New-Object System.Threading.Mutex($true,'Local\VexBridgeWatchdog-v11719',[ref]$created)
if(-not $created){ exit 0 }
$log=Join-Path $PSScriptRoot 'VexBridge-watchdog.log'
function Log([string]$m){ try{"[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),$m | Tee-Object -FilePath $log -Append}catch{} }
function Get-BridgeConfig {
  try { Get-Content (Join-Path $env:APPDATA 'VexBridge\config.json') -Raw | ConvertFrom-Json } catch { $null }
}
function Test-BridgeTcp([int]$Port) {
  $c=New-Object System.Net.Sockets.TcpClient
  try { $ar=$c.BeginConnect('127.0.0.1',$Port,$null,$null); if(-not $ar.AsyncWaitHandle.WaitOne(2500)){ return $false }; $c.EndConnect($ar); return $true } catch { return $false } finally { try{$c.Close()}catch{} }
}
function Test-BridgeHttp($Cfg) {
  if(-not $Cfg -or -not $Cfg.token){ return $false }
  $port=if($Cfg.port){[int]$Cfg.port}else{8765}
  try {
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
    $u='https://127.0.0.1:'+ $port +'/status?token='+[uri]::EscapeDataString([string]$Cfg.token)
    $r=Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 4
    if($r.StatusCode -ne 200){ return $false }
    $j=$r.Content | ConvertFrom-Json
    return ([string]$j.version -eq '0.11.7.19')
  } catch { return $false }
}
function Kill-Bridge {
  Get-Process -Name VexBridge -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Milliseconds 700
}
try {
  Log 'v0.11.7.19 health-aware watchdog started.'
  $bad=0
  while($true){
    if(-not(Test-Path -LiteralPath $BridgeExe)){ Log 'Bridge executable missing.'; break }
    $cfg=Get-BridgeConfig; $port=if($cfg -and $cfg.port){[int]$cfg.port}else{8765}
    $p=Get-Process -Name VexBridge -ErrorAction SilentlyContinue
    $healthy=$false
    if($p){ $healthy=(Test-BridgeTcp $port) -and (Test-BridgeHttp $cfg) }
    if($healthy){ $bad=0 }
    else {
      $bad++
      Log ('Bridge health failure '+$bad+' process='+[bool]$p+' port='+$port)
      if($bad -ge 2){
        Kill-Bridge
        Log 'Restarting VexBridge.exe after failed live health checks.'
        try{ Start-Process -FilePath $BridgeExe -WorkingDirectory $PSScriptRoot | Out-Null }catch{ Log ('Launch error: '+$_.Exception.GetType().Name) }
        $bad=0
        Start-Sleep -Seconds 5
      }
    }
    Start-Sleep -Seconds 6
  }
} finally { try{$mutex.ReleaseMutex()}catch{}; $mutex.Dispose() }
