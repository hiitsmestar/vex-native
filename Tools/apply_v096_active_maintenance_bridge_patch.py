#!/usr/bin/env python3
from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")


def replace_between(start_marker: str, end_marker: str, replacement: str, label: str) -> None:
    global text
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0:
        raise SystemExit(f"{label}: markers missing")
    text = text[:start] + replacement.rstrip() + "\n\n" + text[end:]


# ---------------------------------------------------------------------------
# v0.9.6 housekeeping policy
# - safe junk is actually deleted so disk space is reclaimed
# - review/sensitive items stay where they are; they are never hidden in a bin
# - photos/video/music/documents/program uninstall/system files require approval
# - generic archives are review-only because they can contain personal projects
# ---------------------------------------------------------------------------
new_housekeeping = r'''def _hk_scan_files(root: Path, cutoff: float, kind: str, limit: int = 12000, filename_prefixes: tuple[str, ...] = ()) -> list[dict]:
    if not root.exists():
        return []
    found = []
    try:
        for path in root.rglob("*"):
            if len(found) >= limit:
                break
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                if filename_prefixes and not path.name.lower().startswith(filename_prefixes):
                    continue
                stat = path.stat()
                if stat.st_mtime > cutoff:
                    continue
                found.append({
                    "path": str(path), "bytes": int(stat.st_size), "mtime": float(stat.st_mtime), "kind": kind
                })
            except Exception:
                continue
    except Exception:
        pass
    return found


def _hk_safe_cache_candidates() -> list[dict]:
    now = time.time()
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    system_root = Path(os.environ.get("SystemRoot", "C:\\Windows"))
    program_data = Path(os.environ.get("ProgramData", "C:\\ProgramData"))
    specs = [
        (local / "D3DSCache", now - 7 * 86400, "shader-cache", 4000),
        (local / "CrashDumps", now - 14 * 86400, "crash-dump", 3000),
        (local / "Microsoft" / "Windows" / "INetCache", now - 14 * 86400, "inet-cache", 5000),
        (system_root / "Temp", now - 7 * 86400, "windows-temp", 5000),
        (program_data / "Microsoft" / "Windows" / "WER" / "ReportArchive", now - 14 * 86400, "error-report", 3000),
        (program_data / "Microsoft" / "Windows" / "WER" / "ReportQueue", now - 14 * 86400, "error-report", 3000),
    ]
    found: list[dict] = []
    seen = set()
    for root, cutoff, kind, limit in specs:
        for item in _hk_scan_files(root, cutoff, kind, limit):
            key = os.path.normcase(item["path"])
            if key in seen:
                continue
            seen.add(key)
            found.append(item)
    return found


def _hk_download_candidates() -> tuple[list[dict], list[dict]]:
    root = Path.home() / "Downloads"
    if not root.exists():
        return [], []
    now = time.time()
    installer_cutoff = now - 30 * 86400
    vex_cutoff = now - 14 * 86400
    auto_delete: list[dict] = []
    review: list[dict] = []
    safe_installer_exts = {".exe", ".msi", ".msix", ".msixbundle"}
    archive_exts = {".zip", ".7z", ".rar", ".iso"}
    try:
        for path in root.rglob("*"):
            if len(auto_delete) + len(review) >= 8000:
                break
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                suffix = path.suffix.lower()
                if suffix in HOUSEKEEPER_MEDIA_EXTS or suffix in HOUSEKEEPER_DOC_EXTS:
                    continue
                stat = path.stat()
                name = path.name.lower()
                info = {"path": str(path), "bytes": int(stat.st_size), "mtime": float(stat.st_mtime), "kind": "download"}

                # Old executable installer packages in Downloads are replaceable artifacts,
                # not installed applications. Installed apps themselves are never touched.
                if suffix in safe_installer_exts and stat.st_mtime <= installer_cutoff:
                    info["kind"] = "old-installer"
                    auto_delete.append(info)
                    continue

                # Old Vex release bundles are generated artifacts and safe to prune once stale.
                if suffix in archive_exts and name.startswith("vex") and stat.st_mtime <= vex_cutoff:
                    if any(token in name for token in ["bridge", "native", "brain", "art", "resource", "housekeep"]):
                        info["kind"] = "old-vex-bundle"
                        auto_delete.append(info)
                        continue

                # Generic archives may contain personal projects even when the extension
                # itself looks disposable. Keep them in place and ask before deletion.
                if suffix in archive_exts and stat.st_mtime <= installer_cutoff:
                    info["kind"] = "archive-review"
                    review.append(info)
            except Exception:
                continue
    except Exception:
        pass
    return auto_delete, review


def _hk_audit() -> dict:
    temp = _hk_temp_candidates()
    caches = _hk_safe_cache_candidates()
    installers, review = _hk_download_candidates()
    safe_items = temp + caches + installers
    safe_bytes = sum(int(x.get("bytes") or 0) for x in safe_items)
    review_bytes = sum(int(x.get("bytes") or 0) for x in review)
    try:
        import shutil
        usage = shutil.disk_usage(Path.home().anchor or "C:\\")
        disk = {"total": int(usage.total), "used": int(usage.used), "free": int(usage.free)}
    except Exception:
        disk = {}
    return {
        "ok": True,
        "node_name": socket.gethostname(),
        "safe_temp_files": len(temp),
        "safe_temp_bytes": sum(int(x.get("bytes") or 0) for x in temp),
        "safe_cache_files": len(caches),
        "safe_cache_bytes": sum(int(x.get("bytes") or 0) for x in caches),
        "auto_installer_files": len(installers),
        "auto_installer_bytes": sum(int(x.get("bytes") or 0) for x in installers),
        "approval_required_files": len(review),
        "approval_required_bytes": review_bytes,
        "safe_reclaimable_bytes": safe_bytes,
        "disk": disk,
        "protected": [
            "photos", "videos", "music", "documents", "desktop personal files",
            "installed programs", "Windows/system files", "Vex/Ollama/ComfyUI models"
        ],
        "policy": "Safe junk is permanently deleted. Sensitive/review items stay in place until explicitly approved.",
        "samples": {
            "safe_temp": [x["path"] for x in temp[:6]],
            "safe_cache": [x["path"] for x in caches[:6]],
            "auto_installers": [x["path"] for x in installers[:6]],
            "approval_required": [x["path"] for x in review[:8]],
        },
    }


def _hk_delete_items(items: list[dict]) -> tuple[int, int, int]:
    deleted_files = 0
    deleted_bytes = 0
    skipped = 0
    for item in items:
        path = Path(str(item.get("path") or ""))
        try:
            if not path.exists() or not path.is_file() or path.is_symlink():
                continue
            size = int(item.get("bytes") or path.stat().st_size)
            path.unlink()
            if not path.exists():
                deleted_files += 1
                deleted_bytes += size
        except Exception:
            skipped += 1
    return deleted_files, deleted_bytes, skipped


def _hk_prune_empty_dirs() -> int:
    roots = []
    for raw in [os.environ.get("TEMP"), os.environ.get("TMP"), str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Temp")]:
        if raw:
            p = Path(raw)
            if p.exists() and p not in roots:
                roots.append(p)
    removed = 0
    for root in roots:
        try:
            dirs = [p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()]
            for path in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
                try:
                    path.rmdir()
                    removed += 1
                except Exception:
                    pass
        except Exception:
            pass
    return removed


def _hk_start_index_refresh() -> bool:
    if STATE is None or getattr(STATE, "index", None) is None:
        return False
    try:
        if getattr(STATE.index, "_vex_indexing", False):
            return True
        threading.Thread(target=STATE.index.rebuild, daemon=True, name="VexMaintenanceIndexRefresh").start()
        return True
    except Exception:
        return False


def _hk_fixed_drive_roots() -> list[str]:
    if not sys.platform.startswith("win"):
        return []
    roots = []
    try:
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        DRIVE_FIXED = 3
        for i in range(26):
            if not (mask & (1 << i)):
                continue
            root = f"{chr(ord('A') + i)}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) == DRIVE_FIXED:
                roots.append(root)
    except Exception:
        pass
    return roots


def _hk_optimize_drives() -> dict:
    import subprocess
    results = []
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for root in _hk_fixed_drive_roots():
        try:
            # /O lets Windows choose the correct operation for SSD vs HDD.
            completed = subprocess.run(
                ["defrag.exe", root, "/O", "/H"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=1800,
                creationflags=flags,
            )
            results.append({
                "drive": root,
                "ok": completed.returncode == 0,
                "returncode": int(completed.returncode),
                "message": str(completed.stdout or "")[-1200:],
            })
        except Exception as exc:
            results.append({"drive": root, "ok": False, "error": str(exc)[:500]})
    return {"attempted": len(results), "successful": sum(1 for r in results if r.get("ok")), "results": results}


def _hk_state_path() -> Path:
    return HOUSEKEEPER_ROOT / "maintenance-state.json"


def _hk_load_state() -> dict:
    try:
        return json.loads(_hk_state_path().read_text("utf-8"))
    except Exception:
        return {}


def _hk_save_state(state: dict) -> None:
    try:
        HOUSEKEEPER_ROOT.mkdir(parents=True, exist_ok=True)
        _hk_state_path().write_text(json.dumps(state, indent=2), "utf-8")
    except Exception:
        pass


def _hk_clean_safe() -> dict:
    temp = _hk_temp_candidates()
    caches = _hk_safe_cache_candidates()
    installers, review = _hk_download_candidates()
    candidates = temp + caches + installers
    deleted_files, deleted_bytes, skipped = _hk_delete_items(candidates)
    empty_dirs = _hk_prune_empty_dirs()
    index_started = _hk_start_index_refresh()
    state = _hk_load_state()
    state.update({
        "last_safe_clean": time.time(),
        "last_reclaimed_bytes": int(deleted_bytes),
        "last_deleted_files": int(deleted_files),
        "last_index_refresh": time.time() if index_started else state.get("last_index_refresh"),
    })
    _hk_save_state(state)
    return {
        "ok": True,
        "node_name": socket.gethostname(),
        "deleted_safe_files": deleted_files,
        "deleted_temp_files": deleted_files,
        "deleted_installer_files": sum(1 for x in installers if not Path(x["path"]).exists()),
        "reclaimed_bytes": deleted_bytes,
        "removed_empty_dirs": empty_dirs,
        "approval_required_files": len(review),
        "approval_required_bytes": sum(int(x.get("bytes") or 0) for x in review),
        "quarantined_files": 0,
        "quarantined_bytes": 0,
        "skipped": skipped,
        "index_refresh_started": index_started,
        "note": "Safe junk was permanently deleted. Sensitive/review files stayed in place; nothing new was quarantined.",
    }


def _hk_maintenance_status() -> dict:
    state = _hk_load_state()
    audit = _hk_audit()
    return {
        "ok": True,
        "node_name": socket.gethostname(),
        "state": state,
        "safe_reclaimable_bytes": audit.get("safe_reclaimable_bytes", 0),
        "approval_required_files": audit.get("approval_required_files", 0),
        "approval_required_bytes": audit.get("approval_required_bytes", 0),
        "auto_maintenance": True,
        "safe_cleanup_interval_hours": 24,
        "drive_optimize_interval_days": 7,
    }


def _hk_run_maintenance(force_optimize: bool = False) -> dict:
    clean = _hk_clean_safe()
    state = _hk_load_state()
    now = time.time()
    last_optimize = float(state.get("last_optimize") or 0)
    optimize_due = force_optimize or (now - last_optimize >= 7 * 86400)
    optimize = {"attempted": 0, "successful": 0, "results": []}
    if optimize_due:
        optimize = _hk_optimize_drives()
        state["last_optimize"] = now
        state["last_optimize_result"] = {"attempted": optimize["attempted"], "successful": optimize["successful"]}
    state["last_maintenance"] = now
    _hk_save_state(state)
    clean.update({
        "maintenance": True,
        "optimized_drives": int(optimize.get("successful") or 0),
        "optimization_attempted": int(optimize.get("attempted") or 0),
        "optimize_details": optimize.get("results") or [],
    })
    return clean


def _hk_maintenance_loop() -> None:
    # Give Windows and the Bridge time to settle after boot, then maintain quietly.
    time.sleep(300)
    while True:
        try:
            state = _hk_load_state()
            now = time.time()
            last_clean = float(state.get("last_safe_clean") or 0)
            audit = _hk_audit()
            reclaimable = int(audit.get("safe_reclaimable_bytes") or 0)
            free = int((audit.get("disk") or {}).get("free") or 0)
            total = int((audit.get("disk") or {}).get("total") or 0)
            low_space = total > 0 and (free / total) < 0.15
            clean_due = now - last_clean >= 24 * 3600
            if (clean_due and reclaimable >= 64 * 1024 * 1024) or (low_space and reclaimable >= 8 * 1024 * 1024):
                result = _hk_run_maintenance(force_optimize=False)
                print(
                    f"[housekeeper] reclaimed {int(result.get('reclaimed_bytes') or 0):,} bytes; "
                    f"deleted {int(result.get('deleted_safe_files') or 0):,} safe files",
                    flush=True,
                )
            else:
                # Even when there is little junk, keep the Vex file index fresh daily.
                last_index = float(state.get("last_index_refresh") or 0)
                if now - last_index >= 24 * 3600 and _hk_start_index_refresh():
                    state["last_index_refresh"] = now
                    _hk_save_state(state)
        except Exception as exc:
            print(f"[housekeeper] maintenance pass failed: {exc}", flush=True)
        time.sleep(6 * 3600)
'''

