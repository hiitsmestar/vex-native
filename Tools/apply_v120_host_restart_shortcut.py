#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexAgentRuntimeInstall.py")
text = path.read_text(encoding="utf-8")
marker = 'def main() -> None:\n'
if 'def install_host_restart_shortcut(home: Path) -> None:' in text:
    print('v0.12 host restart shortcut patch already applied')
    raise SystemExit(0)
if marker not in text:
    raise SystemExit('VexAgentRuntimeInstall main marker missing')

helper = r'''def install_host_restart_shortcut(home: Path) -> None:
    helper_path = home / "Restart Vex Host.cmd"
    host_exe = home / "VexWindowsHost" / "VexWindowsHost.exe"
    helper_text = "\r\n".join([
        "@echo off",
        "setlocal",
        "taskkill /IM VexWindowsHost.exe /F >nul 2>&1",
        "timeout /t 1 /nobreak >nul",
        f'start "" "{host_exe}"',
        "exit /b 0",
        "",
    ])
    helper_path.write_text(helper_text, encoding="utf-8")

    ps = f"""$ws = New-Object -ComObject WScript.Shell
$desktop = $ws.SpecialFolders.Item('Desktop')
if (-not $desktop) {{ throw 'Desktop not found' }}
$shortcut = Join-Path $desktop 'Restart Vex Host.lnk'
$s = $ws.CreateShortcut($shortcut)
$s.TargetPath = $env:ComSpec
$s.Arguments = '/c ""{str(helper_path)}""'
$s.WorkingDirectory = {str(home)!r}
$s.IconLocation = {str(host_exe)!r} + ',0'
$s.Save()
$fallback = Join-Path $desktop 'Restart Vex Host.cmd'
Set-Content -LiteralPath $fallback -Value '@echo off`r`ncall "{str(helper_path)}"`r`n' -Encoding ASCII
if (!(Test-Path -LiteralPath $shortcut)) {{ throw 'Shortcut missing' }}
if (!(Test-Path -LiteralPath $fallback)) {{ throw 'Fallback missing' }}
"""
    result = run_powershell(ps, timeout=20)
    if result.returncode != 0:
        raise RuntimeError("Could not create Restart Vex Host desktop controls")


'''
text = text.replace(marker, helper + marker, 1)
lines = text.splitlines(keepends=True)
insert_at = None
for i, line in enumerate(lines):
    if line.strip() != 'for name in RUNTIME_DIRS:':
        continue
    loop_indent = len(line) - len(line.lstrip())
    j = i + 1
    while j < len(lines):
        stripped = lines[j].strip()
        indent = len(lines[j]) - len(lines[j].lstrip())
        if stripped and indent <= loop_indent:
            break
        if 'replace_dir(pkg / name, home / name)' in stripped:
            insert_at = j + 1
            break
        j += 1
    if insert_at is not None:
        break
if insert_at is None:
    raise SystemExit('runtime replacement loop missing')
call_indent = ' ' * loop_indent
lines.insert(insert_at, f'\n{call_indent}install_host_restart_shortcut(home)\n')
text = ''.join(lines)
path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")
if 'install_host_restart_shortcut(home)' not in text:
    raise SystemExit('Host restart shortcut call missing after patch')
print('Applied Restart Vex Host desktop controls')
