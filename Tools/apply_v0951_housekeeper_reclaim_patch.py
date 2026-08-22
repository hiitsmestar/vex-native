#!/usr/bin/env python3
from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")


def replace_function(name: str, new_source: str) -> None:
    global text
    start = text.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"{name}: function not found")
    next_def = text.find("\ndef ", start + 4)
    if next_def < 0:
        raise SystemExit(f"{name}: next function marker not found")
    text = text[:start] + new_source.rstrip() + "\n\n" + text[next_def + 1:]


# ---------------------------------------------------------------------------
# v0.9.5.1 housekeeping policy
# - safe junk is actually deleted and disk space is reclaimed
# - no new quarantine is created during normal cleanup
# - photos/video/music/documents/projects/models/programs/system data stay protected
# - old v0.9.5 quarantine is purged during a normal clean so it cannot become a bin
# - maintenance repeats in the background and refreshes the live file index
# ---------------------------------------------------------------------------
marker = "HOUSEKEEPER_INSTALLER_EXTS = {\".exe\", \".msi\", \".msix\", \".msixbundle\", \".zip\", \".7z\", \".rar\", \".iso\"}\n"
if marker not in text:
    raise SystemExit("housekeeper constants marker missing")
text = text.replace(
    marker,
    marker + "HOUSEKEEPER_AUTO_START_DELAY = 300\nHOUSEKEEPER_AUTO_INTERVAL = 6 * 3600\n",
    1,
)

replace_function("_hk_audit", r'''def _hk_audit() -> dict:
    temp = _hk_temp_candidates()
    downloads = _hk_download_candidates()
    temp_bytes = sum(int(x.get("bytes") or 0) for x in temp)
    download_bytes = sum(int(x.get("bytes") or 0) for x in downloads)
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
        "safe_temp_bytes": temp_bytes,
        "review_installer_files": len(downloads),
        "review_installer_bytes": download_bytes,
        "safe_reclaimable_files": len(temp) + len(downloads),
        "safe_reclaimable_bytes": temp_bytes + download_bytes,
        "disk": disk,
        "policy": "delete-safe-junk",
        "protected": [
            "photos", "videos", "music/audio", "documents", "creative projects/source code",
            "installed programs", "Windows/system files", "Vex/Ollama/ComfyUI models and data"
        ],
        "samples": {
            "temp": [x["path"] for x in temp[:8]],
            "installers": [x["path"] for x in downloads[:8]],
        },
    }''')

replace_function("_hk_clean_safe", r'''def _hk_clean_safe() -> dict:
    temp = _hk_temp_candidates()
    downloads = _hk_download_candidates()
    deleted_bytes = 0
    deleted_temp = 0
    deleted_installers = 0
    skipped = 0

    # Stale temp files are disposable working debris. Delete them for real.
    for item in temp:
        path = Path(item["path"])
        try:
            size = int(item.get("bytes") or 0)
            path.unlink(missing_ok=True)
            if not path.exists():
                deleted_temp += 1
                deleted_bytes += size
        except Exception:
            skipped += 1

    # Old installer/archive files in Downloads are package debris, not installed
    # applications. Media, documents and project/source extensions were excluded
    # by _hk_download_candidates before we get here.
    for item in downloads:
        path = Path(item["path"])
        try:
            size = int(item.get("bytes") or 0)
            path.unlink(missing_ok=True)
            if not path.exists():
                deleted_installers += 1
                deleted_bytes += size
        except Exception:
            skipped += 1

    # v0.9.5 used quarantine as a safety net. Star explicitly wants reclaimed
    # storage instead of junk being moved elsewhere, so purge any legacy bin.
    legacy = _hk_purge_quarantine()
    legacy_bytes = int(legacy.get("purged_bytes") or 0) if isinstance(legacy, dict) else 0
    legacy_files = int(legacy.get("purged_files") or 0) if isinstance(legacy, dict) else 0
    deleted_bytes += legacy_bytes

    # Remove now-empty directories under Downloads only. Never recurse into or
    # delete non-empty user folders.
    downloads_root = Path.home() / "Downloads"
    if downloads_root.exists():
        try:
            directories = sorted(
                [p for p in downloads_root.rglob("*") if p.is_dir() and not p.is_symlink()],
                key=lambda p: len(p.parts),
                reverse=True,
            )
            for directory in directories:
                try:
                    directory.rmdir()
                except OSError:
                    pass
        except Exception:
            pass

    stamp = time.strftime("%Y%m%d-%H%M%S")
    HOUSEKEEPER_MANIFESTS.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": time.time(),
        "run": stamp,
        "policy": "delete-safe-junk",
        "deleted_temp_files": deleted_temp,
        "deleted_installer_archive_files": deleted_installers,
        "purged_legacy_quarantine_files": legacy_files,
        "reclaimed_bytes": deleted_bytes,
        "protected_categories": [
            "photos", "videos", "music/audio", "documents", "creative projects/source code",
            "installed programs", "Windows/system files", "Vex/Ollama/ComfyUI models and data"
        ],
    }
    manifest_path = HOUSEKEEPER_MANIFESTS / f"{stamp}.json"
    try:
        manifest_path.write_text(json.dumps(manifest, indent=2), "utf-8")
    except Exception:
        pass

    total_deleted = deleted_temp + deleted_installers + legacy_files

    # Refresh the live index after a real cleanup. Do it in the background and
    # never start a second rebuild while the full-drive indexer is already busy.
    try:
        if total_deleted > 0 and STATE is not None and not getattr(STATE.index, "_vex_indexing", False):
            threading.Thread(target=STATE.index.rebuild, daemon=True, name="VexHousekeeperReindex").start()
    except Exception:
        pass

    return {
        "ok": True,
        "node_name": socket.gethostname(),
        "deleted_temp_files": deleted_temp,
        "deleted_installer_files": deleted_installers,
        "deleted_clutter_files": total_deleted,
        "reclaimed_bytes": deleted_bytes,
        "quarantined_files": 0,
        "quarantined_bytes": 0,
        "purged_legacy_quarantine_files": legacy_files,
        "purged_legacy_quarantine_bytes": legacy_bytes,
        "skipped": skipped,
        "manifest": str(manifest_path),
        "note": "Safe junk was permanently deleted. Protected personal/system/program/model categories were not touched."
    }''')

