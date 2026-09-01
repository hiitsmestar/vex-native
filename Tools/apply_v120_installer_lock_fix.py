#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
installer = INSTALLER.read_text(encoding="utf-8")

# The cumulative assembler can apply this field-hardening immediately before the
# v0.12 conversation/bootstrap layer.  Accept either the proven .80 baseline or
# an already-bumped v0.12 installer; this patch is version-neutral and only
# strengthens live-directory replacement behavior.
if 'BUNDLE_VERSION = "0.12.0"' not in installer and 'BUNDLE_VERSION = "0.11.7.80"' not in installer:
    raise SystemExit("v0.12 installer lock fix expected .80 or v0.12.0 installer")

replace_file_anchor = "\n\ndef replace_file(src: Path, dst: Path) -> None:\n"
if replace_file_anchor not in installer:
    raise SystemExit("v0.12 installer lock fix could not find replace_file anchor")

helper = r'''

def stop_processes_using_install_path(root: Path) -> None:
    """Stop helper/child processes whose executable or command line points into an old Vex install."""
    root_text = str(root.resolve()).rstrip("\\/")
    quoted = root_text.replace("'", "''")
    script = f"""
$ErrorActionPreference='SilentlyContinue'
$root='{quoted}'
$deadline=(Get-Date).AddSeconds(12)
do {{
  $targets=@(Get-CimInstance Win32_Process | Where-Object {{
    ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($root,[System.StringComparison]::OrdinalIgnoreCase)) -or
    ($_.CommandLine -and $_.CommandLine.IndexOf($root,[System.StringComparison]::OrdinalIgnoreCase) -ge 0)
  }})
  $targets | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
  Start-Sleep -Milliseconds 350
  $left=@(Get-CimInstance Win32_Process | Where-Object {{
    ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($root,[System.StringComparison]::OrdinalIgnoreCase)) -or
    ($_.CommandLine -and $_.CommandLine.IndexOf($root,[System.StringComparison]::OrdinalIgnoreCase) -ge 0)
  }})
}} while ($left.Count -gt 0 -and (Get-Date) -lt $deadline)
"""
    try:
        run_powershell(script, timeout=20)
    except Exception:
        # The directory-swap retry loop is the final authority.  This helper is
        # best-effort because a just-exited child can disappear between CIM reads.
        pass
'''

if "def stop_processes_using_install_path(" not in installer:
    installer = installer.replace(replace_file_anchor, helper + replace_file_anchor, 1)

start = installer.find("def replace_dir(src: Path, dst: Path) -> None:\n")
end = installer.find("\n\ndef local_bridge_get(", start)
if start < 0 or end < 0:
    raise SystemExit("v0.12 installer lock fix could not find replace_dir block")

new_replace_dir = r'''def replace_dir(src: Path, dst: Path) -> None:
    # Use per-install staging names so a previous interrupted install cannot poison
    # the next attempt with a stale .vexnew directory.
    nonce = f"{os.getpid()}-{int(time.time() * 1000)}"
    staged = dst.with_name(dst.name + ".vexnew-" + nonce)
    old = dst.with_name(dst.name + ".vexold-" + nonce)
    shutil.copytree(src, staged)

    last: Exception | None = None
    for attempt in range(18):
        try:
            # Remote Support can have short-lived gh/PowerShell children whose
            # working/executable path keeps this directory locked after the GUI exits.
            stop_processes_using_install_path(dst.parent)
            if dst.exists():
                if old.exists():
                    shutil.rmtree(old)
                dst.replace(old)
            staged.replace(dst)
            shutil.rmtree(old, ignore_errors=True)
            return
        except OSError as exc:
            last = exc
            winerror = getattr(exc, "winerror", None)
            if not isinstance(exc, PermissionError) and winerror not in (5, 32):
                raise
            # A persistent support/watchdog race may relaunch a process between
            # the first stop and the rename.  Re-quiesce and retry instead of
            # deleting the destination with errors ignored.
            stop_known_vex_processes()
            stop_processes_using_install_path(dst.parent)
            time.sleep(min(0.35 + attempt * 0.12, 1.5))

    # If the old directory was already moved aside but the staged promotion never
    # succeeded, restore it so an install failure leaves the previous runtime usable.
    if not dst.exists() and old.exists():
        try:
            old.replace(dst)
        except Exception:
            pass
    try:
        shutil.rmtree(staged, ignore_errors=True)
    except Exception:
        pass
    detail = f"{last.__class__.__name__}: {last}" if last else "unknown Windows lock"
    raise RuntimeError(f"Could not replace {dst.name} after quiescing the old runtime: {detail}")
'''
installer = installer[:start] + new_replace_dir + installer[end:]

main_anchor = "        home = find_home()\n        stop_known_vex_processes()\n\n        for name in ROOT_FILES:\n"
main_replacement = "        home = find_home()\n        stop_known_vex_processes()\n        stop_processes_using_install_path(home)\n\n        for name in ROOT_FILES:\n"
if main_anchor in installer:
    installer = installer.replace(main_anchor, main_replacement, 1)
elif "        stop_processes_using_install_path(home)\n" not in installer:
    raise SystemExit("v0.12 installer lock fix could not find main quiesce anchor")

INSTALLER.write_text(installer, encoding="utf-8")
compile(installer, str(INSTALLER), "exec")

checks = [
    "def stop_processes_using_install_path(",
    "for attempt in range(18):",
    "stop_processes_using_install_path(dst.parent)",
    "stop_processes_using_install_path(home)",
    "Could not replace {dst.name} after quiescing the old runtime",
]
for marker in checks:
    if marker not in installer:
        raise SystemExit(f"v0.12 installer lock fix missing marker: {marker}")
print("Applied v0.12 installer live-lock retry/rollback fix")
