param(
    [switch]$RepairSafe,
    [switch]$Quiet
)

$ErrorActionPreference = "SilentlyContinue"
$DoctorVersion = "0.1.0"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigRoot = Join-Path $env:APPDATA "VexBridge"
$ConfigPath = Join-Path $ConfigRoot "config.json"
$DiagnosticsRoot = Join-Path $ConfigRoot "diagnostics"
$ArtRoot = Join-Path $env:LOCALAPPDATA "VexArt"
$ArtPython = Join-Path $ArtRoot "venv\Scripts\python.exe"
$ComfyDir = Join-Path $ArtRoot "ComfyUI"
$ComfyMain = Join-Path $ComfyDir "main.py"
$Checkpoint = Join-Path $ComfyDir "models\checkpoints\RealVisXL_V5.0_Lightning_fp16.safetensors"
$LearningDb = Join-Path $ConfigRoot "learning\vex-learning.sqlite3"
$SelfRepairState = Join-Path $ConfigRoot "self-repair\state.json"
$WatchdogLog = Join-Path $ScriptRoot "VexBridge-watchdog.log"
$ComfyLog = Join-Path $ArtRoot "comfyui-bridge.log"
$RenderErrorLog = Join-Path $ArtRoot "comfyui-render-errors.log"
$TorchRepairState = Join-Path $ArtRoot "torch-runtime-repair.json"
$StartSelfHeal = Join-Path $ScriptRoot "START-VEX-SELF-HEAL.cmd"

New-Item -ItemType Directory -Force -Path $DiagnosticsRoot | Out-Null

$script:Checks = New-Object System.Collections.Generic.List[object]
$script:Repairs = New-Object System.Collections.Generic.List[object]
$script:Config = $null
$script:Port = 8765
$script:Token = ""

function Add-Check {
    param(
        [string]$Name,
        [ValidateSet("PASS","WARN","FAIL","INFO")][string]$Status,
        [string]$Detail,
        $Data = $null
    )
    $item = [ordered]@{
        name = $Name
        status = $Status
        detail = $Detail
    }
    if ($null -ne $Data) { $item.data = $Data }
    $script:Checks.Add([pscustomobject]$item)
}

function Add-Repair {
    param([string]$Component, [bool]$Ok, [string]$Detail)
    $script:Repairs.Add([pscustomobject][ordered]@{
        component = $Component
        ok = $Ok
        detail = $Detail
        time = (Get-Date).ToString("o")
    })
}

function Get-ProcessRows {
    try {
        return @(Get-CimInstance Win32_Process | Select-Object Name, ProcessId, CommandLine, ExecutablePath)
    } catch {
        return @()
    }
}

function Test-LocalTcpPort {
    param([int]$Port)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(700, $false)
        if ($ok -and $client.Connected) {
            $client.EndConnect($iar)
            $client.Close()
            return $true
        }
        $client.Close()
    } catch {}
    return $false
}

function Invoke-LocalJson {
    param(
        [string]$Url,
        [ValidateSet("GET","POST")][string]$Method = "GET",
        [int]$TimeoutSec = 8
    )
    $oldCallback = [System.Net.ServicePointManager]::ServerCertificateValidationCallback
    try {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
        $params = @{
            Uri = $Url
            Method = $Method
            TimeoutSec = $TimeoutSec
            ErrorAction = "Stop"
        }
        if ($Method -eq "POST") {
            $params.ContentType = "application/json"
            $params.Body = "{}"
        }
        $value = Invoke-RestMethod @params
        return [pscustomobject]@{ ok = $true; value = $value; error = $null }
    } catch {
        return [pscustomobject]@{ ok = $false; value = $null; error = $_.Exception.Message }
    } finally {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $oldCallback
    }
}

function Get-LogTail {
    param([string]$Path, [int]$Lines = 35)
    if (-not (Test-Path $Path)) { return $null }
    try {
        return (@(Get-Content -Path $Path -Tail $Lines -ErrorAction Stop) -join "`n")
    } catch {
        return $null
    }
}

function Get-FileInfoSafe {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    try {
        $item = Get-Item $Path -ErrorAction Stop
        return [pscustomobject]@{
            path = $item.FullName
            bytes = if ($item.PSIsContainer) { $null } else { $item.Length }
            modified = $item.LastWriteTime.ToString("o")
        }
    } catch { return $null }
}