# Background maintenance is intentionally narrow: it runs exactly the same safe
# delete policy as a manual clean and cannot uninstall apps or delete user media.
maintenance_helpers = r'''

def _hk_maintenance_loop() -> None:
    time.sleep(HOUSEKEEPER_AUTO_START_DELAY)
    while True:
        try:
            result = _hk_clean_safe()
            print(
                f"[housekeeper] automatic maintenance reclaimed {int(result.get('reclaimed_bytes') or 0):,} bytes "
                f"across {int(result.get('deleted_clutter_files') or 0):,} safe-junk files",
                flush=True,
            )
        except Exception as exc:
            print(f"[housekeeper] automatic maintenance skipped: {exc}", flush=True)
        time.sleep(HOUSEKEEPER_AUTO_INTERVAL)
'''
insert_before = "\ndef _vex_background_services("
pos = text.find(insert_before)
if pos < 0:
    raise SystemExit("background services function missing")
text = text[:pos] + maintenance_helpers + text[pos:]

# Start one housekeeping loop alongside the existing ComfyUI/resource warmup.
start = text.find("def _vex_background_services(")
line_end = text.find("\n", start)
if start < 0 or line_end < 0:
    raise SystemExit("background services signature missing")
startup = r'''
    if not getattr(_vex_background_services, "_housekeeper_started", False):
        _vex_background_services._housekeeper_started = True
        threading.Thread(target=_hk_maintenance_loop, daemon=True, name="VexHousekeeperMaintenance").start()
'''
text = text[:line_end + 1] + startup + text[line_end + 1:]

bridge_path.write_text(text, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.5"' not in full:
    raise SystemExit("vex_bridge_full.py: expected v0.9.5 version marker missing")
full = full.replace('VERSION = "0.9.5"', 'VERSION = "0.9.5.1"', 1)
full_path.write_text(full, encoding="utf-8")

checks = [
    'HOUSEKEEPER_AUTO_INTERVAL = 6 * 3600',
    '"policy": "delete-safe-junk"',
    '"deleted_installer_files"',
    'VexHousekeeperMaintenance',
    'quarantined_files": 0',
]
for marker in checks:
    if marker not in text:
        raise SystemExit(f"missing v0.9.5.1 housekeeper marker: {marker}")
if 'VERSION = "0.9.5.1"' not in full:
    raise SystemExit("v0.9.5.1 Bridge version marker missing")

print("Applied v0.9.5.1 reclaiming housekeeper: permanent safe-junk deletion + automatic maintenance")
