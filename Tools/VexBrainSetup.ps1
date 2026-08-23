param(
    [string]$Model = "auto",
    [int]$RegistryAttempts = 3,
    [int]$DirectDownloadAttempts = 60
)

$ErrorActionPreference = "Stop"
$BrainRoot = Join-Path $env:LOCALAPPDATA "VexBrain"
$ModelDir = Join-Path $BrainRoot "models"
$ProfilePath = Join-Path $BrainRoot "cognition-profile.json"
$FourBPath = Join-Path $ModelDir "Qwen3-4B-Q4_K_M.gguf"
$FourBUrl = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf?download=true"
$SmallPath = Join-Path $ModelDir "Qwen3-1.7B-Q4_K_M.gguf"
$SmallUrl = "https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf?download=true"

Write-Host ""
Write-Host "Vex Brain Setup v0.10.9 - Adaptive PC Cognition" -ForegroundColor Magenta
Write-Host "================================================" -ForegroundColor Magenta
Write-Host "This probes the actual PC first, then chooses a local model tier with headroom for Windows, Bridge, Remote Support, and tools."
Write-Host "No paid API or cloud inference is used."
Write-Host ""

function Get-OllamaCommand {
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

function Ensure-OllamaHealthy {
    param([string]$Ollama)
    $healthy = $false
    try {
        & $Ollama list *> $null
        if ($LASTEXITCODE -eq 0) { $healthy = $true }
    } catch {}
    if (-not $healthy) {
        Write-Host "Starting the local Ollama service..." -ForegroundColor Cyan
        Start-Process -FilePath $Ollama -ArgumentList "serve" -WindowStyle Hidden
        foreach ($i in 1..40) {
            Start-Sleep -Milliseconds 500
            try {
                & $Ollama list *> $null
                if ($LASTEXITCODE -eq 0) { $healthy = $true; break }
            } catch {}
        }
    }
    if (-not $healthy) { throw "Ollama is installed but its local service did not start." }
}

function Get-HardwareProfile {
    $ramGB = 0.0
    $cpuLogical = [Environment]::ProcessorCount
    $gpuName = $null
    $gpuVramGB = 0.0
    $gpuSource = $null

    try {
        $cs = Get-CimInstance Win32_ComputerSystem
        if ($cs.TotalPhysicalMemory) { $ramGB = [Math]::Round([double]$cs.TotalPhysicalMemory / 1GB, 1) }
        if ($cs.NumberOfLogicalProcessors) { $cpuLogical = [int]$cs.NumberOfLogicalProcessors }
    } catch {}

    $nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($nvidia) {
        try {
            $rows = & $nvidia.Source --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null
            $best = $null
            foreach ($row in $rows) {
                $parts = @($row -split ',')
                if ($parts.Count -lt 2) { continue }
                $mb = 0.0
                if (-not [double]::TryParse($parts[-1].Trim(), [ref]$mb)) { continue }
                if ($null -eq $best -or $mb -gt $best.VramMB) {
                    $best = [pscustomobject]@{ Name = (($parts[0..($parts.Count-2)] -join ',').Trim()); VramMB = $mb }
                }
            }
            if ($best) {
                $gpuName = $best.Name
                $gpuVramGB = [Math]::Round($best.VramMB / 1024, 1)
                $gpuSource = "nvidia-smi"
            }
        } catch {}
    }

    if (-not $gpuName) {
        try {
            $gpu = Get-CimInstance Win32_VideoController | Sort-Object AdapterRAM -Descending | Select-Object -First 1
            if ($gpu) {
                $gpuName = [string]$gpu.Name
                if ($gpu.AdapterRAM) { $gpuVramGB = [Math]::Round([double]$gpu.AdapterRAM / 1GB, 1) }
                $gpuSource = "windows-cim"
            }
        } catch {}
    }

    [pscustomobject]@{
        ram_gb = $ramGB
        cpu_logical = [int]$cpuLogical
        gpu_name = $gpuName
        gpu_vram_gb = $gpuVramGB
        gpu_source = $gpuSource
    }
}

function Get-ModelCandidates {
    param([pscustomobject]$Hardware, [string]$Requested)

    if ($Requested -and $Requested.ToLowerInvariant() -ne "auto") {
        return @($Requested)
    }

    $ram = [double]$Hardware.ram_gb
    $cpu = [int]$Hardware.cpu_logical
    $vram = [double]$Hardware.gpu_vram_gb

    if (($vram -ge 11.0 -and $ram -ge 24.0) -or ($ram -ge 32.0 -and $cpu -ge 12)) {
        return @("qwen3:14b", "qwen3:8b", "qwen3:4b", "qwen3:1.7b")
    }
    if (($vram -ge 7.0 -and $ram -ge 16.0) -or ($ram -ge 20.0 -and $cpu -ge 8)) {
        return @("qwen3:8b", "qwen3:4b", "qwen3:1.7b")
    }
    if ($ram -ge 9.0) {
        return @("qwen3:4b", "qwen3:1.7b")
    }
    return @("qwen3:1.7b")
}

function Get-InstalledModels {
    param([string]$Ollama)
    try {
        $lines = & $Ollama list 2>$null
        return @($lines | Select-Object -Skip 1 | ForEach-Object {
            $s = ($_ | Out-String).Trim()
            if ($s) { ($s -split '\s+')[0] }
        } | Where-Object { $_ })
    } catch { return @() }
}

function Test-ModelInstalled {
    param([string]$Ollama, [string]$Name)
    $wanted = $Name.ToLowerInvariant()
    foreach ($item in (Get-InstalledModels -Ollama $Ollama)) {
        $low = $item.ToLowerInvariant()
        if ($low -eq $wanted -or $low -eq ($wanted + ":latest")) { return $true }
        if ($wanted -eq "qwen3:4b" -and $low -like "vex-qwen3-4b*") { return $true }
        if ($wanted -eq "qwen3:1.7b" -and $low -like "vex-qwen3-1.7b*") { return $true }
    }
    return $false
}

function Invoke-RegistryPull {
    param([string]$Ollama, [string]$Name)
    for ($attempt = 1; $attempt -le $RegistryAttempts; $attempt++) {
        Write-Host "Registry attempt $attempt of $RegistryAttempts for $Name..." -ForegroundColor Cyan
        & $Ollama pull $Name
        if ($LASTEXITCODE -eq 0) { return $true }
        if ($attempt -lt $RegistryAttempts) { Start-Sleep -Seconds (10 * $attempt) }
    }
    return $false
}

function Invoke-ResumableDownload {
    param(
        [string]$Url,
        [string]$Destination,
        [long]$MinimumBytes,
        [int]$Attempts,
        [string]$Label
    )
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) { return $false }
    New-Item -ItemType Directory -Force -Path (Split-Path $Destination -Parent) | Out-Null

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $have = 0
        if (Test-Path $Destination) { $have = (Get-Item $Destination).Length }
        Write-Host "$Label attempt $attempt of $Attempts (saved: $([Math]::Round($have / 1MB, 1)) MB)..." -ForegroundColor Cyan
        & curl.exe -L --fail --retry 8 --retry-all-errors --retry-delay 3 --connect-timeout 30 --speed-time 60 --speed-limit 1024 --continue-at - --output $Destination $Url
        $now = if (Test-Path $Destination) { (Get-Item $Destination).Length } else { 0 }
        if ($LASTEXITCODE -eq 0 -and $now -ge $MinimumBytes) { return $true }
        if ($attempt -lt $Attempts) { Start-Sleep -Seconds ([Math]::Min(90, 5 + (3 * $attempt))) }
    }
    return $false
}

