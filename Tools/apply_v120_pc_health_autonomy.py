#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
PROOF = Path("Tools/ci_v120_postbuild_wants_proof.py")

bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")
proof = PROOF.read_text(encoding="utf-8")

if '"agent_runtime_bundle": "0.12.0"' not in bridge:
    raise SystemExit("v0.12 PC health layer requires v0.12 generated Bridge")
if 'VERSION = "0.11.7.69"' not in remote and 'VERSION = "0.11.7.70"' not in remote:
    raise SystemExit("v0.12 PC health layer requires Remote Support .69/.70 source")

# Ensure helpers have the standard-library modules they use even if an older
# generated Bridge omitted them.
if "import shutil\n" not in bridge:
    bridge = bridge.replace("import secrets\n", "import secrets\nimport shutil\n", 1)
if "import subprocess\n" not in bridge:
    bridge = bridge.replace("import ssl\n", "import ssl\nimport subprocess\n", 1)

V120_LAYER = r'''
# ---------------------------------------------------------------------------
# v0.12 PC health + conservative self-maintenance + idle-work rotation
# ---------------------------------------------------------------------------
V120_PC_HEALTH_AUTONOMY = "v0.12-pc-health-autonomy-v1"
V120_IDLE_ROTATION = "v0.12-idle-productive-rotation-v1"
_V120_HEALTH_RECENT_HOURS = 4
_V120_HEALTH_AUTO_BOOT_GRACE_SECONDS = 3600
_V120_HEALTH_AUTO_INTERVAL_SECONDS = 24 * 3600
_V120_HEALTH_RESEARCH_COOLDOWN_SECONDS = 30 * 60
_V120_HEALTH_LAST_RESEARCH_FINGERPRINT = ""
_V120_HEALTH_LAST_RESEARCH_AT = 0.0


def _v120_health_known_vex_family(name: str) -> str:
    low = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    families = [
        ("vex-agent-runtime", "agent-runtime"),
        ("vexremotesupport", "remote-support"),
        ("vex-remote-support", "remote-support"),
        ("vexbridge", "bridge"),
        ("vex-bridge", "bridge"),
        ("vexwindowshost", "windows-host"),
        ("vex-windows-host", "windows-host"),
        ("vexdoctor", "doctor"),
        ("vex-doctor", "doctor"),
        ("vextoolbox", "toolbox"),
        ("vex-toolbox", "toolbox"),
    ]
    for prefix, family in families:
        if low.startswith(prefix):
            return family
    return ""


def _v120_health_file_item(path: Path, kind: str, family: str = "") -> dict:
    stat = path.stat()
    return {
        "path": str(path),
        "bytes": int(stat.st_size),
        "mtime": float(stat.st_mtime),
        "kind": kind,
        "family": family,
    }


def _v120_health_temp_candidates() -> list[dict]:
    now = time.time()
    cutoff = now - 72 * 3600
    roots: list[Path] = []
    for raw in [
        os.environ.get("TEMP"),
        os.environ.get("TMP"),
        str(Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Temp"),
    ]:
        if not raw:
            continue
        path = Path(raw)
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        if resolved not in roots:
            roots.append(resolved)
    found: list[dict] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        try:
            iterator = root.rglob("*")
            for path in iterator:
                if len(found) >= 8000:
                    break
                try:
                    if not path.is_file() or path.is_symlink():
                        continue
                    stat = path.stat()
                    if stat.st_mtime > cutoff:
                        continue
                    key = os.path.normcase(str(path.resolve()))
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(_v120_health_file_item(path, "old-temp"))
                except Exception:
                    continue
        except Exception:
            continue
    return found


def _v120_health_download_candidates() -> tuple[list[dict], list[dict]]:
    """Conservative policy: auto-delete only unmistakable old Vex package files.

    Never auto-delete arbitrary installers/archives and never auto-delete extracted
    directories because the active Vex home itself can intentionally live under
    Downloads/Desktop. Extracted Vex folders are review-only until the active home
    is explicitly identified.
    """
    now = time.time()
    recent_cutoff = now - _V120_HEALTH_RECENT_HOURS * 3600
    safe_exts = {".zip", ".7z", ".rar", ".exe", ".msi", ".msix", ".msixbundle"}
    generic_review_exts = safe_exts | {".iso"}
    roots = [Path.home() / "Downloads", Path.home() / "Desktop"]
    candidates: list[dict] = []
    review: list[dict] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        try:
            entries = list(root.iterdir())[:12000]
        except Exception:
            continue
        for path in entries:
            try:
                if path.is_symlink():
                    continue
                family = _v120_health_known_vex_family(path.name)
                if path.is_dir():
                    # Deliberately do not recurse/delete package folders: the active
                    # installed Vex home may itself be one of these directories.
                    if family:
                        review.append({
                            "path": str(path), "bytes": 0, "mtime": float(path.stat().st_mtime),
                            "kind": "vex-folder-review", "family": family,
                        })
                    continue
                if not path.is_file():
                    continue
                suffix = path.suffix.lower()
                stat = path.stat()
                if family and suffix in safe_exts:
                    candidates.append(_v120_health_file_item(path, "old-vex-package", family))
                    continue
                if suffix in generic_review_exts and stat.st_mtime <= now - 30 * 86400:
                    review.append(_v120_health_file_item(path, "generic-package-review"))
                elif path.name.lower().startswith("vex") and suffix in generic_review_exts:
                    review.append(_v120_health_file_item(path, "unclassified-vex-package-review"))
            except Exception:
                continue

    # Keep every recent file and the newest file in each known Vex family. Rapid
    # build churn can create many same-family archives in a day, so age alone is
    # not the cleanup criterion.
    newest: dict[str, dict] = {}
    for item in candidates:
        family = str(item.get("family") or "")
        current = newest.get(family)
        if current is None or float(item.get("mtime") or 0) > float(current.get("mtime") or 0):
            newest[family] = item
    protected = {os.path.normcase(str(item["path"])) for item in newest.values()}
    safe: list[dict] = []
    for item in candidates:
        path_key = os.path.normcase(str(item.get("path") or ""))
        if path_key in protected:
            continue
        if float(item.get("mtime") or 0) > recent_cutoff:
            continue
        safe.append(item)
    return safe, review


def _v120_health_housekeeping_audit() -> dict:
    try:
        temp = _v120_health_temp_candidates()
        packages, review = _v120_health_download_candidates()
        safe = temp + packages
        usage = shutil.disk_usage(Path.home().anchor or r"C:\")
        return {
            "ok": True,
            "policy_version": V120_PC_HEALTH_AUTONOMY,
            "safe_temp_files": len(temp),
            "safe_temp_bytes": sum(int(x.get("bytes") or 0) for x in temp),
            "safe_cache_files": 0,
            "safe_cache_bytes": 0,
            "auto_installer_files": len(packages),
            "auto_installer_bytes": sum(int(x.get("bytes") or 0) for x in packages),
            "approval_required_files": len(review),
            "approval_required_bytes": sum(int(x.get("bytes") or 0) for x in review),
            "safe_reclaimable_bytes": sum(int(x.get("bytes") or 0) for x in safe),
            "disk": {"total": int(usage.total), "used": int(usage.used), "free": int(usage.free)},
            "protected": [
                "newest Vex package per family", "files modified in the last 4 hours",
                "all extracted Vex folders", "all arbitrary installers and generic archives",
                "documents", "photos", "video", "music", "installed applications",
                "Windows/system files", "Vex/Ollama/ComfyUI models",
            ],
            "samples": {
                "safe_temp": [x["path"] for x in temp[:8]],
                "safe_vex_packages": [x["path"] for x in packages[:12]],
                "approval_required": [x["path"] for x in review[:12]],
            },
        }
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__, "policy_version": V120_PC_HEALTH_AUTONOMY}


def _v120_health_delete_items(items: list[dict]) -> tuple[int, int, int]:
    deleted = 0
    reclaimed = 0
    skipped = 0
    allowed_roots = []
    for root in [Path.home() / "Downloads", Path.home() / "Desktop"]:
        try:
            allowed_roots.append(root.resolve())
        except Exception:
            pass
    temp_roots = []
    for raw in [os.environ.get("TEMP"), os.environ.get("TMP"), os.environ.get("LOCALAPPDATA")]:
        if raw:
            try:
                p = Path(raw).resolve()
                if raw == os.environ.get("LOCALAPPDATA"):
                    p = (p / "Temp").resolve()
                temp_roots.append(p)
            except Exception:
                pass
    for item in items:
        raw = str(item.get("path") or "")
        path = Path(raw)
        try:
            if not path.exists() or not path.is_file() or path.is_symlink():
                continue
            resolved = path.resolve()
            kind = str(item.get("kind") or "")
            if kind == "old-vex-package":
                if not any(root == resolved.parent for root in allowed_roots):
                    skipped += 1
                    continue
                family = _v120_health_known_vex_family(path.name)
                if not family:
                    skipped += 1
                    continue
            elif kind == "old-temp":
                if not any(root == resolved or root in resolved.parents for root in temp_roots):
                    skipped += 1
                    continue
            else:
                skipped += 1
                continue
            size = int(path.stat().st_size)
            path.unlink()
            if not path.exists():
                deleted += 1
                reclaimed += size
        except Exception:
            skipped += 1
    return deleted, reclaimed, skipped


def _v120_health_state_path() -> Path:
    root = CONFIG_PATH.parent / "maintenance"
    root.mkdir(parents=True, exist_ok=True)
    return root / "v120-health-state.json"


def _v120_health_load_state() -> dict:
    try:
        value = json.loads(_v120_health_state_path().read_text("utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _v120_health_save_state(value: dict) -> None:
    try:
        _v120_health_state_path().write_text(json.dumps(value, indent=2), "utf-8")
    except Exception:
        pass


def _v120_health_clean_safe() -> dict:
    audit = _v120_health_housekeeping_audit()
    if not audit.get("ok"):
        return {"ok": False, "error": str(audit.get("error") or "audit failed")[:120]}
    temp = _v120_health_temp_candidates()
    packages, review = _v120_health_download_candidates()
    deleted, reclaimed, skipped = _v120_health_delete_items(temp + packages)
    state = _v120_health_load_state()
    state.update({
        "last_safe_clean": time.time(),
        "last_reclaimed_bytes": int(reclaimed),
        "last_deleted_files": int(deleted),
        "policy_version": V120_PC_HEALTH_AUTONOMY,
    })
    _v120_health_save_state(state)
    try:
        if STATE is not None and getattr(STATE, "index", None) is not None:
            threading.Thread(target=STATE.index.rebuild, daemon=True, name="VexV120PostCleanupReindex").start()
    except Exception:
        pass
    return {
        "ok": True,
        "deleted_safe_files": int(deleted),
        "reclaimed_bytes": int(reclaimed),
        "approval_required_files": len(review),
        "approval_required_bytes": sum(int(x.get("bytes") or 0) for x in review),
        "optimized_drives": 0,
        "skipped": int(skipped),
        "policy_version": V120_PC_HEALTH_AUTONOMY,
        "note": "Only conservative safe items were deleted; ambiguous archives/installers and all extracted Vex folders remain for review.",
    }


def _v120_health_maintenance_status() -> dict:
    audit = _v120_health_housekeeping_audit()
    state = _v120_health_load_state()
    return {
        "ok": bool(audit.get("ok")),
        "state": state,
        "safe_reclaimable_bytes": int(audit.get("safe_reclaimable_bytes") or 0),
        "approval_required_files": int(audit.get("approval_required_files") or 0),
        "approval_required_bytes": int(audit.get("approval_required_bytes") or 0),
        "auto_maintenance": True,
        "safe_cleanup_interval_hours": 24,
        "drive_optimize_interval_days": 0,
        "policy_version": V120_PC_HEALTH_AUTONOMY,
        "optimization_policy": "not automatic; media type must be inspected first",
    }


def _v120_health_run_maintenance(force_optimize: bool = False) -> dict:
    # `force_optimize` is intentionally ignored in v1. Disk optimization is not
    # performed until /hardware/status identifies media and we explicitly choose it.
    result = _v120_health_clean_safe()
    result["maintenance"] = True
    result["optimization_requested"] = bool(force_optimize)
    result["optimization_deferred"] = bool(force_optimize)
    result["optimized_drives"] = 0
    state = _v120_health_load_state()
    state["last_maintenance"] = time.time()
    _v120_health_save_state(state)
    return result


def _v120_health_maintenance_loop() -> None:
    # Preserve a one-hour post-install audit window for field validation, then
    # maintain only conservative safe categories on a daily cadence.
    time.sleep(_V120_HEALTH_AUTO_BOOT_GRACE_SECONDS)
    while True:
        try:
            state = _v120_health_load_state()
            now = time.time()
            last = float(state.get("last_safe_clean") or 0)
            if now - last >= _V120_HEALTH_AUTO_INTERVAL_SECONDS:
                audit = _v120_health_housekeeping_audit()
                if audit.get("ok") and int(audit.get("safe_reclaimable_bytes") or 0) >= 256 * 1024 * 1024:
                    _v120_health_run_maintenance(force_optimize=False)
        except Exception:
            pass
        time.sleep(30 * 60)


# Alias the legacy housekeeping names so existing routes/background wiring call
# the v0.12 conservative implementations even if old source-generating layers are present.
_hk_audit = _v120_health_housekeeping_audit
_hk_clean_safe = _v120_health_clean_safe
_hk_maintenance_status = _v120_health_maintenance_status
_hk_run_maintenance = _v120_health_run_maintenance
_hk_maintenance_loop = _v120_health_maintenance_loop


def _v120_health_hardware_status() -> dict:
    result = {
        "ok": True,
        "version": V120_PC_HEALTH_AUTONOMY,
        "platform": sys.platform,
        "cpu": {}, "memory": {}, "os": {}, "physical_disks": [],
        "logical_disks": [], "pagefile": {}, "gpus": [],
        "privacy": "serial numbers, UUIDs, MAC addresses, usernames and product keys are not collected",
    }
    if os.name != "nt":
        try:
            usage = shutil.disk_usage(Path.home().anchor or "/")
            result["logical_disks"] = [{"drive": str(Path.home().anchor or "/"), "size_gb": round(usage.total / 2**30, 1), "free_gb": round(usage.free / 2**30, 1)}]
        except Exception:
            pass
        return result
    script = r'''$ErrorActionPreference='Stop'
