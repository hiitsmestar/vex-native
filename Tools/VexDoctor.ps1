param(
    [switch]$NoOpen,
    [int]$TimeoutSeconds = 5
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$BridgeRoot = Join-Path $env:APPDATA "VexBridge"
$BridgeConfig = Join-Path $BridgeRoot "config.json"
$DiagnosticRoot = Join-Path $BridgeRoot "diagnostics"
$ArtRoot = Join-Path $env:LOCALAPPDATA "VexArt"
$ComfyRoot = Join-Path $ArtRoot "ComfyUI"
$ArtPython = Join-Path $ArtRoot "venv\Scripts\python.exe"
$ArtCheckpoint = Join-Path $ComfyRoot "models\checkpoints\RealVisXL_V5.0_Lightning_fp16.safetensors"
$ArtErrorLog = Join-Path $ArtRoot "comfyui-render-errors.log"
$LearningDb = Join-Path $BridgeRoot "learning\vex-learning.sqlite3"

New-Item -ItemType Directory -Force -Path $DiagnosticRoot | Out-Null

$script:Checks = New-Object System.Collections.ArrayList

function Add-Check {
    param(
        [string]$Id,
        [string]$Component,
        [ValidateSet("OK","WARN","FAIL","INFO")][string]$Status,
        [string]$Summary,
        $Details = $null
    )
    $entry = [ordered]@{
        id = $Id
        component = $Component
        status = $Status
        summary = $Summary
        details = $Details
    }
    [void]$script:Checks.Add([pscustomobject]$entry)

    $glyph = switch ($Status) {
        "OK"   { "[ OK ]" }
        "WARN" { "[WARN]" }
        "FAIL" { "[FAIL]" }
        default { "[INFO]" }
    }
    Write-Host ("{0} {1}: {2}" -f $glyph, $Component, $Summary)
}

function Test-TcpListener {
    param([int]$Port)
    try {
        $connections = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
        if ($connections) {
            return [pscustomobject]@{ Listening = $true; Pids = @($connections | Select-Object -ExpandProperty OwningProcess -Unique) }
        }
    } catch {
        try {
            $pattern = ":$Port\s+.*LISTENING\s+(\d+)"
            $hits = @(netstat -ano -p tcp 2>$null | Select-String -Pattern $pattern)
            if ($hits.Count -gt 0) {
                $pids = @()
                foreach ($hit in $hits) {
                    if ($hit.Matches.Count -gt 0) { $pids += [int]$hit.Matches[0].Groups[1].Value }
                }
                return [pscustomobject]@{ Listening = $true; Pids = @($pids | Select-Object -Unique) }
            }
        } catch {}
    }
    return [pscustomobject]@{ Listening = $false; Pids = @() }
}

function Invoke-LocalJson {
    param(
        [string]$Uri,
        [int]$Timeout = 5,
        [switch]$AllowSelfSigned
    )

    $oldCallback = $null
    $changedCallback = $false
    try {
        if ($AllowSelfSigned) {
            $oldCallback = [System.Net.ServicePointManager]::ServerCertificateValidationCallback
            [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
            $changedCallback = $true
        }
        return Invoke-RestMethod -Uri $Uri -Method Get -TimeoutSec $Timeout -ErrorAction Stop
    } finally {
        if ($changedCallback) {
            [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $oldCallback
        }
    }
}

function Get-ProcessSnapshot {
    param([string]$Name)
    try {
        $items = @(Get-CimInstance Win32_Process -Filter "Name='$Name'" -ErrorAction Stop)
        return @($items | ForEach-Object {
            [pscustomobject]@{
                pid = $_.ProcessId
                executable = $_.ExecutablePath
                commandLine = $_.CommandLine
            }
        })
    } catch {
        return @()
    }
}

function Read-TailSafe {
    param([string]$Path, [int]$Lines = 20)
    try {
        if (Test-Path $Path) {
            return @((Get-Content -Path $Path -Tail $Lines -ErrorAction Stop) | ForEach-Object { [string]$_ })
        }
    } catch {}
    return @()
}

Write-Host ""
Write-Host "Vex Doctor v0.1" -ForegroundColor Magenta
Write-Host "================" -ForegroundColor Magenta
Write-Host "Independent diagnostics - evidence first, no language-model guesses." -ForegroundColor DarkGray
Write-Host ""

# ---------------------------------------------------------------------------
# Host snapshot
# ---------------------------------------------------------------------------
$os = $null
$cpu = $null
try { $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop } catch {}
try { $cpu = Get-CimInstance Win32_Processor -ErrorAction Stop | Select-Object -First 1 } catch {}

$hostInfo = [ordered]@{
    computerName = $env:COMPUTERNAME
    userName = $env:USERNAME
    userProfile = $env:USERPROFILE
    os = if ($os) { $os.Caption } else { [System.Environment]::OSVersion.VersionString }
    osVersion = if ($os) { $os.Version } else { [System.Environment]::OSVersion.Version.ToString() }
    cpu = if ($cpu) { $cpu.Name } else { $null }
    logicalProcessors = if ($cpu) { $cpu.NumberOfLogicalProcessors } else { [Environment]::ProcessorCount }
    totalRamGB = if ($os) { [math]::Round(([double]$os.TotalVisibleMemorySize * 1KB / 1GB), 2) } else { $null }
    freeRamGB = if ($os) { [math]::Round(([double]$os.FreePhysicalMemory * 1KB / 1GB), 2) } else { $null }
}
Add-Check -Id "host" -Component "Windows host" -Status "INFO" -Summary ("{0} / {1} / {2} logical CPUs" -f $hostInfo.computerName, $hostInfo.userName, $hostInfo.logicalProcessors) -Details $hostInfo

$drives = @()
try {
    $drives = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction Stop | ForEach-Object {
        [pscustomobject]@{
            drive = $_.DeviceID
            sizeGB = if ($_.Size) { [math]::Round([double]$_.Size / 1GB, 1) } else { 0 }
            freeGB = if ($_.FreeSpace) { [math]::Round([double]$_.FreeSpace / 1GB, 1) } else { 0 }
            freePercent = if ($_.Size) { [math]::Round(([double]$_.FreeSpace / [double]$_.Size) * 100, 1) } else { 0 }
        }
    })
    $low = @($drives | Where-Object { $_.freePercent -lt 8 })
    if ($low.Count -gt 0) {
        Add-Check -Id "disk-space" -Component "Disk space" -Status "WARN" -Summary "One or more fixed drives are below 8% free space." -Details $drives
    } else {
        Add-Check -Id "disk-space" -Component "Disk space" -Status "OK" -Summary "Fixed-drive free space is not critically low." -Details $drives
    }
} catch {
    Add-Check -Id "disk-space" -Component "Disk space" -Status "WARN" -Summary "Could not collect fixed-drive space." -Details $_.Exception.Message
}

# ---------------------------------------------------------------------------
# Bridge config, process, listener, authenticated status
# ---------------------------------------------------------------------------
$bridgeCfg = $null
$bridgePort = 8765
$bridgeToken = $null
if (Test-Path $BridgeConfig) {
    try {
        $bridgeCfg = Get-Content -Raw -Path $BridgeConfig -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        if ($bridgeCfg.port) { $bridgePort = [int]$bridgeCfg.port }
        $bridgeToken = [string]$bridgeCfg.token
        Add-Check -Id "bridge-config" -Component "Bridge config" -Status "OK" -Summary ("Config parsed; port {0}. Token present: {1}." -f $bridgePort, [bool]$bridgeToken) -Details @{ path = $BridgeConfig; tokenRedacted = $true }
    } catch {
        Add-Check -Id "bridge-config" -Component "Bridge config" -Status "FAIL" -Summary "config.json exists but could not be parsed." -Details $_.Exception.Message
    }
} else {
    Add-Check -Id "bridge-config" -Component "Bridge config" -Status "FAIL" -Summary "VexBridge config.json was not found." -Details @{ path = $BridgeConfig }
}

$bridgeProcesses = @(Get-ProcessSnapshot -Name "VexBridge.exe")
if ($bridgeProcesses.Count -gt 0) {
    Add-Check -Id "bridge-process" -Component "Bridge process" -Status "OK" -Summary ("VexBridge.exe is running ({0} process(es))." -f $bridgeProcesses.Count) -Details $bridgeProcesses
} else {
    Add-Check -Id "bridge-process" -Component "Bridge process" -Status "FAIL" -Summary "VexBridge.exe is not running." -Details $null
}

$bridgeListener = Test-TcpListener -Port $bridgePort
if ($bridgeListener.Listening) {
    Add-Check -Id "bridge-port" -Component "Bridge listener" -Status "OK" -Summary ("TCP port {0} is listening." -f $bridgePort) -Details @{ port = $bridgePort; pids = $bridgeListener.Pids }
} else {
    Add-Check -Id "bridge-port" -Component "Bridge listener" -Status "FAIL" -Summary ("Nothing is listening on configured Bridge port {0}." -f $bridgePort) -Details @{ port = $bridgePort }
}

$bridgeStatus = $null
if ($bridgeToken -and $bridgeListener.Listening) {
    try {
        $encodedToken = [Uri]::EscapeDataString($bridgeToken)
        $bridgeStatus = Invoke-LocalJson -Uri ("https://127.0.0.1:{0}/status?token={1}" -f $bridgePort, $encodedToken) -Timeout $TimeoutSeconds -AllowSelfSigned
        Add-Check -Id "bridge-status" -Component "Bridge API" -Status "OK" -Summary "Authenticated /status returned successfully." -Details $bridgeStatus
    } catch {
        Add-Check -Id "bridge-status" -Component "Bridge API" -Status "FAIL" -Summary "Bridge port is reachable but authenticated /status failed." -Details $_.Exception.Message
    }
} else {
    Add-Check -Id "bridge-status" -Component "Bridge API" -Status "FAIL" -Summary "Authenticated Bridge health could not be tested because config/token/listener is unavailable." -Details $null
}

# ---------------------------------------------------------------------------
# Ollama / cognition
# ---------------------------------------------------------------------------
$ollamaPayload = $null
try {
    $ollamaPayload = Invoke-LocalJson -Uri "http://127.0.0.1:11434/api/tags" -Timeout $TimeoutSeconds
    $models = @($ollamaPayload.models | ForEach-Object { [string]($_.name) })
    Add-Check -Id "ollama-api" -Component "Ollama" -Status "OK" -Summary ("Ollama answered; {0} model(s) installed." -f $models.Count) -Details @{ models = $models }
} catch {
    Add-Check -Id "ollama-api" -Component "Ollama" -Status "FAIL" -Summary "Ollama did not answer on 127.0.0.1:11434." -Details $_.Exception.Message
}

if ($bridgeToken -and $bridgeListener.Listening) {
    try {
        $encodedToken = [Uri]::EscapeDataString($bridgeToken)
        $llm = Invoke-LocalJson -Uri ("https://127.0.0.1:{0}/llm/status?token={1}" -f $bridgePort, $encodedToken) -Timeout ([math]::Max($TimeoutSeconds, 8)) -AllowSelfSigned
        if ($llm.ok) {
            Add-Check -Id "cognition-route" -Component "PC cognition" -Status "OK" -Summary ("Bridge /llm/status reports model: {0}" -f $llm.model) -Details $llm
        } else {
            Add-Check -Id "cognition-route" -Component "PC cognition" -Status "FAIL" -Summary "Bridge /llm/status answered but reports no usable local model." -Details $llm
        }
    } catch {
        Add-Check -Id "cognition-route" -Component "PC cognition" -Status "FAIL" -Summary "Bridge /llm/status did not complete." -Details $_.Exception.Message
    }
}

# ---------------------------------------------------------------------------
# Art installation and live ComfyUI health
# ---------------------------------------------------------------------------
$artInstall = [ordered]@{
    comfyMain = Test-Path (Join-Path $ComfyRoot "main.py")
    python = Test-Path $ArtPython
    checkpoint = Test-Path $ArtCheckpoint
    comfyRoot = $ComfyRoot
    pythonPath = $ArtPython
    checkpointPath = $ArtCheckpoint
}
if ($artInstall.comfyMain -and $artInstall.python -and $artInstall.checkpoint) {
    Add-Check -Id "art-install" -Component "Vex Art install" -Status "OK" -Summary "ComfyUI, VexArt Python, and target checkpoint are present." -Details $artInstall
} elseif ($artInstall.comfyMain -and $artInstall.python) {
    Add-Check -Id "art-install" -Component "Vex Art install" -Status "WARN" -Summary "ComfyUI/Python are present but the target checkpoint is missing." -Details $artInstall
} else {
    Add-Check -Id "art-install" -Component "Vex Art install" -Status "FAIL" -Summary "Vex Art installation is incomplete." -Details $artInstall
}

try {
    $comfyStats = Invoke-LocalJson -Uri "http://127.0.0.1:8188/system_stats" -Timeout $TimeoutSeconds
    Add-Check -Id "comfy-live" -Component "ComfyUI live API" -Status "OK" -Summary "ComfyUI /system_stats answered on port 8188." -Details $comfyStats
} catch {
    $status = if ($artInstall.comfyMain -and $artInstall.python) { "INFO" } else { "FAIL" }
    Add-Check -Id "comfy-live" -Component "ComfyUI live API" -Status $status -Summary "ComfyUI is not currently answering on port 8188. This is normal when the on-demand art app is idle." -Details $_.Exception.Message
}

if (Test-Path $ArtErrorLog) {
    try {
        $item = Get-Item $ArtErrorLog -ErrorAction Stop
        Add-Check -Id "art-error-log" -Component "Art execution log" -Status "INFO" -Summary ("Render error log exists; last write {0}." -f $item.LastWriteTime) -Details @{ path = $ArtErrorLog; tail = @(Read-TailSafe -Path $ArtErrorLog -Lines 8) }
    } catch {}
} else {
    Add-Check -Id "art-error-log" -Component "Art execution log" -Status "INFO" -Summary "No detailed ComfyUI render-error log exists yet." -Details @{ path = $ArtErrorLog }
}

# ---------------------------------------------------------------------------
# Learning store
# ---------------------------------------------------------------------------
if (Test-Path $LearningDb) {
    try {
        $learningItem = Get-Item $LearningDb -ErrorAction Stop
        Add-Check -Id "learning-db" -Component "Learning store" -Status "OK" -Summary ("SQLite knowledge store exists; {0:N1} KB, last write {1}." -f ($learningItem.Length / 1KB), $learningItem.LastWriteTime) -Details @{ path = $LearningDb; bytes = $learningItem.Length; lastWrite = $learningItem.LastWriteTime }
    } catch {
        Add-Check -Id "learning-db" -Component "Learning store" -Status "WARN" -Summary "Learning database exists but metadata could not be read." -Details $_.Exception.Message
    }
} else {
    Add-Check -Id "learning-db" -Component "Learning store" -Status "WARN" -Summary "Learning SQLite database has not been created yet." -Details @{ path = $LearningDb }
}

if ($bridgeToken -and $bridgeListener.Listening) {
    try {
        $encodedToken = [Uri]::EscapeDataString($bridgeToken)
        $learningStatus = Invoke-LocalJson -Uri ("https://127.0.0.1:{0}/learning/status?token={1}" -f $bridgePort, $encodedToken) -Timeout $TimeoutSeconds -AllowSelfSigned
        Add-Check -Id "learning-route" -Component "Learning engine" -Status "OK" -Summary "Bridge /learning/status answered." -Details $learningStatus
    } catch {
        Add-Check -Id "learning-route" -Component "Learning engine" -Status "INFO" -Summary "The optional /learning/status probe did not answer; the database check above remains independent evidence." -Details $_.Exception.Message
    }
}

# ---------------------------------------------------------------------------
# Watchdog evidence
# ---------------------------------------------------------------------------
$watchdogs = @()
try {
    $watchdogs = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        $_.Name -match "^(powershell|pwsh)\.exe$" -and $_.CommandLine -match "VexBridgeWatchdog\.ps1"
    } | ForEach-Object {
        [pscustomobject]@{ pid = $_.ProcessId; commandLine = $_.CommandLine }
    })
} catch {}