function Read-Config {
    if (-not (Test-Path $ConfigPath)) {
        Add-Check "bridge-config" "FAIL" "Bridge config is missing at $ConfigPath"
        return
    }
    try {
        $raw = Get-Content -Raw -Path $ConfigPath -ErrorAction Stop
        $cfg = $raw | ConvertFrom-Json -ErrorAction Stop
        $script:Config = $cfg
        if ($cfg.port) { $script:Port = [int]$cfg.port }
        $script:Token = [string]$cfg.token
        if ([string]::IsNullOrWhiteSpace($script:Token)) {
            Add-Check "bridge-config" "FAIL" "Bridge config parsed but has no pairing token" ([pscustomobject]@{ path = $ConfigPath; port = $script:Port })
        } else {
            Add-Check "bridge-config" "PASS" "Bridge config parses correctly" ([pscustomobject]@{
                path = $ConfigPath
                port = $script:Port
                web_search = [bool]$cfg.web_search
                token_present = $true
            })
        }
    } catch {
        Add-Check "bridge-config" "FAIL" "Bridge config could not be parsed: $($_.Exception.Message)"
    }
}

function Test-Processes {
    $rows = Get-ProcessRows
    $bridge = @($rows | Where-Object { $_.Name -ieq "VexBridge.exe" })
    $watchdog = @($rows | Where-Object { ($_.Name -match "^(powershell|pwsh)\.exe$") -and ($_.CommandLine -match "VexBridgeWatchdog\.ps1") })
    $ollama = @($rows | Where-Object { $_.Name -ieq "ollama.exe" })
    $comfy = @($rows | Where-Object { ($_.Name -match "^python(w)?\.exe$") -and ($_.CommandLine -match "ComfyUI.*main\.py|main\.py.*8188") })

    if ($bridge.Count -gt 0) {
        Add-Check "bridge-process" "PASS" "VexBridge.exe is running" (@($bridge | Select-Object ProcessId, ExecutablePath))
    } else {
        Add-Check "bridge-process" "FAIL" "VexBridge.exe is not running"
    }

    if ($watchdog.Count -gt 0) {
        Add-Check "watchdog-process" "PASS" "VexBridge watchdog is running" (@($watchdog | Select-Object ProcessId, CommandLine))
    } else {
        Add-Check "watchdog-process" "WARN" "VexBridge watchdog is not running"
    }

    if ($ollama.Count -gt 0) {
        Add-Check "ollama-process" "INFO" "Ollama process is present" (@($ollama | Select-Object ProcessId, ExecutablePath))
    } else {
        Add-Check "ollama-process" "INFO" "No Ollama process is currently visible"
    }

    if ($comfy.Count -gt 0) {
        Add-Check "comfyui-process" "INFO" "ComfyUI Python process is present" (@($comfy | Select-Object ProcessId, CommandLine))
    } else {
        Add-Check "comfyui-process" "INFO" "ComfyUI is not currently resident; this can be normal when art is cold"
    }
}

function Test-BridgeEndpoints {
    if ([string]::IsNullOrWhiteSpace($script:Token)) {
        Add-Check "bridge-port" "WARN" "Bridge endpoint checks skipped because no valid token is available"
        return
    }

    $encoded = [uri]::EscapeDataString($script:Token)
    $base = "https://127.0.0.1:$($script:Port)"
    $tcp = Test-LocalTcpPort -Port $script:Port
    if ($tcp) { Add-Check "bridge-port" "PASS" "TCP port $($script:Port) is accepting local connections" }
    else { Add-Check "bridge-port" "FAIL" "TCP port $($script:Port) is not accepting local connections" }

    $routes = @(
        @{ name = "bridge-status"; path = "/status" },
        @{ name = "cognition-status"; path = "/llm/status" },
        @{ name = "art-status"; path = "/art/health" },
        @{ name = "repair-status"; path = "/repair/status" },
        @{ name = "maintenance-status"; path = "/maintenance/status" },
        @{ name = "learning-status"; path = "/learning/status" }
    )

    foreach ($route in $routes) {
        $result = Invoke-LocalJson -Url ($base + $route.path + "?token=" + $encoded) -TimeoutSec 12
        if ($result.ok) {
            $value = $result.value
            $reportedOk = $null
            try { $reportedOk = $value.ok } catch {}
            if ($route.name -eq "cognition-status" -and $reportedOk -eq $false) {
                Add-Check $route.name "FAIL" "Bridge answered, but no healthy local cognition model is available" $value
            } elseif ($route.name -eq "art-status" -and $value.installed -eq $false) {
                Add-Check $route.name "WARN" "Bridge answered; Vex Art is not installed on this node" $value
            } elseif ($route.name -eq "art-status" -and $value.running -eq $false) {
                Add-Check $route.name "INFO" "Bridge answered; ComfyUI is currently cold/stopped" $value
            } else {
                Add-Check $route.name "PASS" "Authenticated Bridge endpoint answered" $value
            }
        } else {
            Add-Check $route.name "FAIL" "Endpoint did not answer: $($result.error)"
        }
    }
}