$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1
$cs=Get-CimInstance Win32_ComputerSystem
$os=Get-CimInstance Win32_OperatingSystem
$physical=@(Get-CimInstance Win32_DiskDrive | ForEach-Object {
  [pscustomobject]@{model=$_.Model; media_type=$_.MediaType; interface_type=$_.InterfaceType; size_gb=[math]::Round([double]$_.Size/1GB,1)}
})
$logical=@(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
  [pscustomobject]@{drive=$_.DeviceID; filesystem=$_.FileSystem; size_gb=[math]::Round([double]$_.Size/1GB,1); free_gb=[math]::Round([double]$_.FreeSpace/1GB,1)}
})
$pages=@(Get-CimInstance Win32_PageFileUsage | ForEach-Object {
  $drive=if ($_.Name -match '^([A-Za-z]:)') {$matches[1]} else {''}
  [pscustomobject]@{drive=$drive; allocated_mb=[int]$_.AllocatedBaseSize; current_mb=[int]$_.CurrentUsage; peak_mb=[int]$_.PeakUsage}
})
$gpus=@(Get-CimInstance Win32_VideoController | ForEach-Object {
  [pscustomobject]@{name=$_.Name; adapter_ram_gb=if ($_.AdapterRAM) {[math]::Round([double]$_.AdapterRAM/1GB,1)} else {0}}
})
[pscustomobject]@{
  cpu=[pscustomobject]@{name=$cpu.Name; physical_cores=[int]$cpu.NumberOfCores; logical_processors=[int]$cpu.NumberOfLogicalProcessors; max_clock_mhz=[int]$cpu.MaxClockSpeed}
  memory=[pscustomobject]@{total_gb=[math]::Round([double]$cs.TotalPhysicalMemory/1GB,1); available_gb=[math]::Round([double]$os.FreePhysicalMemory/1MB,1)}
  os=[pscustomobject]@{caption=$os.Caption; version=$os.Version; build=$os.BuildNumber}
  physical_disks=$physical
  logical_disks=$logical
  pagefile=[pscustomobject]@{automatic_managed=[bool]$cs.AutomaticManagedPagefile; files=$pages}
  gpus=$gpus
} | ConvertTo-Json -Depth 6 -Compress'''
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=18,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            raise RuntimeError("PowerShell hardware probe failed")
        value = json.loads(str(completed.stdout or "").strip())
        if not isinstance(value, dict):
            raise RuntimeError("hardware probe returned non-object")
        for key in ["cpu", "memory", "os", "physical_disks", "logical_disks", "pagefile", "gpus"]:
            result[key] = value.get(key) if value.get(key) is not None else result[key]
    except Exception as exc:
        result["ok"] = False
        result["error_class"] = exc.__class__.__name__
    return result


def _v120_health_public_gap_topics(snapshot: dict) -> list[str]:
    topics: list[str] = []
    rows = snapshot.get("open_gaps") if isinstance(snapshot, dict) else []
    if not isinstance(rows, list):
        return topics
    for row in rows:
        if not isinstance(row, dict):
            continue
        category = str(row.get("category") or "capability").lower()
        if category in {"preference", "naturalness", "conversation", "identity", "relationship"}:
            continue
        goal = str(row.get("request_text") or row.get("request") or "")
        detail = str(row.get("detail") or "")
        try:
            topic = str(_autonomy_public_research_topic(category, goal, detail) or "").strip()
        except Exception:
            topic = ""
        if topic:
            topics.append(topic[:700])
    return topics


def _v120_health_rotation_decision(snapshot: dict, reason: str) -> dict:
    slot = int(time.time() // 240) % 3
    choices = [
        ("probe_capability", "system_health"),
        ("rehearse_skills", "capability_mastery"),
        ("review_experience", "grounded_independence"),
    ]
    action, goal = choices[slot]
    return {"action": action, "goal_key": goal, "reason": reason, "source": V120_IDLE_ROTATION}


_v120_health_choose_action_base = globals().get("_initiative_choose_action")
if callable(_v120_health_choose_action_base):
    def _initiative_choose_action(snapshot: dict) -> dict:
        global _V120_HEALTH_LAST_RESEARCH_FINGERPRINT, _V120_HEALTH_LAST_RESEARCH_AT
        decision = _v120_health_choose_action_base(snapshot)
        if not isinstance(decision, dict) or str(decision.get("action") or "") != "research_open_gap":
            return decision
        topics = _v120_health_public_gap_topics(snapshot)
        if not topics:
            return _v120_health_rotation_decision(snapshot, "open gap is private/nontechnical or has no public-safe research topic")
        fingerprint = "|".join(sorted(topics))[:2400]
        now = time.time()
        if fingerprint == _V120_HEALTH_LAST_RESEARCH_FINGERPRINT and now - _V120_HEALTH_LAST_RESEARCH_AT < _V120_HEALTH_RESEARCH_COOLDOWN_SECONDS:
            return _v120_health_rotation_decision(snapshot, "same public research gap is inside productive-work cooldown")
        _V120_HEALTH_LAST_RESEARCH_FINGERPRINT = fingerprint
        _V120_HEALTH_LAST_RESEARCH_AT = now
        return decision
'''