if ($watchdogs.Count -gt 0) {
    Add-Check -Id "watchdog" -Component "Self-heal watchdog" -Status "OK" -Summary ("Watchdog process detected ({0})." -f $watchdogs.Count) -Details $watchdogs
} else {
    Add-Check -Id "watchdog" -Component "Self-heal watchdog" -Status "WARN" -Summary "No VexBridgeWatchdog.ps1 process was detected." -Details $null
}

$watchdogLogs = @()
foreach ($wd in $watchdogs) {
    $cmd = [string]$wd.commandLine
    if ($cmd -match '(?i)-File\s+"?([^"\r\n]*VexBridgeWatchdog\.ps1)"?') {
        $scriptPath = $matches[1].Trim()
        $candidate = Join-Path (Split-Path -Parent $scriptPath) "VexBridge-watchdog.log"
        if (Test-Path $candidate) { $watchdogLogs += $candidate }
    }
}
$watchdogLogs = @($watchdogLogs | Select-Object -Unique)
if ($watchdogLogs.Count -gt 0) {
    $logPayload = @()
    foreach ($log in $watchdogLogs) {
        $logPayload += [pscustomobject]@{ path = $log; tail = @(Read-TailSafe -Path $log -Lines 16) }
    }
    Add-Check -Id "watchdog-log" -Component "Watchdog log" -Status "INFO" -Summary "Recent watchdog evidence was collected." -Details $logPayload
}

