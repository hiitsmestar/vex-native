#!/usr/bin/env python3
from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    text = text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# CPU-friendly Qwen brain settings carried forward from the field hotfix.
# ---------------------------------------------------------------------------
replace_once(
    '''OLLAMA_PREFERRED_MODELS = [\n    "qwen3:8b",\n    "qwen3:4b",\n    "gemma3:4b",\n    "llama3.2:3b",\n]\n''',
    '''OLLAMA_PREFERRED_MODELS = [\n    "vex-qwen3-4b:latest",\n    "vex-qwen3-4b",\n    "qwen3:4b",\n    "gemma3:4b",\n    "llama3.2:3b",\n    "qwen3:8b",\n]\n''',
    "preferred cognition model",
)

replace_once(
    '''                "stream": False,\n                "options": {\n                    "temperature": 0.78,\n                    "top_p": 0.92,\n                    "num_ctx": 8192,\n                    "repeat_penalty": 1.08,\n                },\n            },\n            timeout=42,\n''',
    '''                "stream": False,\n                "think": False,\n                "keep_alive": "30m",\n                "options": {\n                    "temperature": 0.72,\n                    "top_p": 0.90,\n                    "num_ctx": 4096,\n                    "num_predict": 220,\n                    "repeat_penalty": 1.08,\n                },\n            },\n            timeout=85,\n''',
    "CPU cognition options",
)

# ---------------------------------------------------------------------------
# Art-engine startup: keep ComfyUI warm, log startup, and allow slow PCs time.
# ---------------------------------------------------------------------------
start = text.find("def _ensure_art_comfy() -> tuple[bool, str | None]:\n")
end = text.find("\n\ndef _art_is_stylized", start)
if start < 0 or end < 0:
    raise SystemExit("art startup function markers missing")
new_ensure = r'''def _ensure_art_comfy() -> tuple[bool, str | None]:
    global _ART_COMFY_PROCESS
    if _art_comfy_health():
        return True, None
    if not ART_PYTHON.exists() or not (ART_COMFY_DIR / "main.py").exists():
        return False, "Vex Art Engine is not installed on this PC. Run VexArtSetup.ps1 first."

    # If an older child process died, do not keep pretending it is starting.
    try:
        if _ART_COMFY_PROCESS is not None and _ART_COMFY_PROCESS.poll() is not None:
            _ART_COMFY_PROCESS = None
    except Exception:
        _ART_COMFY_PROCESS = None

    try:
        import subprocess
        ART_ROOT.mkdir(parents=True, exist_ok=True)
        log_path = ART_ROOT / "comfyui-bridge.log"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with log_path.open("ab", buffering=0) as log:
            _ART_COMFY_PROCESS = subprocess.Popen(
                [str(ART_PYTHON), "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"],
                cwd=str(ART_COMFY_DIR),
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )

        # Older/CPU-only machines can take well over 40 seconds on the first boot.
        for _ in range(360):
            time.sleep(0.5)
            if _art_comfy_health(timeout=1.2):
                return True, None
            try:
                if _ART_COMFY_PROCESS is not None and _ART_COMFY_PROCESS.poll() is not None:
                    return False, f"ComfyUI exited during startup. See {log_path}"
            except Exception:
                pass
        return False, f"ComfyUI did not become ready within 180 seconds. See {log_path}"
    except Exception as exc:
        return False, f"Could not start ComfyUI: {exc}"
'''
text = text[:start] + new_ensure + text[end:]

# ---------------------------------------------------------------------------
# Resource snapshot + safe housekeeper.
# The utility role changes scheduling only; it never removes Bridge permissions.
# ---------------------------------------------------------------------------
helper_marker = "\n\n_BROWSER_CONTROL_LOCK = threading.Lock()"
if helper_marker not in text:
    raise SystemExit("browser helper marker missing")
