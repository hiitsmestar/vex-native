param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\VexNative\ContinuityVault"
)

$ErrorActionPreference = 'Stop'
$Source = Join-Path $PSScriptRoot 'VexContinuityVault.ps1'
if (-not (Test-Path -LiteralPath $Source)) { throw "Missing $Source" }

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
$Dest = Join-Path $InstallRoot 'VexContinuityVault.ps1'
Copy-Item -LiteralPath $Source -Destination $Dest -Force

$DocsRoot = Join-Path $env:USERPROFILE 'Documents\VexContinuityVault'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Dest -Action init -Root $DocsRoot

$UpdateCmd = @"
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$Dest" -Action build -Root "$DocsRoot"
pause
"@
Set-Content -LiteralPath (Join-Path $InstallRoot 'Update-VexContinuity.bat') -Value $UpdateCmd -Encoding ASCII

$StatusCmd = @"
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$Dest" -Action status -Root "$DocsRoot"
pause
"@
Set-Content -LiteralPath (Join-Path $InstallRoot 'VexContinuity-Status.bat') -Value $StatusCmd -Encoding ASCII

$Desktop = [Environment]::GetFolderPath('Desktop')
$Shortcut = Join-Path $Desktop 'Update Vex Continuity.bat'
Copy-Item -LiteralPath (Join-Path $InstallRoot 'Update-VexContinuity.bat') -Destination $Shortcut -Force

Write-Host ''
Write-Host 'Vex Continuity Vault installed.'
Write-Host "Private vault: $DocsRoot"
Write-Host "Drop thread/session .txt, .md, or .json files into: $DocsRoot\Inbox"
Write-Host "Current save will be: $DocsRoot\Current\VexContinuity_Current.md"
Write-Host 'Nothing in this vault is uploaded to GitHub by this installer.'
