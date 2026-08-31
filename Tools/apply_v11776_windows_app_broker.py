#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
bridge = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

for marker in [
    '"agent_runtime_bundle": "0.11.7.75"',
    'parsed.path == "/windows/capabilities"',
    'parsed.path == "/autolearn/run"',
    'pc-memory-star-query-v11775',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.76 expected Bridge marker missing: {marker}")
if 'BUNDLE_VERSION = "0.11.7.75"' not in installer:
    raise SystemExit("v0.11.7.76 expected installer .75")

insert_anchor = "def _vex_background_services() -> None:\n"
if insert_anchor not in bridge:
    raise SystemExit("v0.11.7.76 background-service insertion anchor missing")

layer = r'''
# ---------------------------------------------------------------------------
# v0.11.7.76 Windows Application Broker
# Local authenticated device-action surface. It can inventory and launch known
# installed applications, but never accepts arbitrary command lines or raw paths.
# Every mutating action receives a local audit receipt.
# ---------------------------------------------------------------------------
VEX_DEVICE_ACTION_LOG = CONFIG_PATH.parent / "device-actions.jsonl"
_V11776_APP_ALIASES = {
    "explorer": {"name": "File Explorer", "target": "explorer.exe", "kind": "exe"},
    "file explorer": {"name": "File Explorer", "target": "explorer.exe", "kind": "exe"},
    "notepad": {"name": "Notepad", "target": "notepad.exe", "kind": "exe"},
    "calculator": {"name": "Calculator", "target": "calc.exe", "kind": "exe"},
    "calc": {"name": "Calculator", "target": "calc.exe", "kind": "exe"},
    "settings": {"name": "Settings", "target": "ms-settings:", "kind": "uri"},
    "powershell": {"name": "Windows PowerShell", "target": "powershell.exe", "kind": "exe"},
    "cmd": {"name": "Command Prompt", "target": "cmd.exe", "kind": "exe"},
    "command prompt": {"name": "Command Prompt", "target": "cmd.exe", "kind": "exe"},
    "task manager": {"name": "Task Manager", "target": "taskmgr.exe", "kind": "exe"},
}


def _v11776_audit(action: str, detail: dict) -> None:
    try:
        record = {
            "time": time.time(),
            "version": "0.11.7.76",
            "action": str(action or "")[:80],
            "detail": detail,
        }
        VEX_DEVICE_ACTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with VEX_DEVICE_ACTION_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _v11776_start_apps() -> list[dict]:
    rows: list[dict] = []
    if os.name != "nt":
        return rows
    try:
        import subprocess
        script = "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        raw = str(completed.stdout or "").strip()
        if completed.returncode == 0 and raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                parsed = [parsed]
            if isinstance(parsed, list):
                for item in parsed[:500]:
                    if not isinstance(item, dict):
                        continue
                    name = re.sub(r"\s+", " ", str(item.get("Name") or "")).strip()
                    appid = re.sub(r"\s+", " ", str(item.get("AppID") or "")).strip()
                    if name and appid:
                        rows.append({"name": name[:240], "app_id": appid[:700], "kind": "start-app"})
    except Exception:
        pass
    return rows


def _v11776_app_catalog(limit: int = 250) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for value in _V11776_APP_ALIASES.values():
        key = value["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": value["name"], "kind": value["kind"], "source": "builtin"})
    for item in _v11776_start_apps():
        key = str(item.get("name") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"name": item["name"], "kind": item["kind"], "source": "start-menu"})
        if len(out) >= max(1, min(int(limit or 250), 500)):
            break
    return out


def _v11776_resolve_app(name: str) -> dict | None:
    query = re.sub(r"\s+", " ", str(name or "")).strip().lower()
    if not query:
        return None
    alias = _V11776_APP_ALIASES.get(query)
    if alias:
        return dict(alias)
    apps = _v11776_start_apps()
    exact = [x for x in apps if str(x.get("name") or "").lower() == query]
    if exact:
        return exact[0]
    prefix = [x for x in apps if str(x.get("name") or "").lower().startswith(query)]
    if len(prefix) == 1:
        return prefix[0]
    contains = [x for x in apps if query in str(x.get("name") or "").lower()]
    if len(contains) == 1:
        return contains[0]
    return None


def _v11776_launch_app(name: str, dry_run: bool = False) -> dict:
    resolved = _v11776_resolve_app(name)
    if resolved is None:
        return {"ok": False, "version": "0.11.7.76", "error": "application not uniquely resolved"}
    public = {"name": str(resolved.get("name") or name)[:240], "kind": str(resolved.get("kind") or "")[:40]}
    if dry_run:
        return {"ok": True, "version": "0.11.7.76", "dry_run": True, "app": public}
    if os.name != "nt":
        return {"ok": False, "version": "0.11.7.76", "error": "Windows application broker is unavailable"}
    try:
        import subprocess
        kind = str(resolved.get("kind") or "")
        if kind == "start-app":
            appid = str(resolved.get("app_id") or "").strip()
            if not appid:
                raise RuntimeError("missing app id")
            subprocess.Popen(
                ["explorer.exe", "shell:AppsFolder\\" + appid],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        elif kind == "uri":
            target = str(resolved.get("target") or "").strip()
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            target = str(resolved.get("target") or "").strip()
            if not target or any(ch in target for ch in "&|><;`\n\r"):
                raise RuntimeError("unsafe target")
            subprocess.Popen(
                [target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        _v11776_audit("launch_app", public)
        return {"ok": True, "version": "0.11.7.76", "launched": True, "app": public}
    except Exception as exc:
        return {"ok": False, "version": "0.11.7.76", "error": exc.__class__.__name__, "app": public}


'''
if "def _v11776_launch_app(" not in bridge:
    bridge = bridge.replace(insert_anchor, layer + insert_anchor, 1)

get_anchor = '        if parsed.path == "/windows/capabilities":\n'
get_route = '''        if parsed.path == "/windows/apps":\n            apps = _v11776_app_catalog(limit=300)\n            self._json(200, {"ok": True, "version": "0.11.7.76", "count": len(apps), "apps": apps})\n            return\n\n'''
if 'parsed.path == "/windows/apps"' not in bridge:
    if get_anchor not in bridge:
        raise SystemExit("v0.11.7.76 Windows GET anchor missing")
    bridge = bridge.replace(get_anchor, get_route + get_anchor, 1)

post_anchor = '        if parsed.path == "/autolearn/run":\n'
post_route = '''        if parsed.path == "/windows/launch":\n            name = str(body.get("name") or body.get("app") or "").strip()\n            dry_run = bool(body.get("dry_run"))\n            result = _v11776_launch_app(name, dry_run=dry_run)\n            self._json(200 if result.get("ok") else 400, result)\n            return\n\n'''
if 'parsed.path == "/windows/launch"' not in bridge:
    if post_anchor not in bridge:
        raise SystemExit("v0.11.7.76 POST anchor missing")
    bridge = bridge.replace(post_anchor, post_route + post_anchor, 1)

bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.75"', '"agent_runtime_bundle": "0.11.7.76"', 1)
installer = installer.replace('BUNDLE_VERSION = "0.11.7.75"', 'BUNDLE_VERSION = "0.11.7.76"', 1)
installer = installer.replace('Vex Agent Runtime v0.11.7.75', 'Vex Agent Runtime v0.11.7.76')

BRIDGE.write_text(bridge, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(installer, str(INSTALLER), "exec")

required = [
    '"agent_runtime_bundle": "0.11.7.76"',
    'def _v11776_app_catalog(', 'def _v11776_resolve_app(', 'def _v11776_launch_app(',
    'parsed.path == "/windows/apps"', 'parsed.path == "/windows/launch"',
    'VEX_DEVICE_ACTION_LOG', '"dry_run": True', 'pc-memory-star-query-v11775',
]
for marker in required:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.76 Bridge marker missing: {marker}")
if 'BUNDLE_VERSION = "0.11.7.76"' not in installer:
    raise SystemExit("v0.11.7.76 installer identity missing")
print("Applied v0.11.7.76 Windows application broker")
