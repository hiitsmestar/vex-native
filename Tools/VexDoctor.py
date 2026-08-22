#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import platform
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

VERSION = "0.9.8"
BRIDGE_DEFAULT_PORT = 8765
OLLAMA_URL = "http://127.0.0.1:11434/api/tags"
COMFY_URL = "http://127.0.0.1:8188/system_stats"


def _appdata() -> Path:
    return Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))


def _localappdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def _install_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _report_root() -> Path:
    path = _appdata() / "VexBridge" / "diagnostics"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> dict:
    value = datetime.now().astimezone()
    return {
        "iso": value.isoformat(timespec="seconds"),
        "weekday": value.strftime("%A"),
        "timezone": value.tzname() or "local",
        "utc_offset": value.strftime("%z"),
        "unix_seconds": time.time(),
    }


def _run(cmd: list[str], timeout: int = 12) -> dict:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            creationflags=flags,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "output": str(proc.stdout or "").strip()[-12000:],
        }
    except subprocess.TimeoutExpired as exc:
        output = ""
        try:
            output = str(exc.stdout or exc.output or "")[-4000:]
        except Exception:
            pass
        return {"ok": False, "timeout": True, "output": output}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _task_names() -> set[str]:
    if os.name != "nt":
        return set()
    result = _run(["tasklist", "/FO", "CSV", "/NH"], timeout=8)
    if not result.get("ok"):
        return set()
    names: set[str] = set()
    try:
        reader = csv.reader(io.StringIO(str(result.get("output") or "")))
        for row in reader:
            if row:
                names.add(row[0].lower())
    except Exception:
        pass
    return names


def _http_json(url: str, timeout: int = 4, insecure_tls: bool = False) -> dict:
    try:
        ctx = ssl._create_unverified_context() if insecure_tls else None
        request = urllib.request.Request(url, headers={"User-Agent": f"VexDoctor/{VERSION}"})
        with urllib.request.urlopen(request, timeout=timeout, context=ctx) as response:
            raw = response.read(512_000)
            payload = json.loads(raw.decode("utf-8", "replace"))
            return {"ok": True, "status": int(response.status), "payload": payload}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _bridge_config() -> tuple[Path, dict]:
    path = _appdata() / "VexBridge" / "config.json"
    if not path.exists():
        return path, {}
    try:
        return path, json.loads(path.read_text("utf-8"))
    except Exception:
        return path, {}


def _bridge_check() -> dict:
    config_path, config = _bridge_config()
    port = int(config.get("port") or BRIDGE_DEFAULT_PORT)
    token = str(config.get("token") or "")
    result = {
        "config_path": str(config_path),
        "config_exists": config_path.exists(),
        "port": port,
        "token_present": bool(token),
    }
    if not token:
        result.update({"ok": False, "error": "Bridge token/config not available"})
        return result
    url = f"https://127.0.0.1:{port}/status?token={urllib.parse.quote(token)}"
    probe = _http_json(url, timeout=6, insecure_tls=True)
    result.update(probe)
    return result


def _ollama_check() -> dict:
    executable = shutil.which("ollama")
    probe = _http_json(OLLAMA_URL, timeout=4)
    models = []
    if probe.get("ok"):
        for item in (probe.get("payload") or {}).get("models") or []:
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                models.append(name)
    preferred = next((x for x in models if x.lower() == "vex-qwen3-4b:latest"), None)
    if preferred is None:
        preferred = next((x for x in models if "qwen3" in x.lower() and "4b" in x.lower()), None)
    return {
        "ok": bool(probe.get("ok") and models),
        "executable": executable,
        "api": probe,
        "models": models,
        "preferred_model": preferred,
    }


