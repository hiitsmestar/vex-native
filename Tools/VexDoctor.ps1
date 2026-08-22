param(
    [switch]$RepairSafe,
    [switch]$KeepOpen
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$ReportRoot = Join-Path $PSScriptRoot "VexDoctor-Reports"
New-Item -ItemType Directory -Force -Path $ReportRoot | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$JsonPath = Join-Path $ReportRoot "VexDoctor-$Stamp.json"
$TextPath = Join-Path $ReportRoot "VexDoctor-$Stamp.txt"

$Checks = New-Object System.Collections.Generic.List[object]
$Actions = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param(
        [string]$Area,
        [string]$Name,
        [string]$State,
        [string]$Detail,
        [string]$Role = "core"
    )
    $Checks.Add([pscustomobject]@{
        area = $Area
        name = $Name
        state = $State
        detail = $Detail
        role = $Role
    }) | Out-Null
}

function Add-Action {
    param([string]$Name, [string]$Result, [string]$Detail)
    $Actions.Add([pscustomobject]@{
        name = $Name
        result = $Result
        detail = $Detail
    }) | Out-Null
}

function Test-TcpPort {
    param([string]$HostName, [int]$Port, [int]$TimeoutMs = 1200)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        if (-not $task.Wait($TimeoutMs)) { return $false }
        return $client.Connected
    } catch { return $false } finally { $client.Dispose() }
}

function Invoke-LocalJson {
    param([string]$Uri, [int]$TimeoutSec = 3)
    try {
        return Invoke-RestMethod -Uri $Uri -Method Get -TimeoutSec $TimeoutSec
    } catch {
        return $null
    }
}

function Get-ListeningPid {
    param([int]$Port)
    try {
        $row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
        if ($row) { return [int]$row.OwningProcess }
    } catch {}
    return $null
}

function Get-ProcessNameSafe {
    param([Nullable[int]]$PidValue)
    if ($null -eq $PidValue) { return $null }
    try { return (Get-Process -Id $PidValue -ErrorAction Stop).ProcessName } catch { return $null }
}

function Find-OllamaExe {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in @(
        "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
        "$env:ProgramFiles\Ollama\ollama.exe"
    )) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Find-BridgeExe {
    $candidate = Join-Path $PSScriptRoot "VexBridge.exe"
    if (Test-Path $candidate) { return $candidate }
    try {
        $found = Get-ChildItem -Path $PSScriptRoot -Filter VexBridge.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { return $found.FullName }
    } catch {}
    return $null
}

function Tail-UsefulLogs {
    $roots = @(
        $PSScriptRoot,
        (Join-Path $env:APPDATA "VexBridge"),
        (Join-Path $env:LOCALAPPDATA "VexArt"),
        (Join-Path $env:LOCALAPPDATA "VexBrain")
    ) | Select-Object -Unique
    $result = @()
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        try {
            $files = Get-ChildItem -Path $root -Filter *.log -File -Recurse -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 8
            foreach ($file in $files) {
                $tail = @()
                try { $tail = Get-Content -Path $file.FullName -Tail 30 -ErrorAction Stop } catch {}
                $result += [pscustomobject]@{
                    path = $file.FullName
                    modified = $file.LastWriteTime.ToString("s")
                    tail = $tail
                }
            }
        } catch {}
    }
    return $result | Sort-Object modified -Descending | Select-Object -First 12
}

Write-Host ""
Write-Host "Vex Doctor" -ForegroundColor Magenta
Write-Host "==========" -ForegroundColor Magenta
Write-Host "Independent diagnostics for VexNative. This does not ask the language model what is working." -ForegroundColor White
Write-Host ""

# Machine snapshot
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$computer = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
$gpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
$uptimeHours = $null
if ($os -and $os.LastBootUpTime) { $uptimeHours = [Math]::Round(((Get-Date) - $os.LastBootUpTime).TotalHours, 1) }
$totalRamGB = $null
$freeRamGB = $null
if ($computer) { $totalRamGB = [Math]::Round($computer.TotalPhysicalMemory / 1GB, 1) }
if ($os) { $freeRamGB = [Math]::Round(($os.FreePhysicalMemory * 1KB) / 1GB, 1) }

$drives = @()
try {
    $drives = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
        [pscustomobject]@{
            drive = $_.DeviceID
            totalGB = if ($_.Size) { [Math]::Round($_.Size / 1GB, 1) } else { $null }
            freeGB = if ($_.FreeSpace) { [Math]::Round($_.FreeSpace / 1GB, 1) } else { 0 }
        }
    }
} catch {}