function Import-GGUFIntoOllama {
    param([string]$Ollama, [string]$GGUF, [string]$Name)
    $folder = Split-Path $GGUF -Parent
    $modelfile = Join-Path $folder "$Name.Modelfile"
    @"
FROM ./$(Split-Path $GGUF -Leaf)
PARAMETER num_ctx 4096
"@ | Set-Content -Encoding UTF8 $modelfile
    Push-Location $folder
    try {
        & $Ollama create $Name -f $modelfile
        if ($LASTEXITCODE -ne 0) { throw "Ollama could not import $Name." }
    } finally { Pop-Location }
}

function Try-DirectFallback {
    param([string]$Ollama, [string]$Name)
    if ($Name -eq "qwen3:4b") {
        if (Invoke-ResumableDownload -Url $FourBUrl -Destination $FourBPath -MinimumBytes 2300000000 -Attempts $DirectDownloadAttempts -Label "Qwen3 4B direct download") {
            Import-GGUFIntoOllama -Ollama $Ollama -GGUF $FourBPath -Name "vex-qwen3-4b"
            return $true
        }
    }
    if ($Name -eq "qwen3:1.7b") {
        if (Invoke-ResumableDownload -Url $SmallUrl -Destination $SmallPath -MinimumBytes 1150000000 -Attempts $DirectDownloadAttempts -Label "Qwen3 1.7B direct download") {
            Import-GGUFIntoOllama -Ollama $Ollama -GGUF $SmallPath -Name "vex-qwen3-1.7b"
            return $true
        }
    }
    return $false
}