def _comfy_check(deep: bool = False) -> dict:
    root = _localappdata() / "VexArt"
    comfy = root / "ComfyUI"
    python = root / "venv" / "Scripts" / "python.exe"
    checkpoint = comfy / "models" / "checkpoints" / "RealVisXL_V5.0_Lightning_fp16.safetensors"
    probe = _http_json(COMFY_URL, timeout=4)
    result = {
        "root": str(root),
        "installed": (comfy / "main.py").exists(),
        "python_exists": python.exists(),
        "checkpoint_exists": checkpoint.exists(),
        "checkpoint_bytes": checkpoint.stat().st_size if checkpoint.exists() else 0,
        "api": probe,
        "running": bool(probe.get("ok")),
    }
    if deep and python.exists():
        smoke = _run(
            [str(python), "-c", "import torch; print(torch.__version__); print('cuda=' + str(torch.cuda.is_available()))"],
            timeout=420,
        )
        result["torch_smoke"] = smoke
    result["ok"] = bool(result["installed"] and result["python_exists"] and result["checkpoint_exists"])
    return result


def _learning_check() -> dict:
    db = _appdata() / "VexBridge" / "learning" / "vex-learning.sqlite3"
    result = {"path": str(db), "exists": db.exists(), "bytes": db.stat().st_size if db.exists() else 0}
    if not db.exists():
        result["ok"] = False
        return result
    try:
        import sqlite3
        conn = sqlite3.connect(str(db), timeout=4)
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        counts = {}
        for table in ["topics", "notes", "activity"]:
            try:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except Exception:
                counts[table] = None
        conn.close()
        result.update({"ok": integrity.lower() == "ok", "integrity": integrity, "counts": counts})
    except Exception as exc:
        result.update({"ok": False, "error": str(exc)})
    return result


