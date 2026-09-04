param(
    [ValidateSet('init','ingest','build','status')]
    [string]$Action = 'build',
    [string]$Root = "$env:USERPROFILE\Documents\VexContinuityVault",
    [string]$InputPath = '',
    [int]$Keep = 10
)

$ErrorActionPreference = 'Stop'

$Inbox     = Join-Path $Root 'Inbox'
$Sources   = Join-Path $Root 'Sources'
$Current   = Join-Path $Root 'Current'
$LocalOnly = Join-Path $Root 'LocalOnly'
$State     = Join-Path $Root 'state.json'
$CurrentFile = Join-Path $Current 'VexContinuity_Current.md'

function Ensure-Vault {
    New-Item -ItemType Directory -Force -Path $Root,$Inbox,$Sources,$Current,$LocalOnly | Out-Null
    if (-not (Test-Path $State)) {
        [ordered]@{
            schema = 'vex-continuity-v1'
            keep = $Keep
            created_utc = [DateTime]::UtcNow.ToString('o')
            updated_utc = $null
            source_count = 0
        } | ConvertTo-Json | Set-Content -LiteralPath $State -Encoding UTF8
    }

    $privateReadme = Join-Path $LocalOnly 'README.txt'
    if (-not (Test-Path $privateReadme)) {
        $privateText = @'
Anything placed in this LocalOnly folder is intentionally excluded from VexContinuity_Current.md.
Use it for material that should remain only on this PC.
'@
        Set-Content -LiteralPath $privateReadme -Value $privateText -Encoding UTF8
    }
}

function Import-One([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Input file not found: $Path" }
    $item = Get-Item -LiteralPath $Path
    if ($item.Extension.ToLowerInvariant() -notin @('.txt','.md','.json')) {
        throw 'Only .txt, .md, and .json source snapshots are accepted.'
    }
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmssfff')
    $safe = ($item.BaseName -replace '[^A-Za-z0-9._-]','_')
    $dest = Join-Path $Sources ("{0}-{1}{2}" -f $stamp,$safe,$item.Extension.ToLowerInvariant())
    Copy-Item -LiteralPath $item.FullName -Destination $dest -Force
}

function Import-Inbox {
    Get-ChildItem -LiteralPath $Inbox -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension.ToLowerInvariant() -in @('.txt','.md','.json') } |
        Sort-Object LastWriteTime |
        ForEach-Object {
            Import-One $_.FullName
            Remove-Item -LiteralPath $_.FullName -Force
        }
}

function Rotate-Sources {
    $all = @(Get-ChildItem -LiteralPath $Sources -File | Sort-Object LastWriteTimeUtc -Descending)
    $old = @($all | Select-Object -Skip $Keep)
    foreach ($item in $old) { Remove-Item -LiteralPath $item.FullName -Force }
}

function Build-Current {
    Import-Inbox
    Rotate-Sources
    $keepFiles = @(Get-ChildItem -LiteralPath $Sources -File | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First $Keep)
    $ordered = @($keepFiles | Sort-Object LastWriteTimeUtc)

    $header = @"
# Vex Continuity Current Save

schema: vex-continuity-v1
generated_utc: $([DateTime]::UtcNow.ToString('o'))
source_count: $($ordered.Count)
retention: newest $Keep source snapshots
privacy: private continuity may contain personal information; this file is not intended for public GitHub storage
fact_rule: Star-authored explicit facts/corrections are authoritative; generated assistant text is context unless independently grounded
correction_rule: newest explicit Star correction wins

## Review instructions
Use this file as continuity context for Star and Vex. Preserve source/provenance distinctions. Do not invent missing events or treat assistant-generated speculation as established fact.
"@
    Set-Content -LiteralPath $CurrentFile -Value $header -Encoding UTF8

    $n = 1
    foreach ($file in $ordered) {
        Add-Content -LiteralPath $CurrentFile -Value "`n---`n`n## Recent source $n - $($file.Name)`n" -Encoding UTF8
        try {
            Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | Add-Content -LiteralPath $CurrentFile -Encoding UTF8
        } catch {
            Add-Content -LiteralPath $CurrentFile -Value "[Unreadable source: $($_.Exception.Message)]" -Encoding UTF8
        }
        $n++
    }

    $s = Get-Content -LiteralPath $State -Raw | ConvertFrom-Json
    $s.keep = $Keep
    $s.updated_utc = [DateTime]::UtcNow.ToString('o')
    $s.source_count = $ordered.Count
    $s | ConvertTo-Json | Set-Content -LiteralPath $State -Encoding UTF8
    Write-Host "Vex continuity save updated: $CurrentFile"
}

Ensure-Vault
switch ($Action) {
    'init' { Write-Host "Vex continuity vault ready: $Root" }
    'ingest' {
        if ([string]::IsNullOrWhiteSpace($InputPath)) { throw '-InputPath is required for ingest.' }
        Import-One $InputPath
        Build-Current
    }
    'build' { Build-Current }
    'status' {
        $count = @(Get-ChildItem -LiteralPath $Sources -File -ErrorAction SilentlyContinue).Count
        Write-Host "Root: $Root"
        Write-Host "Stored source snapshots: $count / $Keep"
        Write-Host "Current save: $CurrentFile"
        Write-Host "Current save exists: $(Test-Path $CurrentFile)"
    }
}