replace_between(
    "def _hk_download_candidates()",
    "def _hk_restore_latest()",
    new_housekeeping,
    "housekeeping engine",
)

# Keep restore/purge only for any quarantine left behind by v0.9.5. v0.9.6 no
# longer creates new quarantine clutter.

# Extend background services to include the periodic maintenance daemon.
old_bg = '    threading.Thread(target=warm_art, daemon=True, name="VexArtWarmup").start()\n'
if old_bg not in text:
    raise SystemExit("background service marker missing")
text = text.replace(
    old_bg,
    old_bg + '    threading.Thread(target=_hk_maintenance_loop, daemon=True, name="VexHousekeeperMaintenance").start()\n',
    1,
)

# Add maintenance status route before the existing housekeeping audit route.
get_marker = '        if parsed.path == "/housekeeping/audit":\n'
if get_marker not in text:
    raise SystemExit("housekeeping GET marker missing")
text = text.replace(
    get_marker,
    '        if parsed.path == "/maintenance/status":\n            self._json(200, _hk_maintenance_status())\n            return\n\n' + get_marker,
    1,
)

# Add explicit maintenance/optimization endpoint. The normal /housekeeping/clean
# remains permanent safe cleanup + reindex and never touches protected files.
post_marker = '        if parsed.path in ("/housekeeping/clean", "/housekeeping/restore", "/housekeeping/purge"):\n'
if post_marker not in text:
    raise SystemExit("housekeeping POST marker missing")
