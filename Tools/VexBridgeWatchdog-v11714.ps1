param([string]$BridgeExe = (Join-Path $PSScriptRoot 'VexBridge.exe'))
$ErrorActionPreference='Continue'
$created=$false
$mutex=New-Object System.Threading.Mutex($true,'Local\VexBridgeWatchdog-v11714',[ref]$created)
if(-not $created){ exit 0 }
$log=Join-Path $PSScriptRoot 'VexBridge-watchdog.log'
function Log([string]$m){ try{"[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),$m | Tee-Object -FilePath $log -Append}catch{} }
try{
  Log 'v0.11.7.14 singleton watchdog started.'
  while($true){
    if(-not(Test-Path -LiteralPath $BridgeExe)){ Log 'Bridge executable missing.'; break }
    $existing=Get-Process -Name VexBridge -ErrorAction SilentlyContinue
    if(-not $existing){
      Log 'Starting VexBridge.exe'
      try{ Start-Process -FilePath $BridgeExe -WorkingDirectory $PSScriptRoot | Out-Null }catch{ Log ('Launch error: '+$_.Exception.GetType().Name) }
    }
    Start-Sleep -Seconds 8
  }
} finally { try{$mutex.ReleaseMutex()}catch{}; $mutex.Dispose() }
