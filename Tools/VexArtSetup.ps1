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
Write-Host "Vex Art Engine Setup v0.9.4" -ForegroundColor Magenta
Write-Host "===========================" -ForegroundColor Magenta
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

New-Item -ItemType Directory -Force -Path $Root | Out-Null

# Python 3.12 is the conservative compatibility choice for ComfyUI + custom tooling.
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Python Launcher and winget were not found. Install Python 3.12, then run this setup again."
    }
    Write-Host "Installing Python 3.12..." -ForegroundColor Cyan
    & winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 installation failed." }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if (-not $py) { throw "Python installed but the Python Launcher is not visible yet. Reopen this setup." }
}

if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Write-Host "Creating the local Vex Art Python environment..." -ForegroundColor Cyan
    & py -3.12 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Vex Art Python environment." }
}

$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"
$ComfyCli = Join-Path $Venv "Scripts\comfy.exe"

Invoke-ExternalRetry "Installing comfy-cli" {
    & $Python -m pip install --upgrade pip comfy-cli
} 8

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
        & $ComfyCli @installArgs
    } 8
} else {
    Write-Host "ComfyUI is already installed in $Comfy" -ForegroundColor Green
}

New-Item -ItemType Directory -Force -Path $CheckpointDir | Out-Null

if (-not (Test-Path $Checkpoint) -or ((Get-Item $Checkpoint).Length -lt 6000000000)) {
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) { throw "Windows curl.exe was not found. Install current Windows updates and run this setup again." }

    Write-Host ""
    Write-Host "Downloading the photoreal model (~7 GB)." -ForegroundColor Cyan
    Write-Host "The download is resumable; unstable internet will not make it start from zero." -ForegroundColor DarkGray
    Invoke-ExternalRetry "Photoreal model download" {
        & curl.exe -L --fail --retry 25 --retry-all-errors --retry-delay 5 --connect-timeout 30 --continue-at - --output $Checkpoint $ModelUrl
    } 12
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
Write-Host "You can also double-click RUN-VEX-ART.cmd in $Root to start it manually." -ForegroundColor Green