function Test-DirectServices {
    $ollama = Invoke-LocalJson -Url "http://127.0.0.1:11434/api/tags" -TimeoutSec 6
    if ($ollama.ok) {
        $models = @()
        try { $models = @($ollama.value.models | ForEach-Object { $_.name }) } catch {}
        Add-Check "ollama-direct" "PASS" "Ollama answers directly on localhost" ([pscustomobject]@{ models = $models })
    } else {
        Add-Check "ollama-direct" "FAIL" "Ollama does not answer directly on localhost: $($ollama.error)"
    }

    if (Test-Path $ComfyMain) {
        $comfy = Invoke-LocalJson -Url "http://127.0.0.1:8188/system_stats" -TimeoutSec 5
        if ($comfy.ok) {
            Add-Check "comfyui-direct" "PASS" "ComfyUI answers directly on localhost" $comfy.value
        } else {
            Add-Check "comfyui-direct" "INFO" "ComfyUI is installed but not currently answering; cold art is allowed" ([pscustomobject]@{ error = $comfy.error })
        }
    } else {
        Add-Check "comfyui-direct" "WARN" "ComfyUI main.py was not found at $ComfyMain"
    }
}

function Test-InstallFiles {
    $bridgeExe = Join-Path $ScriptRoot "VexBridge.exe"
    if (Test-Path $bridgeExe) { Add-Check "bridge-executable" "PASS" "VexBridge.exe exists beside VexDoctor" (Get-FileInfoSafe $bridgeExe) }
    else { Add-Check "bridge-executable" "FAIL" "VexBridge.exe is missing beside VexDoctor" }

    if ((Test-Path $ArtPython) -and (Test-Path $ComfyMain)) {
        Add-Check "art-install" "PASS" "Vex Art Python and ComfyUI installation are present" ([pscustomobject]@{ python = $ArtPython; comfy = $ComfyMain })
    } else {
        Add-Check "art-install" "WARN" "Vex Art installation is incomplete or absent" ([pscustomobject]@{ python_exists = (Test-Path $ArtPython); comfy_exists = (Test-Path $ComfyMain) })
    }

    if (Test-Path $Checkpoint) { Add-Check "art-model" "PASS" "RealVisXL checkpoint exists" (Get-FileInfoSafe $Checkpoint) }
    else { Add-Check "art-model" "WARN" "RealVisXL checkpoint was not found at the expected dynamic-user-independent VexArt path" }

    if (Test-Path $LearningDb) { Add-Check "learning-store" "PASS" "Persistent learning SQLite store exists" (Get-FileInfoSafe $LearningDb) }
    else { Add-Check "learning-store" "INFO" "Learning SQLite store does not exist yet; it is created when the learning engine initializes" }

    if (Test-Path $SelfRepairState) { Add-Check "self-repair-state" "PASS" "Self-repair state file exists" (Get-FileInfoSafe $SelfRepairState) }
    else { Add-Check "self-repair-state" "INFO" "No self-repair state file exists yet" }
}

