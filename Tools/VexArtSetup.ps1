param(
    [string]$ModelUrl = "https://huggingface.co/SG161222/RealVisXL_V5.0_Lightning/resolve/main/RealVisXL_V5.0_Lightning_fp16.safetensors?download=true"
)

$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "VexArt"
$Venv = Join-Path $Root "venv"
$Comfy = Join-Path $Root "ComfyUI"
$CheckpointDir = Join-Path $Comfy "models\checkpoints"
$Checkpoint = Join-Path $CheckpointDir "RealVisXL_V5.0_Lightning_fp16.safetensors"

Write-Host ""
Write-Host "Vex Art Engine Setup v0.9.4 Repair" -ForegroundColor Magenta
Write-Host "==================================" -ForegroundColor Magenta
Write-Host "No paid API. No cloud rendering. The renderer and model stay on this Windows PC." -ForegroundColor White
Write-Host "Default model: RealVisXL V5 Lightning (photoreal SDXL)." -ForegroundColor White
Write-Host ""

function Invoke-ExternalRetry {
    param(
        [string]$Label,
        [scriptblock]$Action,
        [int]$Attempts = 8
    )
    for ($i = 1; $i -le $Attempts; $i++) {
        Write-Host "$Label - attempt $i of $Attempts..." -ForegroundColor Cyan
        & $Action
        if ($LASTEXITCODE -eq 0) { return }
        if ($i -lt $Attempts) {
            $delay = [Math]::Min(90, 8 * $i)
            Write-Host "$Label was interrupted. Retrying in $delay seconds..." -ForegroundColor Yellow
            Start-Sleep -Seconds $delay
        }
    }
    throw "$Label failed after $Attempts attempts."
}

function Test-Python312 {
    param([string]$ExePath)
    if (-not $ExePath -or -not (Test-Path $ExePath)) { return $false }
    try {
        $version = & $ExePath -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"
        return ($version.Trim() -eq "3.12")
    } catch { return $false }
}

function Get-Python312 {
    $candidates = @()
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $resolved = & $py.Source -3.12 -c "import sys; print(sys.executable)" 2>$null
            if ($resolved) { $candidates += $resolved }
        } catch {}
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { $candidates += $python.Source }
    $candidates += @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python\Python312\python.exe"
    )
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Python312 $candidate) { return $candidate }
    }
    return $null
}

function Get-GitExe {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) { return $git.Source }
    $candidates = @(
        "$env:ProgramFiles\Git\cmd\git.exe",
        "$env:ProgramFiles\Git\bin\git.exe",
        "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\git.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

New-Item -ItemType Directory -Force -Path $Root | Out-Null
$winget = Get-Command winget -ErrorAction SilentlyContinue

$PythonCmd = Get-Python312
if (-not $PythonCmd) {
    if (-not $winget) { throw "Python 3.12 and winget were not found. Install Python 3.12, then run this setup again." }
    Write-Host "Installing Python 3.12..." -ForegroundColor Cyan
    & winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 installation failed." }
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Seconds 2
        $PythonCmd = Get-Python312
        if ($PythonCmd) { break }
    }
    if (-not $PythonCmd) { throw "Python 3.12 installed, but python.exe is not visible yet. Close this window and run the setup again." }
}
Write-Host "Python: $PythonCmd" -ForegroundColor Green

# comfy-cli/GitPython requires a real Git executable. Install it automatically and
# point GitPython directly at the executable so this same PowerShell session works.
$GitExe = Get-GitExe
if (-not $GitExe) {
    if (-not $winget) { throw "Git is required for ComfyUI setup and winget was not found." }
    Write-Host "Installing Git for Windows..." -ForegroundColor Cyan
    & winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "Git for Windows installation failed." }
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Seconds 2
        $GitExe = Get-GitExe
        if ($GitExe) { break }
    }
}
if (-not $GitExe) { throw "Git installed but git.exe was not found yet. Close this window and run the setup again." }
$env:GIT_PYTHON_GIT_EXECUTABLE = $GitExe
$gitDir = Split-Path $GitExe -Parent
if (($env:Path -split ';') -notcontains $gitDir) { $env:Path = "$gitDir;$env:Path" }
Write-Host "Git: $GitExe" -ForegroundColor Green