handler_anchor = "class Handler(BaseHTTPRequestHandler):\n"
if "V120_PC_HEALTH_AUTONOMY =" not in bridge:
    if handler_anchor not in bridge:
        raise SystemExit("v0.12 PC health Handler anchor missing")
    bridge = bridge.replace(handler_anchor, V120_LAYER + "\n\n" + handler_anchor, 1)

# Guarantee the health routes exist after every source-generating layer. Existing
# housekeeping routes automatically use our aliases.
get_anchor = '        if parsed.path == "/housekeeping/audit":\n'
if 'parsed.path == "/hardware/status"' not in bridge:
    if get_anchor not in bridge:
        raise SystemExit("v0.12 PC health housekeeping GET anchor missing")
    get_routes = '''        if parsed.path == "/hardware/status":\n            value = _v120_health_hardware_status()\n            self._json(200 if value.get("ok") else 503, value)\n            return\n\n        if parsed.path == "/maintenance/status":\n            self._json(200, _v120_health_maintenance_status())\n            return\n\n'''
    # Avoid a duplicate maintenance route if an old generated layer still has one.
    if 'parsed.path == "/maintenance/status"' in bridge:
        get_routes = get_routes.replace('        if parsed.path == "/maintenance/status":\n            self._json(200, _v120_health_maintenance_status())\n            return\n\n', '')
    bridge = bridge.replace(get_anchor, get_routes + get_anchor, 1)