# ---------------------------------------------------------------------------
# Produce stable machine-readable + human-readable reports. No token is emitted.
# ---------------------------------------------------------------------------
$counts = [ordered]@{
    ok = @($script:Checks | Where-Object status -eq "OK").Count
    warn = @($script:Checks | Where-Object status -eq "WARN").Count
    fail = @($script:Checks | Where-Object status -eq "FAIL").Count
    info = @($script:Checks | Where-Object status -eq "INFO").Count
}

$overall = if ($counts.fail -gt 0) { "FAIL" } elseif ($counts.warn -gt 0) { "WARN" } else { "OK" }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$jsonPath = Join-Path $DiagnosticRoot ("VexDiagnostics-{0}.json" -f $stamp)
$txtPath = Join-Path $DiagnosticRoot ("VexDiagnostics-{0}.txt" -f $stamp)
$latestJson = Join-Path $DiagnosticRoot "latest.json"
$latestTxt = Join-Path $DiagnosticRoot "latest.txt"

$report = [ordered]@{
    schemaVersion = 1
    doctorVersion = "0.1.0"
    generatedAt = (Get-Date).ToString("o")
    overall = $overall
    counts = $counts
    host = $hostInfo
    checks = @($script:Checks)
    secretsIncluded = $false
}

$json = $report | ConvertTo-Json -Depth 12
$json | Set-Content -Path $jsonPath -Encoding UTF8
$json | Set-Content -Path $latestJson -Encoding UTF8

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("Vex Doctor v0.1 Diagnostic Report")
$lines.Add("================================")
$lines.Add("Generated: " + (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz"))
$lines.Add("Host: $($hostInfo.computerName) / $($hostInfo.userName)")
$lines.Add("Overall: $overall   OK=$($counts.ok) WARN=$($counts.warn) FAIL=$($counts.fail) INFO=$($counts.info)")
$lines.Add("Secrets included: NO")
$lines.Add("")

foreach ($status in @("FAIL","WARN","OK","INFO")) {
    $subset = @($script:Checks | Where-Object status -eq $status)
    if ($subset.Count -eq 0) { continue }
    $lines.Add("--- $status ---")
    foreach ($check in $subset) {
        $lines.Add("[$($check.component)] $($check.summary)")
        if ($null -ne $check.details) {
            try {
                $detailText = $check.details | ConvertTo-Json -Depth 8 -Compress
                if ($detailText.Length -gt 5000) { $detailText = $detailText.Substring(0,5000) + "..." }
                $lines.Add("  " + $detailText)
            } catch {}
        }
    }
    $lines.Add("")
}

$lines.Add("JSON report: $jsonPath")
$lines.Add("This report is measured system state. It does not ask Vex's language model to guess what is running.")
$lines | Set-Content -Path $txtPath -Encoding UTF8
$lines | Set-Content -Path $latestTxt -Encoding UTF8

Write-Host ""
Write-Host ("Diagnostic complete: {0}" -f $overall) -ForegroundColor $(if ($overall -eq "OK") { "Green" } elseif ($overall -eq "WARN") { "Yellow" } else { "Red" })
Write-Host "TXT : $txtPath"
Write-Host "JSON: $jsonPath"
Write-Host ""

if (-not $NoOpen) {
    try { Start-Process notepad.exe -ArgumentList ('"{0}"' -f $txtPath) | Out-Null } catch {}
}

if ($overall -eq "FAIL") { exit 2 }
if ($overall -eq "WARN") { exit 1 }
exit 0