helpers = r'''

HOUSEKEEPER_ROOT = Path.home() / "Documents" / "VexHousekeeper"
HOUSEKEEPER_QUARANTINE = HOUSEKEEPER_ROOT / "Quarantine"
HOUSEKEEPER_MANIFESTS = HOUSEKEEPER_ROOT / "Manifests"
HOUSEKEEPER_MEDIA_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".tif", ".tiff", ".bmp",
    ".mp4", ".mov", ".mkv", ".avi", ".wmv", ".m4v", ".webm",
    ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".aiff", ".mid", ".midi",
}
HOUSEKEEPER_DOC_EXTS = {
    ".txt", ".rtf", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".csv", ".md", ".json", ".xml", ".html", ".htm", ".py", ".swift", ".js", ".ts",
}
HOUSEKEEPER_INSTALLER_EXTS = {".exe", ".msi", ".msix", ".msixbundle", ".zip", ".7z", ".rar", ".iso"}


def _resource_snapshot() -> dict:
    cpu_count = int(os.cpu_count() or 1)
    total_memory = None
    available_memory = None
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            total_memory = int(status.ullTotalPhys)
            available_memory = int(status.ullAvailPhys)
    except Exception:
        pass

    drives = []
    try:
        import shutil
        roots = [Path.home().anchor or "C:\\"]
        seen = set()
        for root in roots:
            key = str(root).lower()
            if key in seen:
                continue
            seen.add(key)
            usage = shutil.disk_usage(root)
            drives.append({"root": str(root), "total": int(usage.total), "free": int(usage.free)})
    except Exception:
        pass

    return {
        "hostname": socket.gethostname(),
        "cpu_logical": cpu_count,
        "memory_total": total_memory,
        "memory_available": available_memory,
        "drives": drives,
        "art_installed": ART_PYTHON.exists() and (ART_COMFY_DIR / "main.py").exists(),
        "art_running": _art_comfy_health(timeout=0.8),
        "cognition_model": _choose_ollama_model(),
        "access_mode": (STATE.config.get("access_mode") if STATE is not None else None) or "full",
    }


def _hk_file_info(path: Path) -> dict | None:
    try:
        stat = path.stat()
        return {"path": str(path), "bytes": int(stat.st_size), "mtime": float(stat.st_mtime)}
    except Exception:
        return None


def _hk_temp_candidates() -> list[dict]:
    roots = []
    for raw in [os.environ.get("TEMP"), os.environ.get("TMP"), str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Temp")]:
        if not raw:
            continue
        p = Path(raw)
        if p.exists() and p not in roots:
            roots.append(p)
    cutoff = time.time() - 7 * 86400
    found = []
    for root in roots:
        try:
            for path in root.rglob("*"):
                if len(found) >= 12000:
                    break
                try:
                    if not path.is_file() or path.is_symlink():
                        continue
                    stat = path.stat()
                    if stat.st_mtime > cutoff:
                        continue
                    found.append({"path": str(path), "bytes": int(stat.st_size), "mtime": float(stat.st_mtime), "kind": "temp"})
                except Exception:
                    continue
        except Exception:
            continue
    return found


def _hk_download_candidates() -> list[dict]:
    root = Path.home() / "Downloads"
    if not root.exists():
        return []
    cutoff = time.time() - 30 * 86400
    found = []
    try:
        for path in root.rglob("*"):
            if len(found) >= 6000:
                break
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                suffix = path.suffix.lower()
                if suffix in HOUSEKEEPER_MEDIA_EXTS or suffix in HOUSEKEEPER_DOC_EXTS:
                    continue
                stat = path.stat()
                name = path.name.lower()
                old_installer = suffix in HOUSEKEEPER_INSTALLER_EXTS and stat.st_mtime <= cutoff
                old_vex = name.startswith("vex") and suffix in HOUSEKEEPER_INSTALLER_EXTS and stat.st_mtime <= time.time() - 7 * 86400
                if not (old_installer or old_vex):
                    continue
                found.append({"path": str(path), "bytes": int(stat.st_size), "mtime": float(stat.st_mtime), "kind": "installer"})
            except Exception:
                continue
    except Exception:
        pass
    return found


def _hk_audit() -> dict:
    temp = _hk_temp_candidates()
    downloads = _hk_download_candidates()
    safe_bytes = sum(int(x.get("bytes") or 0) for x in temp)
    quarantine_bytes = sum(int(x.get("bytes") or 0) for x in downloads)
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
        "safe_temp_bytes": safe_bytes,
        "review_installer_files": len(downloads),
        "review_installer_bytes": quarantine_bytes,
        "safe_reclaimable_bytes": safe_bytes,
        "disk": disk,
        "protected": ["photos", "videos", "music", "documents", "Vex/Ollama/ComfyUI models", "active programs"],
        "samples": {
            "temp": [x["path"] for x in temp[:8]],
            "installers": [x["path"] for x in downloads[:8]],
        },
    }


def _hk_clean_safe() -> dict:
    temp = _hk_temp_candidates()
    downloads = _hk_download_candidates()
    deleted_bytes = 0
    deleted_files = 0
    moved = []
    skipped = 0

    for item in temp:
        path = Path(item["path"])
        try:
            size = int(item.get("bytes") or 0)
            path.unlink(missing_ok=True)
            if not path.exists():
                deleted_files += 1
                deleted_bytes += size
        except Exception:
            skipped += 1

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = HOUSEKEEPER_QUARANTINE / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    HOUSEKEEPER_MANIFESTS.mkdir(parents=True, exist_ok=True)
    for item in downloads:
        source = Path(item["path"])
        try:
            if not source.exists():
                continue
            # Preserve relative Downloads structure and never overwrite.
            try:
                rel = source.relative_to(Path.home() / "Downloads")
            except Exception:
                rel = Path(source.name)
            target = run_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target = target.with_name(f"{target.stem}-{secrets.token_hex(3)}{target.suffix}")
            source.replace(target)
            moved.append({"from": str(source), "to": str(target), "bytes": int(item.get("bytes") or 0)})
        except Exception:
            skipped += 1

    manifest = {
        "created_at": time.time(),
        "run": stamp,
        "moved": moved,
        "deleted_temp_files": deleted_files,
        "deleted_temp_bytes": deleted_bytes,
    }
    manifest_path = HOUSEKEEPER_MANIFESTS / f"{stamp}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), "utf-8")
    return {
        "ok": True,
        "node_name": socket.gethostname(),
        "deleted_temp_files": deleted_files,
        "reclaimed_bytes": deleted_bytes,
        "quarantined_files": len(moved),
        "quarantined_bytes": sum(int(x.get("bytes") or 0) for x in moved),
        "skipped": skipped,
        "manifest": str(manifest_path),
        "note": "Personal media/documents and model directories were not touched.",
    }


def _hk_restore_latest() -> dict:
    HOUSEKEEPER_MANIFESTS.mkdir(parents=True, exist_ok=True)
    manifests = sorted(HOUSEKEEPER_MANIFESTS.glob("*.json"), reverse=True)
    if not manifests:
        return {"ok": False, "error": "No housekeeping quarantine run is available to restore."}
    try:
        manifest = json.loads(manifests[0].read_text("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"Could not read housekeeping manifest: {exc}"}
    restored = 0
    skipped = 0
    for item in reversed(manifest.get("moved") or []):
        try:
            source = Path(str(item.get("to") or ""))
            target = Path(str(item.get("from") or ""))
            if not source.exists() or not str(target):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                skipped += 1
                continue
            source.replace(target)
            restored += 1
        except Exception:
            skipped += 1
    return {"ok": True, "node_name": socket.gethostname(), "restored_files": restored, "skipped": skipped, "manifest": str(manifests[0])}


def _hk_purge_quarantine() -> dict:
    import shutil
    if not HOUSEKEEPER_QUARANTINE.exists():
        return {"ok": True, "node_name": socket.gethostname(), "purged_bytes": 0, "purged_files": 0}
    total = 0
    files = 0
    for path in HOUSEKEEPER_QUARANTINE.rglob("*"):
        try:
            if path.is_file():
                total += int(path.stat().st_size)
                files += 1
        except Exception:
            pass
    try:
        shutil.rmtree(HOUSEKEEPER_QUARANTINE)
    except Exception as exc:
        return {"ok": False, "error": f"Could not purge quarantine: {exc}"}
    HOUSEKEEPER_QUARANTINE.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "node_name": socket.gethostname(), "purged_bytes": total, "purged_files": files}


def _vex_background_services() -> None:
    # Art is started in a daemon thread so Bridge becomes usable immediately.
    def warm_art() -> None:
        time.sleep(6)
        if ART_PYTHON.exists() and (ART_COMFY_DIR / "main.py").exists() and not _art_comfy_health(timeout=0.8):
            ok, error = _ensure_art_comfy()
            if ok:
                print("[art] ComfyUI warm and ready", flush=True)
            elif error:
                print(f"[art] warmup: {error}", flush=True)
    threading.Thread(target=warm_art, daemon=True, name="VexArtWarmup").start()

'''
text = text.replace(helper_marker, helpers + helper_marker, 1)

