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
    """Create one stable desktop shortcut that always restarts the currently installed Host."""
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

    desktop = Path(os.environ.get("USERPROFILE") or str(Path.home())) / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    shortcut = desktop / "Restart Vex Host.lnk"
    ps = f'''$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut({str(shortcut)!r})
$s.TargetPath = $env:ComSpec
$s.Arguments = '/c ""{str(helper_path)}""'
$s.WorkingDirectory = {str(home)!r}
$s.IconLocation = {str(host_exe)!r} + ',0'
$s.Description = 'Restart the currently installed Vex Windows Host'
$s.Save()
'''
    result = run_powershell(ps, timeout=20)
    if result.returncode != 0 or not shortcut.exists():
        raise RuntimeError("Could not create Restart Vex Host desktop shortcut")


'''
text = text.replace(marker, helper + marker, 1)

needle = '        for name in RUNTIME_DIRS:\n            replace_dir(pkg / name, home / name)\n'
if needle not in text:
    raise SystemExit('runtime replacement marker missing')
text = text.replace(needle, needle + '\n        # Recreate this every install so the desktop control always follows the newest Host build.\n        install_host_restart_shortcut(home)\n', 1)

path.write_text(text, encoding="utf-8")
print('Applied stable self-updating Restart Vex Host desktop shortcut')
