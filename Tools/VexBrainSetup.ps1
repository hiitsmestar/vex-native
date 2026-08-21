param(
    [string]$Model = "qwen3:4b",
    [int]$RegistryAttempts = 3,
    [int]$DirectDownloadAttempts = 60
)

$ErrorActionPreference = "Stop"
$BrainRoot = Join-Path $env:LOCALAPPDATA "VexBrain"
$ModelDir = Join-Path $BrainRoot "models"
$GGUFPath = Join-Path $ModelDir "Qwen3-4B-Q4_K_M.gguf"
$GGUFUrl = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf?download=true"
$FallbackSmallPath = Join-Path $ModelDir "Qwen3-1.7B-Q4_K_M.gguf"
$FallbackSmallUrl = "https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf?download=true"

Write-Host ""
Write-Host "Vex Brain Setup v0.9.4 Network Repair" -ForegroundColor Magenta
Write-Host "=======================================" -ForegroundColor Magenta
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

function Model-AlreadyInstalled {
    param([string]$Ollama)
    try {
        $rows = & $Ollama list 2>$null | Out-String
        return ($rows -match "qwen3:4b" -or $rows -match "vex-qwen3-4b" -or $rows -match "Qwen3-4B-GGUF" -or $rows -match "vex-qwen3-1.7b")
    } catch { return $false }
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
    if (-not $curl) { throw "Windows curl.exe was not found." }
    New-Item -ItemType Directory -Force -Path (Split-Path $Destination -Parent) | Out-Null

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $have = 0
        if (Test-Path $Destination) { $have = (Get-Item $Destination).Length }
        $haveMB = [Math]::Round($have / 1MB, 1)
        Write-Host ""
        Write-Host "$Label attempt $attempt of $Attempts (already saved: $haveMB MB)..." -ForegroundColor Cyan
        & curl.exe -L --fail --retry 8 --retry-all-errors --retry-delay 3 --connect-timeout 30 --speed-time 60 --speed-limit 1024 --continue-at - --output $Destination $Url
        $now = 0
        if (Test-Path $Destination) { $now = (Get-Item $Destination).Length }
        if ($LASTEXITCODE -eq 0 -and $now -ge $MinimumBytes) { return $true }
        if ($attempt -lt $Attempts) {
            $delay = [Math]::Min(90, 5 + (3 * $attempt))
            Write-Host "Connection dropped. The partial file is preserved; retrying in $delay seconds..." -ForegroundColor Yellow
            Start-Sleep -Seconds $delay
        }
    }
    return $false
}

function Import-GGUFIntoOllama {
    param(
        [string]$Ollama,
        [string]$GGUF,
        [string]$Name
    )
    $folder = Split-Path $GGUF -Parent
    $modelfile = Join-Path $folder "$Name.Modelfile"
    @"
FROM ./$(Split-Path $GGUF -Leaf)
PARAMETER num_ctx 8192
"@ | Set-Content -Encoding UTF8 $modelfile
    Push-Location $folder
    try {
        & $Ollama create $Name -f $modelfile
        if ($LASTEXITCODE -ne 0) { throw "Ollama could not import the downloaded GGUF." }
    } finally {
        Pop-Location
    }
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
    if (-not $ollama) { throw "Ollama installed but ollama.exe is not visible yet. Close this window and rerun setup." }
}

Write-Host "Ollama: $ollama" -ForegroundColor Green
Ensure-OllamaHealthy -Ollama $ollama

if (Model-AlreadyInstalled -Ollama $ollama) {
    Write-Host "A compatible Vex cognition model is already installed." -ForegroundColor Green
} else {
    Write-Host "Trying Ollama's normal registry first..." -ForegroundColor Cyan
    $pulled = $false
    for ($attempt = 1; $attempt -le $RegistryAttempts; $attempt++) {
        Write-Host "Registry attempt $attempt of $RegistryAttempts..." -ForegroundColor Cyan
        & $ollama pull $Model
        if ($LASTEXITCODE -eq 0) { $pulled = $true; break }
        if ($attempt -lt $RegistryAttempts) { Start-Sleep -Seconds (10 * $attempt) }
    }

    if (-not $pulled) {
        Write-Host ""
        Write-Host "The Ollama registry route is repeatedly timing out." -ForegroundColor Yellow
        Write-Host "Switching to a resumable direct Hugging Face download of the same Qwen3 4B Q4_K_M model." -ForegroundColor Yellow
        $fourB = Invoke-ResumableDownload -Url $GGUFUrl -Destination $GGUFPath -MinimumBytes 2300000000 -Attempts $DirectDownloadAttempts -Label "Qwen3 4B direct download"
        if ($fourB) {
            Import-GGUFIntoOllama -Ollama $ollama -GGUF $GGUFPath -Name "vex-qwen3-4b"
            $pulled = $true
        } else {
            Write-Host ""
            Write-Host "The 4B file still could not finish on this connection." -ForegroundColor Yellow
            Write-Host "Falling back to Qwen3 1.7B Q4_K_M (~1.28 GB) so Vex still gets a much stronger PC brain than the onboard tiny model." -ForegroundColor Yellow
            $small = Invoke-ResumableDownload -Url $FallbackSmallUrl -Destination $FallbackSmallPath -MinimumBytes 1150000000 -Attempts $DirectDownloadAttempts -Label "Qwen3 1.7B fallback download"
            if ($small) {
                Import-GGUFIntoOllama -Ollama $ollama -GGUF $FallbackSmallPath -Name "vex-qwen3-1.7b"
                $pulled = $true
            }
        }
    }

    if (-not $pulled) {
        throw "Neither the Ollama registry nor the resumable Hugging Face fallback could finish on this connection. Partial files are preserved for the next run."
    }
}

Write-Host ""
Write-Host "Installed local models:" -ForegroundColor Cyan
& $ollama list
Write-Host ""
Write-Host "Vex cognition overlay is ready on this PC. Restart VexBridge.exe, then reopen VexNative." -ForegroundColor Green
Write-Host "You can run this on the other paired PC too for redundancy." -ForegroundColor Green
