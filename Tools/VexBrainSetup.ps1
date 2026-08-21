param(
    [string]$Model = "qwen3:4b"
)

$ErrorActionPreference = "Stop"
Write-Host ""
Write-Host "Vex Brain Setup v0.9.3" -ForegroundColor Magenta
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

# Ollama's Windows app normally keeps its local service running. If it is not
# answering yet, start a local-only serve process and wait briefly.
$healthy = $false
try {
    & $ollama list *> $null
    if ($LASTEXITCODE -eq 0) { $healthy = $true }
} catch {}

if (-not $healthy) {
    Write-Host "Starting the local Ollama service..." -ForegroundColor Cyan
    Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
    foreach ($i in 1..20) {
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
Write-Host "This is a one-time download and may take a while depending on the model." -ForegroundColor DarkGray
& $ollama pull $Model
if ($LASTEXITCODE -ne 0) {
    throw "The model download failed."
}

Write-Host ""
Write-Host "Installed local models:" -ForegroundColor Cyan
& $ollama list
Write-Host ""
Write-Host "Vex cognition overlay is ready on this PC. Restart VexBridge.exe, then reopen VexNative." -ForegroundColor Green
Write-Host "You can run this on the other paired PC too for redundancy." -ForegroundColor Green