post_anchor = '        if parsed.path in ("/housekeeping/clean", "/housekeeping/restore", "/housekeeping/purge"):\n'
if 'parsed.path == "/maintenance/run"' not in bridge:
    if post_anchor not in bridge:
        raise SystemExit("v0.12 PC health housekeeping POST anchor missing")
    maintenance_post = '''        if parsed.path == "/maintenance/run":\n            try:\n                length = int(self.headers.get("Content-Length", "0") or "0")\n                payload = {}\n                if length > 0:\n                    raw = self.rfile.read(min(length, 64 * 1024))\n                    payload = json.loads(raw.decode("utf-8")) if raw else {}\n                    if not isinstance(payload, dict):\n                        payload = {}\n                result = _v120_health_run_maintenance(force_optimize=bool(payload.get("optimize") is True))\n                self._json(200 if result.get("ok") else 500, result)\n            except Exception as exc:\n                self._json(500, {"ok": False, "error": exc.__class__.__name__})\n            return\n\n'''
    bridge = bridge.replace(post_anchor, maintenance_post + post_anchor, 1)

# Remote Support .70: expose only the safe hardware profile. It deliberately does
# not expose serials, user paths, MACs, tokens, or raw process/window details.
remote = re.sub(r'^VERSION = "0\.11\.7\.(?:69|70)"', 'VERSION = "0.11.7.70"', remote, count=1, flags=re.M)
remote_helper_anchor = "def maintenance_public(value: dict) -> dict:\n"
remote_helpers = r'''def hardware_public(value: dict) -> dict:
    if not isinstance(value, dict):
        return {"ok": False}
    safe = {
        "ok": yes(value.get("ok")),
        "version": str(value.get("version") or "")[:80] or None,
        "platform": str(value.get("platform") or "")[:40] or None,
        "cpu": value.get("cpu") if isinstance(value.get("cpu"), dict) else {},
        "memory": value.get("memory") if isinstance(value.get("memory"), dict) else {},
        "os": value.get("os") if isinstance(value.get("os"), dict) else {},
        "physical_disks": value.get("physical_disks") if isinstance(value.get("physical_disks"), list) else [],
        "logical_disks": value.get("logical_disks") if isinstance(value.get("logical_disks"), list) else [],
        "pagefile": value.get("pagefile") if isinstance(value.get("pagefile"), dict) else {},
        "gpus": value.get("gpus") if isinstance(value.get("gpus"), list) else [],
    }
    # Defense in depth: reject any accidental sensitive key if the Bridge schema expands.
    forbidden = {"serial", "serialnumber", "uuid", "mac", "token", "productkey", "username", "user"}
    def scrub(obj):
        if isinstance(obj, dict):
            return {str(k)[:80]: scrub(v) for k, v in obj.items() if str(k).lower().replace("_", "") not in forbidden}
        if isinstance(obj, list):
            return [scrub(x) for x in obj[:32]]
        if isinstance(obj, str):
            return obj[:240]
        return obj
    return scrub(safe)


'''
if "def hardware_public(" not in remote:
    if remote_helper_anchor not in remote:
        raise SystemExit("v0.12 PC health Remote helper anchor missing")
    remote = remote.replace(remote_helper_anchor, remote_helpers + remote_helper_anchor, 1)