$ollama = Get-OllamaCommand
if (-not $ollama) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) { throw "Ollama is not installed and winget was not found." }
    Write-Host "Installing Ollama..." -ForegroundColor Cyan
    & winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "Ollama installation failed." }
    Start-Sleep -Seconds 3
    $ollama = Get-OllamaCommand
    if (-not $ollama) { throw "Ollama installed but ollama.exe is not visible yet. Rerun setup after the installer finishes." }
}

Ensure-OllamaHealthy -Ollama $ollama
$hardware = Get-HardwareProfile
$candidates = @(Get-ModelCandidates -Hardware $hardware -Requested $Model)

Write-Host "Hardware probe:" -ForegroundColor Cyan
Write-Host "  RAM: $($hardware.ram_gb) GB"
Write-Host "  Logical CPU: $($hardware.cpu_logical)"
Write-Host "  GPU: $($hardware.gpu_name)"
Write-Host "  GPU memory hint: $($hardware.gpu_vram_gb) GB ($($hardware.gpu_source))"
Write-Host "  Candidate order: $($candidates -join ' -> ')"
Write-Host ""

$chosen = $null
foreach ($candidate in $candidates) {
    if (Test-ModelInstalled -Ollama $ollama -Name $candidate) {
        $chosen = $candidate
        Write-Host "$candidate is already installed." -ForegroundColor Green
        break
    }

    if (Invoke-RegistryPull -Ollama $ollama -Name $candidate) {
        $chosen = $candidate
        break
    }

    if (Try-DirectFallback -Ollama $ollama -Name $candidate) {
        $chosen = $candidate
        break
    }

    Write-Host "$candidate could not be installed; trying the next smaller safe tier." -ForegroundColor Yellow
}

if (-not $chosen) {
    throw "No hardware-appropriate local cognition model could be installed. Existing models were left untouched."
}

New-Item -ItemType Directory -Force -Path $BrainRoot | Out-Null
[pscustomobject]@{
    version = "0.10.9"
    selected_model = $chosen
    hardware = $hardware
    candidates = $candidates
    configured_utc = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $ProfilePath

Write-Host ""
Write-Host "Selected local PC brain: $chosen" -ForegroundColor Green
Write-Host "Profile saved to $ProfilePath" -ForegroundColor Green
Write-Host "Restart VexBridge after setup. Bridge will still step down under memory/art pressure when a smaller installed model is available." -ForegroundColor Green