# Bridge is persistent core infrastructure.
$bridgeConfigPath = Join-Path $env:APPDATA "VexBridge\config.json"
$bridgePort = 8765
if (Test-Path $bridgeConfigPath) {
    try {
        $cfg = Get-Content $bridgeConfigPath -Raw | ConvertFrom-Json
        if ($cfg.port) { $bridgePort = [int]$cfg.port }
        Add-Check "Bridge" "Configuration" "ok" "Config readable at $bridgeConfigPath; token intentionally omitted from report." "persistent-core"
    } catch {
        Add-Check "Bridge" "Configuration" "bad" "Config exists but could not be parsed: $($_.Exception.Message)" "persistent-core"
    }
} else {
    Add-Check "Bridge" "Configuration" "missing" "No config found at $bridgeConfigPath" "persistent-core"
}

$bridgeTcp = Test-TcpPort "127.0.0.1" $bridgePort
$bridgePid = Get-ListeningPid $bridgePort
$bridgeProc = Get-ProcessNameSafe $bridgePid
if ($bridgeTcp) {
    Add-Check "Bridge" "Listener" "ok" "127.0.0.1:$bridgePort is listening; PID=$bridgePid process=$bridgeProc" "persistent-core"
} else {
    Add-Check "Bridge" "Listener" "down" "Nothing is listening on 127.0.0.1:$bridgePort" "persistent-core"
}

$watchdog = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "VexBridgeWatchdog\.ps1"
} | Select-Object -First 1
if ($watchdog) {
    Add-Check "Bridge" "Self-heal watchdog" "ok" "Watchdog process is running; PID=$($watchdog.ProcessId)" "persistent-core"
} else {
    Add-Check "Bridge" "Self-heal watchdog" "down" "No VexBridgeWatchdog.ps1 process detected." "persistent-core"
}

# Cognition/Ollama is core while PC cognition is desired.
$ollamaExe = Find-OllamaExe
if ($ollamaExe) {
    Add-Check "Cognition" "Ollama install" "ok" $ollamaExe "persistent-core"
} else {
    Add-Check "Cognition" "Ollama install" "missing" "ollama.exe was not found in the expected locations." "persistent-core"
}

$ollamaTcp = Test-TcpPort "127.0.0.1" 11434
if ($ollamaTcp) {
    $tags = Invoke-LocalJson "http://127.0.0.1:11434/api/tags" 4
    if ($tags) {
        $names = @($tags.models | ForEach-Object { $_.name })
        $preferred = @($names | Where-Object { $_ -match "^(vex-qwen3-4b|qwen3:4b)" })
        $state = if ($preferred.Count -gt 0) { "ok" } else { "warn" }
        $detail = "Ollama API healthy. Models: " + (($names | Select-Object -First 12) -join ", ")
        Add-Check "Cognition" "Ollama API/models" $state $detail "persistent-core"
    } else {
        Add-Check "Cognition" "Ollama API/models" "warn" "Port 11434 is open but /api/tags did not return readable JSON." "persistent-core"
    }
} else {
    Add-Check "Cognition" "Ollama API/models" "down" "Ollama is not listening on 127.0.0.1:11434." "persistent-core"
}

# Art is intentionally on-demand. Installed + stopped is healthy/idle, not broken.
$artRoot = Join-Path $env:LOCALAPPDATA "VexArt"
$comfyMain = Join-Path $artRoot "ComfyUI\main.py"
$artPython = Join-Path $artRoot "venv\Scripts\python.exe"
$checkpoint = Join-Path $artRoot "ComfyUI\models\checkpoints\RealVisXL_V5.0_Lightning_fp16.safetensors"
$runArt = Join-Path $artRoot "RUN-VEX-ART.cmd"
$artInstalled = (Test-Path $comfyMain) -and (Test-Path $artPython)
if ($artInstalled) {
    $modelDetail = if (Test-Path $checkpoint) { "checkpoint present" } else { "checkpoint missing" }
    Add-Check "Art" "Vex Art install" "ok" "ComfyUI installed at $artRoot; $modelDetail." "on-demand-tool"
} else {
    Add-Check "Art" "Vex Art install" "missing" "Expected ComfyUI/venv not found under $artRoot." "on-demand-tool"
}

$comfyTcp = Test-TcpPort "127.0.0.1" 8188
if ($comfyTcp) {
    $stats = Invoke-LocalJson "http://127.0.0.1:8188/system_stats" 4
    if ($stats) {
        Add-Check "Art" "ComfyUI runtime" "ok" "ComfyUI is running and /system_stats answered on port 8188." "on-demand-tool"
    } else {
        Add-Check "Art" "ComfyUI runtime" "warn" "Port 8188 is open but /system_stats did not answer normally." "on-demand-tool"
    }
} elseif ($artInstalled) {
    Add-Check "Art" "ComfyUI runtime" "idle" "Installed and currently stopped. This is normal for an on-demand tool." "on-demand-tool"
} else {
    Add-Check "Art" "ComfyUI runtime" "unavailable" "Not running because the art install is incomplete or absent." "on-demand-tool"
}