def _disk_check() -> dict:
    items = []
    if os.name == "nt":
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            root = Path(f"{letter}:\\")
            try:
                if not root.exists():
                    continue
                usage = shutil.disk_usage(root)
                items.append({
                    "drive": str(root),
                    "total_bytes": usage.total,
                    "used_bytes": usage.used,
                    "free_bytes": usage.free,
                    "free_percent": round((usage.free / usage.total) * 100.0, 1) if usage.total else 0.0,
                })
            except Exception:
                continue
    else:
        usage = shutil.disk_usage(Path.home())
        items.append({"drive": str(Path.home()), "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free})
    return {"ok": True, "drives": items}


def _recent_logs() -> dict:
    root = _appdata() / "VexBridge"
    art_root = _localappdata() / "VexArt"
    candidates = [
        root / "self-repair.log",
        root / "learning" / "learning.log",
        art_root / "comfyui-render-errors.log",
    ]
    found = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            text = path.read_text("utf-8", errors="replace")
            found.append({"path": str(path), "tail": text[-6000:]})
        except Exception:
            pass
    return {"files": found}


def collect(deep: bool = False) -> dict:
    tasks = _task_names()
    report = {
        "schema": 1,
        "doctor_version": VERSION,
        "generated_at": _now(),
        "machine": {
            "hostname": socket.gethostname(),
            "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "install_root": str(_install_root()),
        },
        "processes": {
            "vexbridge": "vexbridge.exe" in tasks,
            "ollama": "ollama.exe" in tasks,
            "python": "python.exe" in tasks,
            "watchdog_powershell": "powershell.exe" in tasks or "pwsh.exe" in tasks,
        },
        "bridge": _bridge_check(),
        "ollama": _ollama_check(),
        "comfyui": _comfy_check(deep=deep),
        "learning": _learning_check(),
        "storage": _disk_check(),
        "logs": _recent_logs(),
    }

    critical = {
        "bridge": bool(report["bridge"].get("ok")),
        "ollama": bool(report["ollama"].get("ok")),
        "art_installed": bool(report["comfyui"].get("ok")),
    }
    warnings = []
    if not critical["bridge"]:
        warnings.append("Bridge did not answer its authenticated local status probe")
    if not critical["ollama"]:
        warnings.append("Ollama did not expose a usable local model")
    if not critical["art_installed"]:
        warnings.append("Vex Art installation is incomplete or its checkpoint is missing")
    if report["learning"].get("exists") and not report["learning"].get("ok"):
        warnings.append("Learning database exists but failed integrity check")

    report["summary"] = {
        "overall": "healthy" if all(critical.values()) else ("degraded" if any(critical.values()) else "broken"),
        "critical": critical,
        "warnings": warnings,
    }
    return report


def write_report(report: dict, output: str | None = None) -> tuple[Path, Path]:
    root = _report_root()
    json_path = Path(output).expanduser() if output else (root / "latest.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), "utf-8")
    txt_path = json_path.with_suffix(".txt")

    lines = [
        f"Vex Doctor v{VERSION}",
        "=" * 48,
        f"Generated: {report['generated_at']['iso']}",
        f"Machine: {report['machine']['hostname']} / {report['machine']['user']}",
        f"Overall: {report['summary']['overall'].upper()}",
        "",
        f"Bridge: {'OK' if report['bridge'].get('ok') else 'FAIL'}",
        f"Ollama: {'OK' if report['ollama'].get('ok') else 'FAIL'} | model={report['ollama'].get('preferred_model')}",
        f"Vex Art installed: {'OK' if report['comfyui'].get('ok') else 'FAIL'} | running={report['comfyui'].get('running')}",
        f"Learning DB: {'OK' if report['learning'].get('ok') else ('NOT CREATED YET' if not report['learning'].get('exists') else 'FAIL')}",
        "",
    ]
    for warning in report["summary"].get("warnings") or []:
        lines.append(f"WARNING: {warning}")
    lines.extend(["", "Full JSON report:", str(json_path)])
    txt_path.write_text("\n".join(lines), "utf-8")
    return json_path, txt_path


def _gui(deep: bool = False) -> int:
    import tkinter as tk
    from tkinter import messagebox
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title(f"Vex Doctor v{VERSION}")
    root.geometry("900x700")
    root.minsize(760, 560)

    heading = tk.Label(root, text="Vex Doctor — deterministic node diagnostics", font=("Segoe UI", 16, "bold"))
    heading.pack(pady=(14, 6))
    note = tk.Label(root, text="Reads the real PC state directly. It does not ask the language model to guess what is working.")
    note.pack(pady=(0, 10))

    text = ScrolledText(root, wrap="word", font=("Consolas", 10))
    text.pack(fill="both", expand=True, padx=14, pady=8)

    state = {"report": None, "paths": None}

    def refresh(use_deep: bool = False) -> None:
        text.delete("1.0", "end")
        text.insert("end", "Running diagnostics...\n")
        root.update_idletasks()
        report = collect(deep=use_deep)
        paths = write_report(report)
        state["report"] = report
        state["paths"] = paths
        text.delete("1.0", "end")
        text.insert("end", paths[1].read_text("utf-8", errors="replace"))
        text.insert("end", "\n\n--- DETAIL ---\n")
        text.insert("end", json.dumps(report, indent=2, ensure_ascii=False))

    buttons = tk.Frame(root)
    buttons.pack(fill="x", padx=14, pady=(0, 14))
    tk.Button(buttons, text="Refresh", command=lambda: refresh(False), width=16).pack(side="left", padx=4)
    tk.Button(buttons, text="Deep Art Check", command=lambda: refresh(True), width=16).pack(side="left", padx=4)

    def copy_report() -> None:
        report = state.get("report")
        if report is None:
            return
        root.clipboard_clear()
        root.clipboard_append(json.dumps(report, indent=2, ensure_ascii=False))
        root.update()
        messagebox.showinfo("Vex Doctor", "Diagnostic JSON copied to the clipboard.")

    tk.Button(buttons, text="Copy Report", command=copy_report, width=16).pack(side="left", padx=4)

    def open_folder() -> None:
        folder = _report_root()
        if os.name == "nt":
            os.startfile(str(folder))

    tk.Button(buttons, text="Open Reports", command=open_folder, width=16).pack(side="left", padx=4)
    refresh(deep)
    root.mainloop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Vex Doctor — deterministic VexNative diagnostics")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--deep", action="store_true", help="include long torch import smoke test")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    if not args.headless:
        return _gui(deep=args.deep)

    report = collect(deep=args.deep)
    json_path, txt_path = write_report(report, args.json_out)
    print(json.dumps({"ok": True, "overall": report["summary"]["overall"], "json": str(json_path), "text": str(txt_path)}, ensure_ascii=False))
    return 0 if report["summary"]["overall"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
