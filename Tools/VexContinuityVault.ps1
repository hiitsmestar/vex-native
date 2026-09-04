param(
    [ValidateSet('init','ingest','build','status')]
    [string]$Action = 'build',
    [string]$Root = "$env:USERPROFILE\Documents\VexContinuityVault",
    [string]$InputPath = '',
    [int]$Keep = 10
)

$ErrorActionPreference = 'Stop'

$Inbox          = Join-Path $Root 'Inbox'
$Sources        = Join-Path $Root 'Sources'
$ThreadArchives = Join-Path $Root 'ThreadArchives'
$Current        = Join-Path $Root 'Current'
$LocalOnly      = Join-Path $Root 'LocalOnly'
$State          = Join-Path $Root 'state.json'
$CurrentFile    = Join-Path $Current 'VexContinuity_Current.md'

function Ensure-Vault {
    New-Item -ItemType Directory -Force -Path $Root,$Inbox,$Sources,$ThreadArchives,$Current,$LocalOnly | Out-Null
    if (-not (Test-Path $State)) {
        [ordered]@{
            schema = 'vex-continuity-v2'
            keep = $Keep
            created_utc = [DateTime]::UtcNow.ToString('o')
            updated_utc = $null
            source_count = 0
            thread_archive_count = 0
        } | ConvertTo-Json | Set-Content -LiteralPath $State -Encoding UTF8
    }

    $privateReadme = Join-Path $LocalOnly 'README.txt'
    if (-not (Test-Path $privateReadme)) {
        $privateText = @'
Anything placed in this LocalOnly folder is intentionally excluded from VexContinuity_Current.md and Dropbox sync.
Use it for material that should remain only on this PC.
'@
        Set-Content -LiteralPath $privateReadme -Value $privateText -Encoding UTF8
    }
}

function Find-DropboxRoot {
    $candidates = @()
    if ($env:DROPBOX) { $candidates += $env:DROPBOX }
    $candidates += (Join-Path $env:USERPROFILE 'Dropbox')
    $candidates += (Join-Path $env:USERPROFILE 'Dropbox (Personal)')

    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate -PathType Container)) {
            return $candidate
        }
    }
    return $null
}

function Test-IsThreadArchive([System.IO.FileInfo]$Item) {
    if ($Item.BaseName -match '(?i)(thread|conversation|transcript|chat[-_ ]?export)') { return $true }
    if ($Item.Extension.ToLowerInvariant() -eq '.html') { return $true }
    try {
        $head = Get-Content -LiteralPath $Item.FullName -TotalCount 30 -ErrorAction Stop | Out-String
        if ($head -match '(?i)vex-thread-archive-v1') { return $true }
    } catch { }
    return $false
}

function Sync-CurrentToDropbox {
    if (-not (Test-Path -LiteralPath $CurrentFile -PathType Leaf)) { return $null }
    $dropboxRoot = Find-DropboxRoot
    if (-not $dropboxRoot) {
        Write-Host 'Dropbox sync skipped: local Dropbox folder not found yet.'
        return $null
    }

    $destDir = Join-Path $dropboxRoot 'VexContinuity'
    $destThreads = Join-Path $destDir 'ThreadArchives'
    New-Item -ItemType Directory -Force -Path $destDir,$destThreads | Out-Null

    $dest = Join-Path $destDir 'VexContinuity_Current.md'
    Copy-Item -LiteralPath $CurrentFile -Destination $dest -Force

    $localThreads = @(Get-ChildItem -LiteralPath $ThreadArchives -File -ErrorAction SilentlyContinue)
    foreach ($thread in $localThreads) {
        Copy-Item -LiteralPath $thread.FullName -Destination (Join-Path $destThreads $thread.Name) -Force
    }

    $allowed = @{}
    foreach ($thread in $localThreads) { $allowed[$thread.Name.ToLowerInvariant()] = $true }
    Get-ChildItem -LiteralPath $destThreads -File -ErrorAction SilentlyContinue | ForEach-Object {
        if (-not $allowed.ContainsKey($_.Name.ToLowerInvariant())) {
            Remove-Item -LiteralPath $_.FullName -Force
        }
    }

    Write-Host "Dropbox continuity copy updated: $dest"
    Write-Host "Dropbox thread archives synced: $($localThreads.Count)"
    return $dest
}

function Import-One([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Input file not found: $Path" }
    $item = Get-Item -LiteralPath $Path
    if ($item.Extension.ToLowerInvariant() -notin @('.txt','.md','.json','.html')) {
        throw 'Only .txt, .md, .json, and .html continuity files are accepted.'
    }

    $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmssfff')
    $safe = ($item.BaseName -replace '[^A-Za-z0-9._-]','_')
    $ext = $item.Extension.ToLowerInvariant()

    if (Test-IsThreadArchive $item) {
        $dest = Join-Path $ThreadArchives ("{0}-{1}{2}" -f $stamp,$safe,$ext)
        Copy-Item -LiteralPath $item.FullName -Destination $dest -Force
        Write-Host "Thread archive ingested: $dest"
    } else {
        $dest = Join-Path $Sources ("{0}-{1}{2}" -f $stamp,$safe,$ext)
        Copy-Item -LiteralPath $item.FullName -Destination $dest -Force
        Write-Host "Continuity summary ingested: $dest"
    }
}

function Import-Inbox {
    Get-ChildItem -LiteralPath $Inbox -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension.ToLowerInvariant() -in @('.txt','.md','.json','.html') } |
        Sort-Object LastWriteTime |
        ForEach-Object {
            Import-One $_.FullName
            Remove-Item -LiteralPath $_.FullName -Force
        }
}