remote_command_anchor = "def parse_command("
remote_wrapper = r'''_v120_health_execute_command_base = execute_command


def execute_command(command: dict, allow_maintenance: bool) -> dict:
    action = str(command.get("action") or "").strip().lower()
    if action == "hardware_status":
        return {"hardware": hardware_public(bridge_get("/hardware/status", timeout=22))}
    return _v120_health_execute_command_base(command, allow_maintenance)


'''
if "_v120_health_execute_command_base = execute_command" not in remote:
    if remote_command_anchor not in remote:
        raise SystemExit("v0.12 PC health Remote command anchor missing")
    remote = remote.replace(remote_command_anchor, remote_wrapper + remote_command_anchor, 1)

# Include the safe hardware profile in ordinary status snapshots too.
remote_snapshot_anchor = "def gh_api("
remote_snapshot = r'''_v120_health_collect_snapshot_base = collect_snapshot


def collect_snapshot(include_doctor: bool = False, deep: bool = False) -> dict:
    snap = _v120_health_collect_snapshot_base(include_doctor=include_doctor, deep=deep)
    snap["hardware_profile"] = hardware_public(bridge_get("/hardware/status", timeout=22))
    return snap


'''
if "_v120_health_collect_snapshot_base = collect_snapshot" not in remote:
    if remote_snapshot_anchor not in remote:
        raise SystemExit("v0.12 PC health Remote snapshot anchor missing")
    remote = remote.replace(remote_snapshot_anchor, remote_snapshot + remote_snapshot_anchor, 1)

