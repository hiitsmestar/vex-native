#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path('Bridge/vex_bridge.py')
REMOTE = Path('Tools/VexRemoteSupport.py')
DOCTOR = Path('Tools/VexDoctor.py')
INSTALLER = Path('Tools/VexInstall11722.py')
WATCHDOG = Path('Tools/VexBridgeWatchdog-v11722.ps1')

bridge = BRIDGE.read_text(encoding='utf-8')
remote = REMOTE.read_text(encoding='utf-8')
doctor = DOCTOR.read_text(encoding='utf-8')
installer = INSTALLER.read_text(encoding='utf-8')
watchdog = WATCHDOG.read_text(encoding='utf-8')

for label, text, marker in [
    ('Bridge', bridge, '"version": "0.11.7.22"'),
    ('Remote', remote, 'VERSION = "0.11.7.22"'),
    ('Doctor', doctor, 'VERSION = "0.11.7.22"'),
    ('Installer', installer, "VERSION='0.11.7.22'"),
]:
    if marker not in text:
        raise SystemExit(f'v0.11.7.23 expected {label} v0.11.7.22 marker missing')

# Version the coordinated runtime together so watchdog/installer identity checks agree.
bridge = bridge.replace('"version": "0.11.7.22"', '"version": "0.11.7.23"')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.23"', remote, count=1, flags=re.M)
doctor = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.23"', doctor, count=1, flags=re.M)
installer = installer.replace("VERSION='0.11.7.22'", "VERSION='0.11.7.23'", 1)
watchdog = watchdog.replace('0.11.7.22', '0.11.7.23')

# The GUI used to run gh_ready() and a full Bridge snapshot before mainloop().
# On a broken/unreachable Bridge that can make the window appear to never open.
# Render the window immediately, then do all potentially slow health work on
# background threads and marshal UI updates back through root.after().
old_status = '''    status_var = tk.StringVar(value=gh_ready()[1])\n    tk.Label(root, textvariable=status_var, font=("Segoe UI", 11, "bold")).pack(pady=(0, 8))\n'''
new_status = '''    status_var = tk.StringVar(value="Remote Support ready")\n    tk.Label(root, textvariable=status_var, font=("Segoe UI", 11, "bold")).pack(pady=(0, 8))\n'''
if old_status not in remote:
    raise SystemExit('v0.11.7.23 blocking startup status anchor missing')
remote = remote.replace(old_status, new_status, 1)

old_refresh = '''    def refresh_local() -> None:\n        output.delete("1.0", "end")\n        output.insert("end", json.dumps(collect_snapshot(include_doctor=False), indent=2, ensure_ascii=False))\n'''
new_refresh = '''    def refresh_local() -> None:\n        status_var.set("Refreshing local snapshot…")\n        def work() -> None:\n            try:\n                text = json.dumps(collect_snapshot(include_doctor=False), indent=2, ensure_ascii=False)\n                detail = gh_ready()[1]\n            except Exception as exc:\n                text = json.dumps({"ok": False, "error_class": exc.__class__.__name__}, indent=2)\n                detail = "Remote Support ready"\n            def apply() -> None:\n                output.delete("1.0", "end")\n                output.insert("end", text)\n                status_var.set(detail)\n            root.after(0, apply)\n        threading.Thread(target=work, daemon=True, name="VexRemoteStartupHealth").start()\n'''
if old_refresh not in remote:
    raise SystemExit('v0.11.7.23 refresh anchor missing')
remote = remote.replace(old_refresh, new_refresh, 1)

# Do not launch the initial health scan until Tk has entered its event loop.
old_initial = '''    tk.Button(lower, text="Publish Sanitized Snapshot", command=publish_now, width=24).pack(side="left", padx=4)\n    refresh_local()\n\n    def on_close() -> None:\n'''
new_initial = '''    tk.Button(lower, text="Publish Sanitized Snapshot", command=publish_now, width=24).pack(side="left", padx=4)\n    root.after(250, refresh_local)\n\n    def on_close() -> None:\n'''
if old_initial not in remote:
    raise SystemExit('v0.11.7.23 initial refresh anchor missing')
remote = remote.replace(old_initial, new_initial, 1)

# Windowed PyInstaller builds hide tracebacks. Persist only exception class/message
# to a local crash log and show a small dialog if GUI startup itself fails.
old_entry = '''if __name__ == "__main__":\n    raise SystemExit(main())\n'''
new_entry = '''if __name__ == "__main__":\n    try:\n        raise SystemExit(main())\n    except SystemExit:\n        raise\n    except Exception as exc:\n        try:\n            crash = app_root() / "startup-crash.log"\n            crash.write_text(f"{datetime.now(timezone.utc).isoformat()} {exc.__class__.__name__}: {str(exc)[:500]}\\n", "utf-8")\n        except Exception:\n            pass\n        try:\n            import tkinter as _tk\n            from tkinter import messagebox as _mb\n            _r = _tk.Tk(); _r.withdraw()\n            _mb.showerror("Vex Remote Support", f"Startup failed: {exc.__class__.__name__}")\n            _r.destroy()\n        except Exception:\n            pass\n        raise\n'''
if old_entry not in remote:
    raise SystemExit('v0.11.7.23 entrypoint anchor missing')
remote = remote.replace(old_entry, new_entry, 1)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
DOCTOR.write_text(doctor, encoding='utf-8')
INSTALLER.write_text(installer, encoding='utf-8')
WATCHDOG.write_text(watchdog, encoding='utf-8')

compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')
compile(doctor, str(DOCTOR), 'exec')
compile(installer, str(INSTALLER), 'exec')

for marker in [
    'VERSION = "0.11.7.23"',
    'tk.StringVar(value="Remote Support ready")',
    'root.after(250, refresh_local)',
    'name="VexRemoteStartupHealth"',
    'startup-crash.log',
]:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.23 Remote verifier missing: {marker}')
if '"version": "0.11.7.23"' not in bridge:
    raise SystemExit('v0.11.7.23 Bridge version missing')
if "VERSION='0.11.7.23'" not in installer:
    raise SystemExit('v0.11.7.23 Installer version missing')
if '0.11.7.23' not in watchdog:
    raise SystemExit('v0.11.7.23 Watchdog version missing')

print('Applied v0.11.7.23 nonblocking Remote Support UI startup + crash telemetry')