if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Write-Host "Creating the local Vex Art Python environment..." -ForegroundColor Cyan
    & $PythonCmd -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Vex Art Python environment." }
}

$Python = Join-Path $Venv "Scripts\python.exe"
$ComfyCli = Join-Path $Venv "Scripts\comfy.exe"
Invoke-ExternalRetry "Installing comfy-cli" {
    & $Python -m pip install --upgrade pip comfy-cli
} 8

# Clean only a broken/incomplete ComfyUI checkout; keep the venv and downloaded model.
if ((Test-Path $Comfy) -and -not (Test-Path (Join-Path $Comfy "main.py"))) {
    Write-Host "Removing an incomplete ComfyUI checkout from an earlier failed attempt..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $Comfy -ErrorAction SilentlyContinue
}

$gpuText = ((Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join " ").ToLowerInvariant()
$installArgs = @("--skip-prompt", "--workspace", $Root, "install", "--fast-deps", "--skip-manager")
if ($gpuText -match "nvidia") {
    Write-Host "Detected NVIDIA graphics." -ForegroundColor Green
    $installArgs += @("--nvidia", "--cuda-version", "12.6")
} elseif ($gpuText -match "amd|radeon") {
    Write-Host "Detected AMD graphics." -ForegroundColor Green
    $installArgs += "--amd"
} elseif ($gpuText -match "intel" -and $gpuText -match "arc") {
    Write-Host "Detected Intel Arc graphics." -ForegroundColor Green
    $installArgs += "--intel-arc"
} else {
    Write-Host "No supported discrete GPU was confidently detected; installing CPU-capable ComfyUI." -ForegroundColor Yellow
    $installArgs += "--cpu"
}

if (-not (Test-Path (Join-Path $Comfy "main.py"))) {
    Invoke-ExternalRetry "Installing ComfyUI" {
        $env:GIT_PYTHON_GIT_EXECUTABLE = $GitExe
        & $ComfyCli @installArgs
    } 12
} else {
    Write-Host "ComfyUI is already installed in $Comfy" -ForegroundColor Green
}

New-Item -ItemType Directory -Force -Path $CheckpointDir | Out-Null
if (-not (Test-Path $Checkpoint) -or ((Get-Item $Checkpoint).Length -lt 6000000000)) {
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) { throw "Windows curl.exe was not found. Install current Windows updates and run this setup again." }
    Write-Host ""
    Write-Host "Downloading the photoreal model (~7 GB)." -ForegroundColor Cyan
    Write-Host "The download is resumable; repeated runs continue the same file." -ForegroundColor DarkGray
    Invoke-ExternalRetry "Photoreal model download" {
        & curl.exe -L --fail --retry 25 --retry-all-errors --retry-delay 5 --connect-timeout 30 --speed-time 60 --speed-limit 1024 --continue-at - --output $Checkpoint $ModelUrl
    } 30
}

if (-not (Test-Path $Checkpoint)) { throw "The photoreal checkpoint is missing after download." }

$RunCmd = Join-Path $Root "RUN-VEX-ART.cmd"
@"
@echo off
cd /d "$Comfy"
"$Python" main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch
pause
"@ | Set-Content -Encoding ASCII $RunCmd

Write-Host ""
Write-Host "Vex Art Engine is installed." -ForegroundColor Green
Write-Host "ComfyUI: $Comfy" -ForegroundColor Green
Write-Host "Model: $Checkpoint" -ForegroundColor Green
Write-Host "VexBridge v0.9.4 can start it automatically when Star asks for a render." -ForegroundColor Green