function Test-Logs {
    $logs = @(
        @{ name = "watchdog-log"; path = $WatchdogLog },
        @{ name = "comfyui-log"; path = $ComfyLog },
        @{ name = "render-error-log"; path = $RenderErrorLog },
        @{ name = "torch-repair-state"; path = $TorchRepairState }
    )
    foreach ($log in $logs) {
        if (Test-Path $log.path) {
            Add-Check $log.name "INFO" "Recent diagnostic tail captured" ([pscustomobject]@{ path = $log.path; tail = (Get-LogTail $log.path) })
        } else {
            Add-Check $log.name "INFO" "No file currently present at $($log.path)"
        }
    }
}

function Run-Diagnostics {
    $script:Checks.Clear()
    $script:Config = $null
    $script:Port = 8765
    $script:Token = ""
    Read-Config
    Test-Processes
    Test-InstallFiles
    Test-BridgeEndpoints
    Test-DirectServices
    Test-Logs
}

function Find-OllamaExe {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\ollama.exe")
    )
    try {
        $cmd = Get-Command ollama.exe -ErrorAction Stop
        if ($cmd.Source) { $candidates = @($cmd.Source) + $candidates }
    } catch {}
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

function Invoke-SafeRepairs {
    $rows = Get-ProcessRows
    $watchdog = @($rows | Where-Object { ($_.Name -match "^(powershell|pwsh)\.exe$") -and ($_.CommandLine -match "VexBridgeWatchdog\.ps1") })
    $bridge = @($rows | Where-Object { $_.Name -ieq "VexBridge.exe" })

    if ($watchdog.Count -eq 0 -and (Test-Path $StartSelfHeal)) {
        try {
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c", ('"' + $StartSelfHeal + '"') -WorkingDirectory $ScriptRoot | Out-Null
            Start-Sleep -Seconds 5
            Add-Repair "watchdog" $true "Started START-VEX-SELF-HEAL.cmd"
        } catch {
            Add-Repair "watchdog" $false "Could not start watchdog: $($_.Exception.Message)"
        }
    } elseif ($watchdog.Count -gt 0) {
        Add-Repair "watchdog" $true "Watchdog was already running"
    } elseif ($bridge.Count -gt 0) {
        Add-Repair "watchdog" $false "Bridge is running but watchdog launcher was not found beside VexDoctor"
    } else {
        Add-Repair "watchdog" $false "Neither watchdog nor Bridge is running and the self-heal launcher is unavailable"
    }

    $ollamaHealth = Invoke-LocalJson -Url "http://127.0.0.1:11434/api/tags" -TimeoutSec 4
    if (-not $ollamaHealth.ok) {
        $ollamaExe = Find-OllamaExe
        if ($ollamaExe) {
            try {
                Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden | Out-Null
                Start-Sleep -Seconds 4
                $again = Invoke-LocalJson -Url "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
                Add-Repair "ollama" ([bool]$again.ok) $(if ($again.ok) { "Started Ollama and verified localhost API" } else { "Started Ollama, but localhost API still did not answer" })
            } catch {
                Add-Repair "ollama" $false "Ollama launch failed: $($_.Exception.Message)"
            }
        } else {
            Add-Repair "ollama" $false "Ollama is unhealthy and ollama.exe could not be located"
        }
    } else {
        Add-Repair "ollama" $true "Ollama was already healthy"
    }

    if (-not [string]::IsNullOrWhiteSpace($script:Token)) {
        $encoded = [uri]::EscapeDataString($script:Token)
        $repair = Invoke-LocalJson -Url "https://127.0.0.1:$($script:Port)/repair/run?token=$encoded" -Method POST -TimeoutSec 240
        if ($repair.ok) {
            $ok = $true
            try { $ok = [bool]$repair.value.ok } catch {}
            Add-Repair "bridge-self-repair" $ok "Bridge repair pass completed; result is included in report"
            $script:Repairs.Add([pscustomobject][ordered]@{ component = "bridge-self-repair-result"; ok = $ok; detail = ($repair.value | ConvertTo-Json -Depth 8 -Compress); time = (Get-Date).ToString("o") })
        } else {
            Add-Repair "bridge-self-repair" $false "Could not call /repair/run: $($repair.error)"
        }
    }

    Start-Sleep -Seconds 3
}