# Add deterministic resource and housekeeping routes before the cognition status route.
get_marker = '        if parsed.path == "/llm/status":\n'
if get_marker not in text:
    raise SystemExit("GET cognition marker missing")
get_routes = r'''        if parsed.path == "/resource/status":
            self._json(200, {"ok": True, "node_name": socket.gethostname(), "resources": _resource_snapshot()})
            return

        if parsed.path == "/housekeeping/audit":
            self._json(200, _hk_audit())
            return

'''
text = text.replace(get_marker, get_routes + get_marker, 1)

post_marker = '        if parsed.path == "/llm/chat":\n'
if post_marker not in text:
    raise SystemExit("POST cognition marker missing")
post_routes = r'''        if parsed.path in ("/housekeeping/clean", "/housekeeping/restore", "/housekeeping/purge"):
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                payload = {}
                if length > 0:
                    if length > 32_000:
                        self._json(413, {"ok": False, "error": "housekeeping payload too large"})
                        return
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if parsed.path == "/housekeeping/clean":
                    if str(payload.get("confirm") or "").lower() not in {"true", "1", "yes"} and payload.get("confirm") is not True:
                        self._json(400, {"ok": False, "error": "safe cleanup requires confirm=true"})
                        return
                    self._json(200, _hk_clean_safe())
                    return
                if parsed.path == "/housekeeping/restore":
                    self._json(200, _hk_restore_latest())
                    return
                if str(payload.get("confirm") or "").lower() not in {"true", "1", "yes"} and payload.get("confirm") is not True:
                    self._json(400, {"ok": False, "error": "purging quarantine requires confirm=true"})
                    return
                self._json(200, _hk_purge_quarantine())
            except Exception as exc:
                self._json(500, {"ok": False, "error": f"housekeeping failed: {exc}"})
            return

'''
text = text.replace(post_marker, post_routes + post_marker, 1)

