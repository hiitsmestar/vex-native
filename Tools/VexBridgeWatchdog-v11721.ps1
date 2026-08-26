param([string]$BridgeExe = (Join-Path $PSScriptRoot 'VexBridge.exe'))
$ErrorActionPreference='Continue'
$created=$false
$mutex=New-Object System.Threading.Mutex($true,'Local\VexBridgeWatchdog-v11721',[ref]$created)
if(-not $created){ exit 0 }
$log=Join-Path $PSScriptRoot 'VexBridge-watchdog.log'
function Log([string]$m){ try{"[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),$m | Tee-Object -FilePath $log -Append}catch{} }
function Get-BridgeConfig {
  try { Get-Content (Join-Path $env:APPDATA 'VexBridge\config.json') -Raw | ConvertFrom-Json } catch { $null }
}
function Get-CandidatePorts($Cfg) {
  $external=if($Cfg -and $Cfg.port){[int]$Cfg.port}else{8765}
  $preferred=if($Cfg -and $Cfg.local_control_port){[int]$Cfg.local_control_port}else{($external+1)}
  $ports=@($preferred)
  foreach($p in (($external+1)..($external+12))){ if($ports -notcontains $p){ $ports += $p } }
  return $ports
}
function Test-LocalControlPort($Cfg,[int]$Port) {
  if(-not $Cfg -or -not $Cfg.token){ return $false }
  try {
    $u='http://127.0.0.1:'+ $Port +'/status?token='+[uri]::EscapeDataString([string]$Cfg.token)
    $r=Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 3 -Proxy $null
    if($r.StatusCode -ne 200){ return $false }
    $j=$r.Content | ConvertFrom-Json
    return (([string]$j.version -eq '0.11.7.21') -and ([string]$j.local_control_protocol -eq 'vex-local-v1'))
  } catch { return $false }
}
function Find-HealthyLocalPort($Cfg) {
  foreach($port in (Get-CandidatePorts $Cfg)){ if(Test-LocalControlPort $Cfg $port){ return [int]$port } }
  return 0
}
function Kill-Bridge {
  Get-Process -Name VexBridge -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Milliseconds 900
}
try {
  Log 'v0.11.7.21 restart-safe unified-control watchdog started.'
  $bad=0
  $restartGraceUntil=(Get-Date).AddSeconds(90)
  while($true){
    if(-not(Test-Path -LiteralPath $BridgeExe)){ Log 'Bridge executable missing.'; break }
    $cfg=Get-BridgeConfig
    $p=Get-Process -Name VexBridge -ErrorAction SilentlyContinue
    $healthyPort=0
    if($p){ $healthyPort=Find-HealthyLocalPort $cfg }
    if($healthyPort -gt 0){
      $bad=0
      $restartGraceUntil=(Get-Date).AddSeconds(30)
    } elseif((Get-Date) -lt $restartGraceUntil -and $p){
      Log 'Bridge process is inside startup grace; not restarting it.'
      $bad=0
    } else {
      $bad++
      Log ('Local control health failure '+$bad+' process='+[bool]$p)
      if($bad -ge 3){
        Kill-Bridge
        Log 'Restarting VexBridge.exe after sustained unified control failure.'
        try{ Start-Process -FilePath $BridgeExe -WorkingDirectory $PSScriptRoot | Out-Null }catch{ Log ('Launch error: '+$_.Exception.GetType().Name) }
        $bad=0
        $restartGraceUntil=(Get-Date).AddSeconds(90)
      }
    }
    Start-Sleep -Seconds 6
  }
} finally { try{$mutex.ReleaseMutex()}catch{}; $mutex.Dispose() }