# The main Agent installer already preserves the RemoteSupport runtime directory;
# only advance its declared component version so field diagnostics match the binary.
installer = re.sub(r'^REMOTE_VERSION = "[^"]+"', 'REMOTE_VERSION = "0.11.7.70"', installer, count=1, flags=re.M)

BRIDGE.write_text(bridge, encoding="utf-8")
REMOTE.write_text(remote, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
for path, text in [(BRIDGE, bridge), (REMOTE, remote), (INSTALLER, installer)]:
    compile(text, str(path), "exec")

# Make the existing final-artifact proof reapply this layer after correctness,
# freeze Remote Support .70, copy it into the main package, and prove the health
# endpoints from the rewritten ZIP.
if 'run(sys.executable, "Tools/apply_v120_pc_health_autonomy.py")' not in proof:
    proof = proof.replace(
        '    run(sys.executable, "apply_v120_correctness_upgrades.py")\n',
        '    run(sys.executable, "apply_v120_correctness_upgrades.py")\n    run(sys.executable, "Tools/apply_v120_pc_health_autonomy.py")\n',
        1,
    )
if 'remote_source = ROOT / "Tools" / "VexRemoteSupport.py"' not in proof:
    proof = proof.replace(
        '    bridge_source = ROOT / "Bridge" / "vex_bridge.py"\n',
        '    bridge_source = ROOT / "Bridge" / "vex_bridge.py"\n    remote_source = ROOT / "Tools" / "VexRemoteSupport.py"\n',
        1,
    )
    proof = proof.replace(
        '    py_compile.compile(str(bridge_source), doraise=True)\n',
        '    py_compile.compile(str(bridge_source), doraise=True)\n    py_compile.compile(str(remote_source), doraise=True)\n',
        1,
    )
    proof = proof.replace(
        '    bridge_text = bridge_source.read_text(encoding="utf-8")\n',
        '    bridge_text = bridge_source.read_text(encoding="utf-8")\n    remote_text = remote_source.read_text(encoding="utf-8")\n',
        1,
    )
if 'V120_PC_HEALTH_AUTONOMY' not in proof:
    proof = proof.replace(
        '        "V120_FACT_PRESERVING_RECALL",\n',
        '        "V120_FACT_PRESERVING_RECALL",\n        "V120_PC_HEALTH_AUTONOMY",\n        "V120_IDLE_ROTATION",\n        "def _v120_health_housekeeping_audit() -> dict:",\n        \'parsed.path == "/hardware/status"\',\n        \'parsed.path == "/maintenance/status"\',\n        \'parsed.path == "/maintenance/run"\',\n',
        1,
    )
    proof = proof.replace(
        '    pyinstaller = shutil.which("pyinstaller")\n',
        '    for marker in [\'VERSION = "0.11.7.70"\', "def hardware_public(", \'action == "hardware_status"\']:\n        if marker not in remote_text:\n            raise RuntimeError(f"post-build Remote source marker missing: {marker}")\n\n    pyinstaller = shutil.which("pyinstaller")\n',
        1,
    )
if 'DIST / "VexRemoteSupport"' not in proof:
    proof = proof.replace(
        '    shutil.rmtree(DIST / "VexWindowsHost", ignore_errors=True)\n',
        '    shutil.rmtree(DIST / "VexWindowsHost", ignore_errors=True)\n    shutil.rmtree(DIST / "VexRemoteSupport", ignore_errors=True)\n',
        1,
    )
    proof = proof.replace(
        '    shutil.rmtree(ROOT / "build" / "VexWindowsHost", ignore_errors=True)\n',
        '    shutil.rmtree(ROOT / "build" / "VexWindowsHost", ignore_errors=True)\n    shutil.rmtree(ROOT / "build" / "VexRemoteSupport", ignore_errors=True)\n',
        1,
    )
    host_build = '''    run(\n        pyinstaller, "--noconfirm", "--clean", "--onedir", "--noupx", "--windowed",\n        "--name", "VexWindowsHost", "--collect-all", "requests", "Tools/VexWindowsHost-v11740.py",\n    )\n'''
    remote_build = host_build + '''    run(\n        pyinstaller, "--noconfirm", "--clean", "--onedir", "--noupx", "--windowed",\n        "--name", "VexRemoteSupport", "--collect-all", "requests", "Tools/VexRemoteSupport.py",\n    )\n'''
    if host_build not in proof:
        raise SystemExit("v0.12 PC health proof Host build anchor missing")
    proof = proof.replace(host_build, remote_build, 1)
    proof = proof.replace(
        '    replace_tree(DIST / "VexWindowsHost", PKG / "VexWindowsHost")\n',
        '    replace_tree(DIST / "VexWindowsHost", PKG / "VexWindowsHost")\n    replace_tree(DIST / "VexRemoteSupport", PKG / "VexRemoteSupportRuntime")\n',
        1,
    )
if '/hardware/status?' not in proof:
    proof = proof.replace(
        '                log("PASS final ZIP Bridge v0.12 + authenticated local requests + Wants reconciliation")\n',
        '                hardware = no_proxy_json(f"http://127.0.0.1:{port}/hardware/status?{query}", timeout=22)\n                if hardware.get("ok") is not True:\n                    raise RuntimeError(f"hardware status failed: {hardware}")\n                maintenance = no_proxy_json(f"http://127.0.0.1:{port}/maintenance/status?{query}", timeout=8)\n                if maintenance.get("ok") is not True:\n                    raise RuntimeError(f"maintenance status failed: {maintenance}")\n                audit = no_proxy_json(f"http://127.0.0.1:{port}/housekeeping/audit?{query}", timeout=12)\n                if audit.get("ok") is not True:\n                    raise RuntimeError(f"housekeeping audit failed: {audit}")\n                log("PASS final ZIP Bridge v0.12 + Wants reconciliation + PC health endpoints")\n',
        1,
    )
if 'VexRemoteSupportRuntime" / "VexRemoteSupport.exe"' not in proof:
    proof = proof.replace(
        '    prove_host_from_zip()\n',
        '    remote_exe = VERIFY / "VexRemoteSupportRuntime" / "VexRemoteSupport.exe"\n    if not remote_exe.exists():\n        raise RuntimeError(f"rewritten ZIP Remote Support missing: {remote_exe}")\n    prove_host_from_zip()\n',
        1,
    )
PROOF.write_text(proof, encoding="utf-8")
compile(proof, str(PROOF), "exec")

# Final invariants. These intentionally fail the build instead of shipping a
# cleanup layer that could classify arbitrary Downloads installers as disposable.
for marker in [
    'V120_PC_HEALTH_AUTONOMY = "v0.12-pc-health-autonomy-v1"',
    'V120_IDLE_ROTATION = "v0.12-idle-productive-rotation-v1"',
    'def _v120_health_housekeeping_audit() -> dict:',
    'parsed.path == "/hardware/status"',
    'parsed.path == "/maintenance/status"',
    'parsed.path == "/maintenance/run"',
    'all arbitrary installers and generic archives',
    'optimization_policy',
    '_v120_health_choose_action_base',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.12 PC health Bridge invariant missing: {marker}")
for forbidden in [
    'suffix in safe_installer_exts and stat.st_mtime <= installer_cutoff',
]:
    # The historical implementation can remain earlier in the generated file, but
    # the live aliases must point at v0.12 conservative code. This check is limited
    # to our layer text, not the whole cumulative source.
    if forbidden in V120_LAYER:
        raise SystemExit(f"v0.12 PC health unsafe policy regression: {forbidden}")
for marker in [
    'VERSION = "0.11.7.70"',
    'def hardware_public(',
    'action == "hardware_status"',
    '_v120_health_collect_snapshot_base = collect_snapshot',
]:
    if marker not in remote:
        raise SystemExit(f"v0.12 PC health Remote invariant missing: {marker}")
if 'REMOTE_VERSION = "0.11.7.70"' not in installer:
    raise SystemExit("v0.12 PC health installer Remote version invariant missing")
for marker in [
    'Tools/apply_v120_pc_health_autonomy.py',
    'DIST / "VexRemoteSupport"',
    'PKG / "VexRemoteSupportRuntime"',
    '/hardware/status?',
]:
    if marker not in proof:
        raise SystemExit(f"v0.12 PC health proof invariant missing: {marker}")

print("Applied v0.12 PC health, conservative housekeeping, hardware profile, Remote .70, and productive idle rotation")
