#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

REMOTE = Path('Tools/VexRemoteSupport.py')
INSTALLER = Path('Tools/VexInstall11722.py')

remote = REMOTE.read_text(encoding='utf-8')
installer = INSTALLER.read_text(encoding='utf-8')

# Remote Support is intentionally built as PyInstaller one-folder for v0.11.7.29.
# The previous one-file self-extracting executable was blocked by Microsoft Defender
# as virus/PUA on the field PC. Keep Bridge in the installation root while putting
# Remote Support's dependency tree in a dedicated child directory.
old_home = '''    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent
    else:
        candidate = Path(__file__).resolve().parent.parent
    if (candidate / "VexBridge.exe").exists():
'''
new_home = '''    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidate = exe_dir.parent if exe_dir.name == "VexRemoteSupportRuntime" else exe_dir
    else:
        candidate = Path(__file__).resolve().parent.parent
    if (candidate / "VexBridge.exe").exists():
'''
if old_home not in remote:
    raise SystemExit('v0.11.7.29 Defender-safe Remote Support home anchor missing')
remote = remote.replace(old_home, new_home, 1)

old_files = "FILES=['VexBridge.exe','VexRemoteSupport.exe','VexDoctor.exe']"
new_files = "FILES=['VexBridge.exe','VexDoctor.exe']\nREMOTE_DIR='VexRemoteSupportRuntime'"
if old_files not in installer:
    raise SystemExit('v0.11.7.29 Defender-safe installer FILES anchor missing')
installer = installer.replace(old_files, new_files, 1)

replace_anchor = '''def bridge_config()->dict:
'''
copy_tree_helper = '''def replace_tree_with_retry(src:Path,dst:Path,seconds:int=45)->None:
    deadline=time.time()+seconds; last=None
    while time.time()<deadline:
        try:
            staged=dst.with_name(dst.name+'.vexnew')
            backup=dst.with_name(dst.name+'.vexold')
            if staged.exists(): shutil.rmtree(staged,ignore_errors=True)
            shutil.copytree(src,staged)
            exe=staged/'VexRemoteSupport.exe'
            if not exe.exists(): raise RuntimeError('Staged Remote Support executable missing')
            if backup.exists(): shutil.rmtree(backup,ignore_errors=True)
            if dst.exists(): dst.replace(backup)
            staged.replace(dst)
            if backup.exists(): shutil.rmtree(backup,ignore_errors=True)
            return
        except Exception as exc:
            last=exc; time.sleep(0.8)
    raise RuntimeError(f'Could not replace {dst.name}: {last}')

'''
if replace_anchor not in installer:
    raise SystemExit('v0.11.7.29 Defender-safe installer tree-copy anchor missing')
installer = installer.replace(replace_anchor, copy_tree_helper + replace_anchor, 1)

validate_old = '''        for name in FILES:
            if not (pkg/name).exists(): raise RuntimeError(f'Package file missing: {name}')
        stop_all_vex(home)
'''
validate_new = '''        for name in FILES:
            if not (pkg/name).exists(): raise RuntimeError(f'Package file missing: {name}')
        remote_pkg=pkg/REMOTE_DIR
        if not (remote_pkg/'VexRemoteSupport.exe').exists(): raise RuntimeError('Package Remote Support runtime missing')
        stop_all_vex(home)
'''
if validate_old not in installer:
    raise SystemExit('v0.11.7.29 Defender-safe package validation anchor missing')
installer = installer.replace(validate_old, validate_new, 1)

copy_old = '''        for name in FILES:
            dstname='VexBridgeWatchdog.ps1' if name.endswith('v11722.ps1') else name
            replace_with_retry(pkg/name,home/dstname)
        subprocess.Popen([str(home/'VexBridge.exe')],cwd=str(home))
'''
copy_new = '''        for name in FILES:
            dstname='VexBridgeWatchdog.ps1' if name.endswith('v11722.ps1') else name
            replace_with_retry(pkg/name,home/dstname)
        legacy_remote=home/'VexRemoteSupport.exe'
        if legacy_remote.exists():
            retired=home/'VexRemoteSupport.exe.disabled-v11729-onefile'
            try:
                if retired.exists(): retired.unlink()
                legacy_remote.replace(retired)
            except Exception:
                try: legacy_remote.unlink()
                except Exception: pass
        replace_tree_with_retry(remote_pkg,home/REMOTE_DIR)
        subprocess.Popen([str(home/'VexBridge.exe')],cwd=str(home))
'''
if copy_old not in installer:
    raise SystemExit('v0.11.7.29 Defender-safe installer copy anchor missing')
installer = installer.replace(copy_old, copy_new, 1)

launch_old = "        subprocess.Popen([str(home/'VexRemoteSupport.exe')],cwd=str(home))\n"
launch_new = "        subprocess.Popen([str(home/REMOTE_DIR/'VexRemoteSupport.exe')],cwd=str(home))\n"
if launch_old not in installer:
    raise SystemExit('v0.11.7.29 Defender-safe Remote Support launch anchor missing')
installer = installer.replace(launch_old, launch_new, 1)

REMOTE.write_text(remote, encoding='utf-8')
INSTALLER.write_text(installer, encoding='utf-8')
compile(remote, str(REMOTE), 'exec')
compile(installer, str(INSTALLER), 'exec')

for marker in [
    'exe_dir.name == "VexRemoteSupportRuntime"',
    'candidate = exe_dir.parent if exe_dir.name == "VexRemoteSupportRuntime" else exe_dir',
]:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.29 Defender-safe Remote verifier missing: {marker}')
for marker in [
    "REMOTE_DIR='VexRemoteSupportRuntime'",
    'def replace_tree_with_retry',
    "home/REMOTE_DIR/'VexRemoteSupport.exe'",
    'VexRemoteSupport.exe.disabled-v11729-onefile',
]:
    if marker not in installer:
        raise SystemExit(f'v0.11.7.29 Defender-safe installer verifier missing: {marker}')

print('Applied v0.11.7.29 Defender-safe one-folder Remote Support packaging')