function Save-Report {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $pass = @($script:Checks | Where-Object status -eq "PASS").Count
    $warn = @($script:Checks | Where-Object status -eq "WARN").Count
    $fail = @($script:Checks | Where-Object status -eq "FAIL").Count
    $info = @($script:Checks | Where-Object status -eq "INFO").Count
    $overall = if ($fail -gt 0) { "FAIL" } elseif ($warn -gt 0) { "WARN" } else { "PASS" }

    $report = [ordered]@{
        schema = 1
        doctor_version = $DoctorVersion
        node_name = $env:COMPUTERNAME
        generated_at = (Get-Date).ToString("o")
        repair_mode = [bool]$RepairSafe
        overall = $overall
        counts = [ordered]@{ pass = $pass; warn = $warn; fail = $fail; info = $info }
        checks = @($script:Checks)
        repairs = @($script:Repairs)
    }

    $json = $report | ConvertTo-Json -Depth 12
    $jsonPath = Join-Path $DiagnosticsRoot "VexDiagnostic-$timestamp.json"
    $txtPath = Join-Path $DiagnosticsRoot "VexDiagnostic-$timestamp.txt"
    $latestJson = Join-Path $DiagnosticsRoot "VexDiagnostic-LATEST.json"
    $latestTxt = Join-Path $DiagnosticsRoot "VexDiagnostic-LATEST.txt"
    $json | Set-Content -Encoding UTF8 $jsonPath
    $json | Set-Content -Encoding UTF8 $latestJson

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("VexDoctor $DoctorVersion")
    $lines.Add("Node: $($env:COMPUTERNAME)")
    $lines.Add("Generated: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))")
    $lines.Add("Overall: $overall | PASS $pass | WARN $warn | FAIL $fail | INFO $info")
    $lines.Add("")
    foreach ($check in $script:Checks) {
        $lines.Add("[$($check.status)] $($check.name) - $($check.detail)")
    }
    if ($script:Repairs.Count -gt 0) {
        $lines.Add("")
        $lines.Add("SAFE REPAIR ACTIONS")
        foreach ($repair in $script:Repairs) {
            $tag = if ($repair.ok) { "OK" } else { "FAILED" }
            $lines.Add("[$tag] $($repair.component) - $($repair.detail)")
        }
    }
    $lines.Add("")
    $lines.Add("JSON report: $jsonPath")
    $lines.Add("Latest JSON: $latestJson")
    $lines | Set-Content -Encoding UTF8 $txtPath
    $lines | Set-Content -Encoding UTF8 $latestTxt

    return [pscustomobject]@{ report = $report; json = $jsonPath; text = $txtPath; latest_json = $latestJson; latest_text = $latestTxt }
}

Run-Diagnostics
if ($RepairSafe) {
    Invoke-SafeRepairs
    Run-Diagnostics
}
$result = Save-Report

if (-not $Quiet) {
    Clear-Host
    Write-Host ""
    Write-Host "VexDoctor $DoctorVersion" -ForegroundColor Magenta
    Write-Host "=================" -ForegroundColor Magenta
    Write-Host "Node: $env:COMPUTERNAME"
    Write-Host ""
    foreach ($check in $script:Checks) {
        $color = switch ($check.status) {
            "PASS" { "Green" }
            "WARN" { "Yellow" }
            "FAIL" { "Red" }
            default { "Gray" }
        }
        Write-Host ("[{0}] {1} - {2}" -f $check.status, $check.name, $check.detail) -ForegroundColor $color
    }
    if ($script:Repairs.Count -gt 0) {
        Write-Host ""
        Write-Host "Safe repair actions:" -ForegroundColor Cyan
        foreach ($repair in $script:Repairs) {
            $tag = if ($repair.ok) { "OK" } else { "FAILED" }
            Write-Host ("[{0}] {1} - {2}" -f $tag, $repair.component, $repair.detail)
        }
    }
    Write-Host ""
    Write-Host "Latest report:" -ForegroundColor Cyan
    Write-Host $result.latest_text
    Write-Host $result.latest_json
    Write-Host ""
    Write-Host "This tool reports direct process/API/file evidence; it does not ask the language model to guess system state." -ForegroundColor DarkGray
    Write-Host ""
}

if ($result.report.overall -eq "FAIL") { exit 2 }
if ($result.report.overall -eq "WARN") { exit 1 }
exit 0