# Advertise the new services in /status.
status_marker = '                "local_art_model": ART_CHECKPOINT if (ART_COMFY_DIR / "models" / "checkpoints" / ART_CHECKPOINT).exists() else None,\n'
if status_marker not in text:
    raise SystemExit("art status capability marker missing")
status_new = status_marker + '                "resource_director": True,\n                "housekeeping": {"audit": True, "safe_clean": True, "restore": True, "purge": True},\n                "resources": _resource_snapshot(),\n'
text = text.replace(status_marker, status_new, 1)

bridge_path.write_text(text, encoding="utf-8")

# Full launcher: v0.9.5 and background art warmup without blocking Bridge startup.
full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.4"' not in full:
    raise SystemExit("full bridge v0.9.4 marker missing")
full = full.replace('VERSION = "0.9.4"', 'VERSION = "0.9.5"', 1)
launch_marker = '    threading.Thread(target=refresh_loop, args=(state,), daemon=True, name="VexBridgeRefresh").start()\n'
if launch_marker not in full:
    raise SystemExit("full bridge refresh marker missing")
full = full.replace(launch_marker, launch_marker + '    core._vex_background_services()\n', 1)
full_path.write_text(full, encoding="utf-8")

# Sanity markers.
checks = [
    "vex-qwen3-4b:latest", '"think": False', '"num_ctx": 4096', "timeout=85",
    "HOUSEKEEPER_QUARANTINE", 'parsed.path == "/resource/status"',
    'parsed.path == "/housekeeping/audit"', '"/housekeeping/clean"',
    "ComfyUI did not become ready within 180 seconds", "_vex_background_services",
]
final = bridge_path.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"missing v0.9.5 bridge marker: {marker}")
if 'VERSION = "0.9.5"' not in full_path.read_text(encoding="utf-8"):
    raise SystemExit("missing v0.9.5 full bridge version")

print("Applied v0.9.5 resource director + safe housekeeper + art warmup + CPU cognition patch")
