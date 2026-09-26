param(
    [string]$RepoRoot = (Join-Path $HOME "Documents\vex-native"),
    [string]$Branch = "build/v156-desktop-parity",
    [switch]$EnableLan
)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/hiitsmestar/vex-native.git"

function Require-Git {
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($git) { return $git.Source }
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (!$winget) { throw "git.exe is required and winget is unavailable." }
    & $winget.Source install --id Git.Git -e --accept-source-agreements --accept-package-agreements
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if (!$git) {
        $candidate = Join-Path $env:ProgramFiles "Git\cmd\git.exe"
        if (Test-Path $candidate) { return $candidate }
        throw "git.exe was not available after installation."
    }
    return $git.Source
}

$git = Require-Git
if (Test-Path (Join-Path $RepoRoot ".git")) {
    & $git -C $RepoRoot fetch origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git fetch failed." }
    & $git -C $RepoRoot checkout -B $Branch "origin/$Branch"
    if ($LASTEXITCODE -ne 0) { throw "git checkout failed." }
} else {
    if (Test-Path $RepoRoot) {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        Move-Item $RepoRoot ($RepoRoot + ".pre-v156-" + $stamp)
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $RepoRoot -Parent) | Out-Null
    & $git clone --branch $Branch --single-branch $RepoUrl $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw "git clone failed." }
}

$install = Join-Path $RepoRoot "Tools\Install-VexDesktopParity.ps1"
$dropbox = Join-Path $RepoRoot "Tools\Install-VexDropboxParityBridge.ps1"
if ($EnableLan) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $install -Mode Both
} else {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $install -Mode Both -NoLan
}
if ($LASTEXITCODE -ne 0) { throw "Desktop parity install failed." }

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $dropbox
if ($LASTEXITCODE -ne 0) { throw "Dropbox parity bridge install failed." }

Write-Host "Vex Desktop Parity v0.15.6 bootstrap complete."
