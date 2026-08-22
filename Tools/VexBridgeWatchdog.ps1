param(
    [string]$BridgeExe = (Join-Path $PSScriptRoot "VexBridge.exe")
)

$ErrorActionPreference = "Continue"
$StopFile = Join-Path $PSScriptRoot "STOP-VEX-WATCHDOG"
$LogFile = Join-Path $PSScriptRoot "VexBridge-watchdog.log"

function Write-WatchdogLog([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch {}
}

if (-not (Test-Path $BridgeExe)) {
    Write-WatchdogLog "VexBridge.exe was not found at $BridgeExe"
    exit 2
}

Remove-Item $StopFile -Force -ErrorAction SilentlyContinue
$crashTimes = New-Object System.Collections.Generic.List[datetime]

Write-WatchdogLog "Self-healing process watchdog started. Close this watchdog window to stop supervision."

while ($true) {
    if (Test-Path $StopFile) {
        Remove-Item $StopFile -Force -ErrorAction SilentlyContinue
        Write-WatchdogLog "Stop flag found; watchdog exiting."
        break
    }

    $started = Get-Date
    Write-WatchdogLog "Starting VexBridge.exe"
    try {
        $process = Start-Process -FilePath $BridgeExe -WorkingDirectory $PSScriptRoot -PassThru
        $process.WaitForExit()
        $code = $process.ExitCode
    } catch {
        $code = -999
        Write-WatchdogLog "Launch error: $($_.Exception.Message)"
    }

    $runtime = ((Get-Date) - $started).TotalSeconds
    if (Test-Path $StopFile) {
        Remove-Item $StopFile -Force -ErrorAction SilentlyContinue
        Write-WatchdogLog "Stop flag found after Bridge exit; watchdog exiting."
        break
    }

    # A clean Ctrl+C / normal exit is treated as intentional. Unexpected exits
    # are restarted, with a circuit breaker so a native/DLL crash cannot loop forever.
    if ($code -eq 0) {
        Write-WatchdogLog "VexBridge exited cleanly; watchdog exiting."
        break
    }

    $now = Get-Date
    for ($i = $crashTimes.Count - 1; $i -ge 0; $i--) {
        if (($now - $crashTimes[$i]).TotalMinutes -gt 15) { $crashTimes.RemoveAt($i) }
    }
    $crashTimes.Add($now)

    Write-WatchdogLog "VexBridge exited unexpectedly with code $code after $([int]$runtime)s."
    if ($crashTimes.Count -ge 5) {
        Write-WatchdogLog "Five unexpected exits occurred within 15 minutes. Circuit breaker engaged; not restarting again automatically."
        break
    }

    $delay = [Math]::Min(30, [Math]::Max(3, [Math]::Pow(2, $crashTimes.Count)))
    Write-WatchdogLog "Restarting in $([int]$delay) seconds."
    Start-Sleep -Seconds $delay
}