function Rotate-Folder([string]$Path) {
    $all = @(Get-ChildItem -LiteralPath $Path -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending)
    $old = @($all | Select-Object -Skip $Keep)
    foreach ($item in $old) { Remove-Item -LiteralPath $item.FullName -Force }
}

function Build-Current {
    Import-Inbox
    Rotate-Folder $Sources
    Rotate-Folder $ThreadArchives

    $keepFiles = @(Get-ChildItem -LiteralPath $Sources -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First $Keep)
    $ordered = @($keepFiles | Sort-Object LastWriteTimeUtc)
    $threads = @(Get-ChildItem -LiteralPath $ThreadArchives -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First $Keep)

    $header = @"
# Vex Continuity Current Save

schema: vex-continuity-v2
generated_utc: $([DateTime]::UtcNow.ToString('o'))
summary_source_count: $($ordered.Count)
thread_archive_count: $($threads.Count)
retention: newest $Keep summary snapshots and newest $Keep full-thread archives
privacy: private continuity may contain personal information; these contents are not intended for public GitHub storage
fact_rule: Star-authored explicit facts/corrections are authoritative; generated assistant text is context unless independently grounded
correction_rule: newest explicit Star correction wins

## Review instructions
Read this current save first. When exact wording, chronology, corrections, or subtle continuity matters, search/read the referenced full-thread archives in Dropbox /VexContinuity/ThreadArchives instead of guessing from the summary. Preserve provenance distinctions and do not invent missing events.
"@
    Set-Content -LiteralPath $CurrentFile -Value $header -Encoding UTF8

    if ($threads.Count -gt 0) {
        Add-Content -LiteralPath $CurrentFile -Value "`n## Full thread archives`n" -Encoding UTF8
        foreach ($thread in ($threads | Sort-Object LastWriteTimeUtc)) {
            Add-Content -LiteralPath $CurrentFile -Value ("- /VexContinuity/ThreadArchives/{0}" -f $thread.Name) -Encoding UTF8
        }
    }

    $n = 1
    foreach ($file in $ordered) {
        Add-Content -LiteralPath $CurrentFile -Value "`n---`n`n## Recent continuity summary $n - $($file.Name)`n" -Encoding UTF8
        try {
            Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | Add-Content -LiteralPath $CurrentFile -Encoding UTF8
        } catch {
            Add-Content -LiteralPath $CurrentFile -Value "[Unreadable source: $($_.Exception.Message)]" -Encoding UTF8
        }
        $n++
    }

    try {
        $s = Get-Content -LiteralPath $State -Raw | ConvertFrom-Json
    } catch {
        $s = [pscustomobject]@{}
    }
    $newState = [ordered]@{
        schema = 'vex-continuity-v2'
        keep = $Keep
        created_utc = if ($s.created_utc) { $s.created_utc } else { [DateTime]::UtcNow.ToString('o') }
        updated_utc = [DateTime]::UtcNow.ToString('o')
        source_count = $ordered.Count
        thread_archive_count = $threads.Count
    }
    $newState | ConvertTo-Json | Set-Content -LiteralPath $State -Encoding UTF8

    Write-Host "Vex continuity save updated: $CurrentFile"
    Write-Host "Summary snapshots retained: $($ordered.Count) / $Keep"
    Write-Host "Full thread archives retained: $($threads.Count) / $Keep"
    [void](Sync-CurrentToDropbox)
}

Ensure-Vault
switch ($Action) {
    'init' {
        Write-Host "Vex continuity vault ready: $Root"
        Write-Host "Full thread archive folder: $ThreadArchives"
        $dropboxRoot = Find-DropboxRoot
        if ($dropboxRoot) { Write-Host "Dropbox detected: $dropboxRoot" }
    }
    'ingest' {
        if ([string]::IsNullOrWhiteSpace($InputPath)) { throw '-InputPath is required for ingest.' }
        Import-One $InputPath
        Build-Current
    }
    'build' { Build-Current }
    'status' {
        $count = @(Get-ChildItem -LiteralPath $Sources -File -ErrorAction SilentlyContinue).Count
        $threadCount = @(Get-ChildItem -LiteralPath $ThreadArchives -File -ErrorAction SilentlyContinue).Count
        Write-Host "Root: $Root"
        Write-Host "Stored continuity summaries: $count / $Keep"
        Write-Host "Stored full thread archives: $threadCount / $Keep"
        Write-Host "Current save: $CurrentFile"
        Write-Host "Current save exists: $(Test-Path $CurrentFile)"
        $dropboxRoot = Find-DropboxRoot
        if ($dropboxRoot) {
            $dropboxFile = Join-Path (Join-Path $dropboxRoot 'VexContinuity') 'VexContinuity_Current.md'
            $dropboxThreads = Join-Path (Join-Path $dropboxRoot 'VexContinuity') 'ThreadArchives'
            Write-Host "Dropbox root: $dropboxRoot"
            Write-Host "Dropbox continuity copy: $dropboxFile"
            Write-Host "Dropbox continuity copy exists: $(Test-Path $dropboxFile)"
            Write-Host "Dropbox thread archive folder: $dropboxThreads"
        } else {
            Write-Host 'Dropbox root: not detected'
        }
    }
}
