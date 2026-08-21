param(
    [string]$Model = "qwen3:4b",
    [int]$MaxPullAttempts = 30
)

$ErrorActionPreference = "Stop"
Write-Host ""
Write-Host "Vex Brain Setup v0.9.4" -ForegroundColor Magenta
Write-Host "=======================" -ForegroundColor Magenta
Write-Host "This adds a stronger LOCAL conversation brain for VexNative."
Write-Host "The model stays on this Windows PC; VexBridge remains the authenticated LAN gateway."
Write-Host ""

function Get-OllamaCommand {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $common = @(
        "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
        "$env:ProgramFiles\Ollama\ollama.exe"
    )
    foreach ($candidate in $common) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

$ollama = Get-OllamaCommand
if (-not $ollama) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Ollama is not installed and Windows Package Manager (winget) was not found. Install Ollama from its official Windows installer, then run this script again."
    }

    Write-Host "Installing Ollama..." -ForegroundColor Cyan
    & winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    Start-Sleep -Seconds 3
    $ollama = Get-OllamaCommand
    if (-not $ollama) {
        throw "Ollama installation finished but ollama.exe was not found yet. Sign out/in or reopen PowerShell, then run this script again."
    }
}

Write-Host "Ollama: $ollama" -ForegroundColor Green

$healthy = $false
try {
    & $ollama list *> $null
    if ($LASTEXITCODE -eq 0) { $healthy = $true }
} catch {}

if (-not $healthy) {
    Write-Host "Starting the local Ollama service..." -ForegroundColor Cyan
    Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
    foreach ($i in 1..30) {
        Start-Sleep -Milliseconds 500
        try {
            & $ollama list *> $null
            if ($LASTEXITCODE -eq 0) { $healthy = $true; break }
        } catch {}
    }
}

if (-not $healthy) {
    throw "Ollama is installed but its local service did not start. Launch Ollama once from the Start menu, then rerun this script."
}

Write-Host "Pulling local model $Model ..." -ForegroundColor Cyan
Write-Host "The model is about 2.5 GB. Interrupted pulls are resumable; this setup will keep retrying the preserved partial download." -ForegroundColor DarkGray

$pulled = $false
for ($attempt = 1; $attempt -le $MaxPullAttempts; $attempt++) {
    Write-Host ""
    Write-Host "Model download attempt $attempt of $MaxPullAttempts..." -ForegroundColor Cyan
    & $ollama pull $Model
    if ($LASTEXITCODE -eq 0) {
        $pulled = $true
        break
    }

    if ($attempt -lt $MaxPullAttempts) {
        $delay = [Math]::Min(120, 10 + (5 * $attempt))
        Write-Host "The model connection was reset, timed out, or interrupted." -ForegroundColor Yellow
        Write-Host "Ollama keeps the partial blobs. Retrying in $delay seconds..." -ForegroundColor Yellow
        Start-Sleep -Seconds $delay
    }
}

if (-not $pulled) {
    Write-Host ""
    Write-Host "Ollama is installed correctly, but the remote model host never stayed connected long enough." -ForegroundColor Red
    Write-Host "The partial download is still preserved. Running this setup again continues from the saved blobs." -ForegroundColor Yellow
    throw "The model download was repeatedly interrupted by the network."
}

Write-Host ""
Write-Host "Installed local models:" -ForegroundColor Cyan
& $ollama list
Write-Host ""
Write-Host "Vex cognition overlay is ready on this PC. Restart VexBridge.exe, then reopen VexNative." -ForegroundColor Green
Write-Host "You can run this on the other paired PC too for redundancy." -ForegroundColor Green
