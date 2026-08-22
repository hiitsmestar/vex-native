param(
    [ValidateSet("List","Status","Start")]
    [string]$Action = "List",
    [string]$App = ""
)

$ErrorActionPreference = "Stop"
$RegistryPath = Join-Path $PSScriptRoot "VexAppRegistry.json"

if (-not (Test-Path $RegistryPath)) {
    throw "VexAppRegistry.json is missing beside VexAppHost.ps1"
}

$registry = Get-Content -Raw -Path $RegistryPath | ConvertFrom-Json

function Expand-VexValue([string]$Value) {
    if ($null -eq $Value) { return $null }
    $expanded = [Environment]::ExpandEnvironmentVariables($Value)
    $expanded = $expanded.Replace('$TOOLBOX', $PSScriptRoot)
    return $expanded
}

function Get-AppRecord([string]$Id) {
    return @($registry.apps | Where-Object { $_.id -eq $Id }) | Select-Object -First 1
}

function Invoke-Health($record) {
    $health = $record.health
    if ($null -eq $health) {
        return [pscustomobject]@{ ok = $null; state = "unknown"; detail = "No direct health contract yet" }
    }

    switch ([string]$health.type) {
        "file" {
            $path = Expand-VexValue ([string]$health.path)
            return [pscustomobject]@{ ok = (Test-Path $path); state = $(if (Test-Path $path) { "available" } else { "missing" }); detail = $path }
        }
        "http" {
            $url = Expand-VexValue ([string]$health.url)
            try {
                $ProgressPreference = "SilentlyContinue"
                $null = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 3 -ErrorAction Stop
                return [pscustomobject]@{ ok = $true; state = "running"; detail = $url }
            } catch {
                return [pscustomobject]@{ ok = $false; state = "idle-or-unavailable"; detail = $_.Exception.Message }
            }
        }
        "bridge" {
            $cfgPath = Expand-VexValue ([string]$health.config)
            if (-not (Test-Path $cfgPath)) {
                return [pscustomobject]@{ ok = $false; state = "not-configured"; detail = $cfgPath }
            }
            try {
                $cfg = Get-Content -Raw -Path $cfgPath | ConvertFrom-Json
                $port = if ($cfg.port) { [int]$cfg.port } else { 8765 }
                $token = [Uri]::EscapeDataString([string]$cfg.token)
                $old = [System.Net.ServicePointManager]::ServerCertificateValidationCallback
                try {
                    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
                    $reply = Invoke-RestMethod -Uri ("https://127.0.0.1:{0}/status?token={1}" -f $port, $token) -Method Get -TimeoutSec 4 -ErrorAction Stop
                } finally {
                    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $old
                }
                return [pscustomobject]@{ ok = $true; state = "running"; detail = ("Bridge answered on port {0}" -f $port) }
            } catch {
                return [pscustomobject]@{ ok = $false; state = "unavailable"; detail = $_.Exception.Message }
            }
        }
        default {
            return [pscustomobject]@{ ok = $null; state = "unknown"; detail = "Unsupported health type: $($health.type)" }
        }
    }
}

function Find-LaunchExecutable($record) {
    if ($null -eq $record.launch) { return $null }
    if ($record.launch.executable) {
        $candidate = Expand-VexValue ([string]$record.launch.executable)
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
        if (Test-Path $candidate) { return $candidate }
    }
    foreach ($raw in @($record.launch.candidates)) {
        $candidate = Expand-VexValue ([string]$raw)
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Get-LaunchArguments($record) {
    $args = @()
    foreach ($raw in @($record.launch.arguments)) {
        $args += (Expand-VexValue ([string]$raw))
    }
    return $args
}

if ($Action -eq "List") {
    $rows = foreach ($record in $registry.apps) {
        $health = Invoke-Health $record
        [pscustomobject]@{
            Id = $record.id
            Name = $record.name
            Lifecycle = $record.lifecycle
            PreferredNode = $record.preferredNode
            Resource = $record.resourceClass
            State = $health.state
        }
    }
    $rows | Format-Table -AutoSize
    exit 0
}

if ([string]::IsNullOrWhiteSpace($App)) {
    throw "Use -App <id>. Run VexAppHost.ps1 -Action List to see registered app IDs."
}

$record = Get-AppRecord $App
if ($null -eq $record) {
    throw "Unknown Vex app '$App'."
}

if ($Action -eq "Status") {
    $health = Invoke-Health $record
    [pscustomobject]@{
        id = $record.id
        name = $record.name
        lifecycle = $record.lifecycle
        preferredNode = $record.preferredNode
        resourceClass = $record.resourceClass
        health = $health
        installChecks = @($record.installChecks | ForEach-Object {
            $path = Expand-VexValue ([string]$_)
            [pscustomobject]@{ path = $path; exists = (Test-Path $path) }
        })
        managedBy = $record.managedBy
        notes = $record.notes
    } | ConvertTo-Json -Depth 8
    exit 0
}

if ($Action -eq "Start") {
    $before = Invoke-Health $record
    if ($before.ok -eq $true -and $record.id -ne "vexdoctor") {
        Write-Host "$($record.name) is already healthy/running."
        exit 0
    }

    if ($null -eq $record.launch) {
        $manager = if ($record.managedBy) { [string]$record.managedBy } else { "no launcher registered" }
        throw "$($record.name) is not independently launchable yet (managed by: $manager). The registry records this boundary instead of pretending it is modular already."
    }

    $exe = Find-LaunchExecutable $record
    if (-not $exe) {
        throw "No installed launcher candidate was found for $($record.name)."
    }
    $args = Get-LaunchArguments $record
    Start-Process -FilePath $exe -ArgumentList $args | Out-Null
    Write-Host "Started $($record.name)."
    exit 0
}
