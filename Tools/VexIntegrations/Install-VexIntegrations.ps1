param(
  [string]$ToolsRoot = (Join-Path $env:USERPROFILE 'Documents\VexNativeTools')
)

$ErrorActionPreference='Stop'

$UnlazyCommit='16671491f6679ad9378f52604d3bc2415b4120c7'
$ICMRelease='icm-v0.10.65'
$ICMAsset='icm-x86_64-pc-windows-msvc.zip'

$third=Join-Path $ToolsRoot 'ThirdParty'
$unlazy=Join-Path $third 'unlazy'
$icm=Join-Path $third 'icm'
$state=Join-Path $env:APPDATA 'VexICM'
$db=Join-Path $state 'vexnative-memory.db'
New-Item -ItemType Directory -Force -Path $third,$state | Out-Null

$temp=Join-Path $env:TEMP 'VexIntegrationsInstall'
if(Test-Path $temp){Remove-Item $temp -Recurse -Force}
New-Item -ItemType Directory -Force -Path $temp | Out-Null

# Unlazy: exact commit pin.
$unlazyZip=Join-Path $temp 'unlazy.zip'
Invoke-WebRequest -UseBasicParsing -Uri ("https://github.com/Leonxlnx/unlazy/archive/$UnlazyCommit.zip") -OutFile $unlazyZip
$ux=Join-Path $temp 'unlazy'
Expand-Archive -LiteralPath $unlazyZip -DestinationPath $ux -Force
$root=Get-ChildItem $ux -Directory | Select-Object -First 1
if(-not $root){throw 'Unexpected Unlazy archive layout'}
if(Test-Path $unlazy){Remove-Item $unlazy -Recurse -Force}
Move-Item $root.FullName $unlazy
$uHash=(Get-FileHash $unlazyZip -Algorithm SHA256).Hash.ToLowerInvariant()
@{repo='Leonxlnx/unlazy';commit=$UnlazyCommit;archive_sha256=$uHash} |
  ConvertTo-Json | Set-Content (Join-Path $unlazy 'VEX_PIN.json') -Encoding UTF8

# ICM: exact release pin + publisher checksum verification.
$base="https://github.com/rtk-ai/icm/releases/download/$ICMRelease"
$icmZip=Join-Path $temp $ICMAsset
$checks=Join-Path $temp 'checksums.txt'
Invoke-WebRequest -UseBasicParsing -Uri "$base/$ICMAsset" -OutFile $icmZip
Invoke-WebRequest -UseBasicParsing -Uri "$base/checksums.txt" -OutFile $checks
$line=Get-Content $checks | Where-Object { $_ -match [regex]::Escape($ICMAsset) } | Select-Object -First 1
if(-not $line){throw 'ICM checksum entry missing'}
$expected=($line -split '\s+')[0].ToLowerInvariant()
$actual=(Get-FileHash $icmZip -Algorithm SHA256).Hash.ToLowerInvariant()
if($actual -ne $expected){throw "ICM checksum mismatch expected=$expected actual=$actual"}
if(Test-Path $icm){Remove-Item $icm -Recurse -Force}
New-Item -ItemType Directory -Force -Path $icm | Out-Null
Expand-Archive -LiteralPath $icmZip -DestinationPath $icm -Force
@{repo='rtk-ai/icm';release=$ICMRelease;asset=$ICMAsset;sha256=$actual} |
  ConvertTo-Json | Set-Content (Join-Path $icm 'VEX_PIN.json') -Encoding UTF8

# Stable wrappers.
$icmExe=Join-Path $icm 'icm.exe'
Set-Content (Join-Path $ToolsRoot 'VexICM.cmd') -Encoding ASCII -Value @(
  '@echo off',
  ('"' + $icmExe + '" --db "' + $db + '" --no-embeddings %*')
)
Set-Content (Join-Path $ToolsRoot 'VexUnlazy.cmd') -Encoding ASCII -Value @(
  '@echo off',
  ('node "' + (Join-Path $unlazy 'scripts\gate-check.mjs') + '" %*')
)
Set-Content (Join-Path $ToolsRoot 'VexUnlazyLint.cmd') -Encoding ASCII -Value @(
  '@echo off',
  ('node "' + (Join-Path $unlazy 'scripts\gate-lint.mjs') + '" %*')
)

# Persistent warm ICM HTTP service, localhost only.
$start=Join-Path $ToolsRoot 'Start-VexICM.ps1'
$startBody=@'
$ErrorActionPreference='Stop'
$toolsRoot=Join-Path $env:USERPROFILE 'Documents\VexNativeTools'
$icm=Join-Path $toolsRoot 'ThirdParty\icm\icm.exe'
$db=Join-Path $env:APPDATA 'VexICM\vexnative-memory.db'
$port=11435
$existing=Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if($existing){ exit 0 }
Start-Process -FilePath $icm -ArgumentList @('--db',$db,'--no-embeddings','serve','--http','127.0.0.1:11435') -WindowStyle Hidden
$deadline=(Get-Date).AddSeconds(30)
while((Get-Date)-lt $deadline){
  Start-Sleep -Milliseconds 500
  try {
    $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:11435/health' -TimeoutSec 2
    if($r.StatusCode -eq 200){ exit 0 }
  } catch {}
}
throw 'VexICM HTTP service did not become healthy'
'@
Set-Content $start -Value $startBody -Encoding UTF8
$startup=Join-Path ([Environment]::GetFolderPath('Startup')) 'VexICM.cmd'
Set-Content $startup -Encoding ASCII -Value @(
  '@echo off',
  ('powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $start + '"')
)

# VexNative-readable manifest. No credentials.
$manifestDir=Join-Path $env:APPDATA 'VexNative'
New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
@{
  schema='vex-integrations-v1'
  icm=@{binary=$icmExe;db=$db;http='http://127.0.0.1:11435';mode='fts-keyword';version='0.10.65'}
  unlazy=@{
    dir=$unlazy;commit=$UnlazyCommit
    gateChecker=(Join-Path $unlazy 'scripts\gate-check.mjs')
    gateLint=(Join-Path $unlazy 'scripts\gate-lint.mjs')
    executionApprovalRequired=$true
  }
  a2a=@{
    protocol='A2A 1.0'
    coordinator='http://127.0.0.1:8800'
    agentCard='http://127.0.0.1:8800/.well-known/agent-card.json'
    registry='http://127.0.0.1:8800/registry'
    provider='VexBridgeMCP package'
  }
  authority=@{
    continuity=(Join-Path $env:USERPROFILE 'Documents\VexContinuityVault')
    rule='ICM is auxiliary retrieval only; newest Star-authored corrections and verified live state override ICM.'
  }
} | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $manifestDir 'integrations.json') -Encoding UTF8

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $start
& $icmExe --version
node (Join-Path $unlazy 'scripts\gate-check.mjs') --help | Select-Object -First 2
Write-Output 'VEX_INTEGRATIONS_INSTALL=PASS'