# Optional safe repair only starts known installed core components. It does not delete, reinstall, or alter user files.
if ($RepairSafe) {
    Write-Host "Safe repair requested. Only known startup repairs will be attempted." -ForegroundColor Yellow

    if (-not $ollamaTcp -and $ollamaExe) {
        try {
            Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
            Start-Sleep -Seconds 3
            if (Test-TcpPort "127.0.0.1" 11434 1800) {
                Add-Action "Start Ollama" "ok" "Ollama began listening on port 11434."
            } else {
                Add-Action "Start Ollama" "failed" "ollama serve was launched but port 11434 still is not listening."
            }
        } catch { Add-Action "Start Ollama" "failed" $_.Exception.Message }
    }

    if (-not $watchdog) {
        $watchdogScript = Join-Path $PSScriptRoot "VexBridgeWatchdog.ps1"
        if ((Test-Path $watchdogScript) -and (Find-BridgeExe)) {
            try {
                Start-Process powershell.exe -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + $watchdogScript + '"')) -WorkingDirectory $PSScriptRoot
                Start-Sleep -Seconds 3
                Add-Action "Start Bridge watchdog" "attempted" "Started VexBridgeWatchdog.ps1. Re-run Vex Doctor to verify the listener."
            } catch { Add-Action "Start Bridge watchdog" "failed" $_.Exception.Message }
        } else {
            Add-Action "Start Bridge watchdog" "skipped" "Watchdog script or VexBridge.exe was not found beside this tool."
        }
    }

    # ComfyUI remains idle unless explicitly used for art; Doctor does not start it just to make every light green.
    if ($artInstalled -and -not $comfyTcp) {
        Add-Action "ComfyUI" "left-idle" "Art is installed but stopped; preserved the intended on-demand behavior."
    }
}

$logs = Tail-UsefulLogs
$report = [pscustomobject]@{
    schema = 1
    generatedAt = (Get-Date).ToString("o")
    machine = [pscustomobject]@{
        computerName = $env:COMPUTERNAME
        userName = $env:USERNAME
        windows = if ($os) { $os.Caption } else { $null }
        uptimeHours = $uptimeHours
        totalRamGB = $totalRamGB
        freeRamGB = $freeRamGB
        gpu = @($gpu)
        drives = @($drives)
    }
    checks = @($Checks)
    safeRepairRequested = [bool]$RepairSafe
    actions = @($Actions)
    recentLogs = @($logs)
}

$report | ConvertTo-Json -Depth 8 | Set-Content -Path $JsonPath -Encoding UTF8

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("VEX DOCTOR REPORT") | Out-Null
$lines.Add("Generated: $($report.generatedAt)") | Out-Null
$lines.Add("Machine: $env:COMPUTERNAME / $env:USERNAME") | Out-Null
$lines.Add("RAM: $freeRamGB GB free / $totalRamGB GB total") | Out-Null
$lines.Add("") | Out-Null
foreach ($check in $Checks) {
    $lines.Add(("[{0}] {1} / {2} ({3}) - {4}" -f $check.state.ToUpperInvariant(), $check.area, $check.name, $check.role, $check.detail)) | Out-Null
}
if ($Actions.Count -gt 0) {
    $lines.Add("") | Out-Null
    $lines.Add("SAFE REPAIR ACTIONS") | Out-Null
    foreach ($action in $Actions) {
        $lines.Add(("[{0}] {1} - {2}" -f $action.result.ToUpperInvariant(), $action.name, $action.detail)) | Out-Null
    }
}
$lines.Add("") | Out-Null
$lines.Add("JSON report: $JsonPath") | Out-Null
$lines.Add("Text report: $TextPath") | Out-Null
$lines | Set-Content -Path $TextPath -Encoding UTF8

Write-Host ""
foreach ($check in $Checks) {
    $color = switch ($check.state) {
        "ok" { "Green" }
        "idle" { "Cyan" }
        "warn" { "Yellow" }
        default { "Red" }
    }
    Write-Host ("[{0}] {1} / {2}: {3}" -f $check.state.ToUpperInvariant(), $check.area, $check.name, $check.detail) -ForegroundColor $color
}
if ($Actions.Count -gt 0) {
    Write-Host ""
    Write-Host "Safe repair actions:" -ForegroundColor Magenta
    foreach ($action in $Actions) { Write-Host ("[$($action.result)] $($action.name): $($action.detail)") }
}

Write-Host ""
Write-Host "Reports saved:" -ForegroundColor Green
Write-Host $TextPath
Write-Host $JsonPath
Write-Host ""
Write-Host "Tip: send the text/JSON report instead of asking the local model to guess what is running." -ForegroundColor DarkGray

if ($KeepOpen) {
    Write-Host ""
    Read-Host "Press Enter to close" | Out-Null
}