maintenance_post = r'''        if parsed.path == "/maintenance/run":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                payload = {}
                if length > 0:
                    if length > 32_000:
                        self._json(413, {"ok": False, "error": "maintenance payload too large"})
                        return
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if str(payload.get("confirm") or "").lower() not in {"true", "1", "yes"} and payload.get("confirm") is not True:
                    self._json(400, {"ok": False, "error": "maintenance requires confirm=true"})
                    return
                force_optimize = payload.get("optimize") is True or str(payload.get("optimize") or "").lower() in {"true", "1", "yes"}
                self._json(200, _hk_run_maintenance(force_optimize=force_optimize))
            except Exception as exc:
                self._json(500, {"ok": False, "error": f"maintenance failed: {exc}"})
            return

'''
text = text.replace(post_marker, maintenance_post + post_marker, 1)

# Advertise v0.9.6 semantics in /status.
old_status = '                "housekeeping": {"audit": True, "safe_clean": True, "restore": True, "purge": True},\n'
if old_status not in text:
    raise SystemExit("housekeeping status marker missing")
text = text.replace(
    old_status,
    '                "housekeeping": {"audit": True, "permanent_safe_clean": True, "auto_maintenance": True, "reindex": True, "drive_optimize": True, "approval_gate": True, "legacy_restore": True, "legacy_purge": True},\n',
    1,
)

bridge_path.write_text(text, encoding="utf-8")

# Version bump for the full Windows launcher.
full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.5"' not in full:
    raise SystemExit("full bridge v0.9.5 marker missing")
full = full.replace('VERSION = "0.9.5"', 'VERSION = "0.9.6"', 1)
full_path.write_text(full, encoding="utf-8")

checks = [
    "def _hk_safe_cache_candidates", "def _hk_run_maintenance", "def _hk_maintenance_loop",
    'parsed.path == "/maintenance/status"', 'parsed.path == "/maintenance/run"',
    '"permanent_safe_clean": True', "VexHousekeeperMaintenance", "defrag.exe",
    "Sensitive/review files stayed in place; nothing new was quarantined.",
]
final = bridge_path.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"missing v0.9.6 bridge marker: {marker}")
if 'VERSION = "0.9.6"' not in full_path.read_text(encoding="utf-8"):
    raise SystemExit("missing v0.9.6 bridge version")

print("Applied v0.9.6 active maintenance + permanent safe cleanup + reindex + drive optimize policy")
