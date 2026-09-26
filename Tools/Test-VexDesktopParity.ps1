param()
$ErrorActionPreference = "Stop"
$required = @(
"get_config","set_config_value","read_file","read_multiple_files","write_file","write_pdf",
"create_directory","list_directory","move_file","start_search","get_more_search_results",
"stop_search","list_searches","get_file_info","edit_block","start_process","read_process_output",
"interact_with_process","force_terminate","list_sessions","list_processes","kill_process"
)
$root = Join-Path $env:LOCALAPPDATA "VexNative\DesktopParity"
if (!(Test-Path (Join-Path $root "package.json"))) { throw "parity runtime not installed" }
$pkg = Get-Content -Raw (Join-Path $root "package.json") | ConvertFrom-Json
if (!$pkg.dependencies.'@wonderwhy-er/desktop-commander') { throw "Desktop Commander engine dependency missing" }
foreach ($file in @("VexDesktopParityNode.mjs","VexDesktopParityHub.mjs","dropbox-call.mjs")) {
    if (!(Test-Path (Join-Path $root $file))) { throw "missing $file" }
}
$state = Join-Path $HOME "Dropbox\VexRemoteBridge\state.json"
if (Test-Path $state) { Write-Host "Dropbox bridge state present." }
Write-Host ("Required substantive Desktop Commander tool surface: " + ($required -join ", "))
Write-Host "v0.15.6 parity static checks passed."
