param([int]$Port = 8765, [string]$InstallRoot = "$env:LOCALAPPDATA\VexBridgeAgent")
$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Copy-Item "$SourceRoot\server.py" "$InstallRoot\server.py" -Force
Copy-Item "$SourceRoot\requirements.txt" "$InstallRoot\requirements.txt" -Force
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Python launcher 'py' was not found." }
$Venv = Join-Path $InstallRoot ".venv"
if (-not (Test-Path "$Venv\Scripts\python.exe")) { & py -3 -m venv $Venv }
& "$Venv\Scripts\python.exe" -m pip install --upgrade pip
& "$Venv\Scripts\python.exe" -m pip install -r "$InstallRoot\requirements.txt"
$ConfigDir = Join-Path $env:APPDATA "VexBridge"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
$Roots = @(Get-PSDrive -PSProvider FileSystem | ForEach-Object { $_.Root } | Where-Object { $_ })
$Config = @{ allowedRoots=$Roots; fileReadLineLimit=1000; searchResultLimit=500 } | ConvertTo-Json -Depth 4
Set-Content -Path (Join-Path $ConfigDir "config.json") -Value $Config -Encoding UTF8
$Launcher = Join-Path $InstallRoot "run-vexbridge.ps1"
$LauncherLines = @('$env:VEXBRIDGE_HOST = "127.0.0.1"', '$env:VEXBRIDGE_PORT = "' + $Port + '"', '& "' + $Venv + '\Scripts\python.exe" "' + $InstallRoot + '\server.py"')
Set-Content -Path $Launcher -Value $LauncherLines -Encoding UTF8
$TaskName = "VexBridge MCP Agent"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + $Launcher + '"')
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2
Write-Host "Installed VexBridge at $InstallRoot"
Write-Host "MCP endpoint: http://127.0.0.1:$Port/mcp"
Write-Host ("Allowed roots: " + ($Roots -join ", "))