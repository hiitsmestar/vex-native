$ErrorActionPreference = 'Stop'

Write-Host 'Configuring downstairs PC to stay awake on AC power...'
& powercfg.exe /change standby-timeout-ac 0
if ($LASTEXITCODE -ne 0) { throw "Failed to set AC sleep timeout (exit $LASTEXITCODE)" }
& powercfg.exe /change hibernate-timeout-ac 0
if ($LASTEXITCODE -ne 0) { throw "Failed to set AC hibernate timeout (exit $LASTEXITCODE)" }

Write-Host 'Downstairs AC sleep timeout: Never'
Write-Host 'Downstairs AC hibernate timeout: Never'
Write-Host 'Display timeout was left unchanged.'
