#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

VERSION = "0.9.9"
REPO = "hiitsmestar/vex-native"
OWNER = "hiitsmestar"
ISSUE_NUMBER = 52
POLL_SECONDS = 15
SESSION_SECONDS = 2 * 60 * 60


def app_root() -> Path:
    root = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexRemoteSupport"
    root.mkdir(parents=True, exist_ok=True)
    return root


STATE_PATH = app_root() / "state.json"


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text("utf-8"))
    except Exception:
        return {}


def save_state(data: dict) -> None:
    STATE_PATH.write_text(json.dumps(data, indent=2), "utf-8")


def node_id() -> str:
    state = load_state()
    value = str(state.get("node_id") or "").strip()
    if not value:
        value = "vex-" + secrets.token_hex(4)
        state["node_id"] = value
        save_state(state)
    return value


def gh_path() -> str | None:
    direct = shutil.which("gh") or shutil.which("gh.exe")
    if direct:
        return direct
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "GitHub CLI" / "gh.exe",
        Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "GitHub CLI" / "gh.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def run_quiet(args: list[str], timeout: int = 30, input_text: str | None = None) -> subprocess.CompletedProcess:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        args,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        creationflags=flags,
    )


def gh_ready() -> tuple[bool, str]:
    gh = gh_path()
    if not gh:
        return False, "GitHub CLI is not installed"
    try:
        result = run_quiet([gh, "auth", "status", "-h", "github.com"], timeout=15)
        if result.returncode == 0:
            return True, "GitHub access is ready"
        return False, "GitHub CLI is installed but not signed in"
    except Exception as exc:
        return False, f"GitHub check failed: {exc}"


def launch_github_setup() -> None:
    gh = gh_path()
    if gh:
        command = f'& "{gh}" auth login -h github.com -p https -w'
    else:
        command = (
            'winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements; '
            '$gh=(Get-Command gh -ErrorAction SilentlyContinue); '
            'if (-not $gh) { $p="$env:ProgramFiles\\GitHub CLI\\gh.exe"; if (Test-Path $p) { $gh=$p } }; '
            'if ($gh) { & $gh auth login -h github.com -p https -w } else { Write-Host "GitHub CLI was not found after install." }'
        )
    subprocess.Popen(["powershell.exe", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", command])


def bridge_config() -> dict:
    path = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexBridge" / "config.json"
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return {}


def bridge_url(path: str) -> tuple[str, dict] | None:
    config = bridge_config()
    token = str(config.get("token") or "").strip()
    port = int(config.get("port") or 8765)
    if not token:
        return None
    return f"https://127.0.0.1:{port}{path}", {"token": token}


def bridge_get(path: str, timeout: int = 8) -> dict:
    target = bridge_url(path)
    if not target:
        return {"ok": False, "error": "bridge config unavailable"}
    url, params = target
    try:
        response = requests.get(url, params=params, timeout=timeout, verify=False)
        payload = response.json() if response.content else {}
        if not isinstance(payload, dict):
            payload = {"value": payload}
        payload.setdefault("http_status", response.status_code)
        if response.status_code >= 400:
            payload.setdefault("ok", False)
        return payload
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


def bridge_post(path: str, payload: dict | None = None, timeout: int = 180) -> dict:
    target = bridge_url(path)
    if not target:
        return {"ok": False, "error": "bridge config unavailable"}
    url, params = target
    try:
        response = requests.post(url, params=params, json=payload or {}, timeout=timeout, verify=False)
        body = response.json() if response.content else {}
        if not isinstance(body, dict):
            body = {"value": body}
        body.setdefault("http_status", response.status_code)
        if response.status_code >= 400:
            body.setdefault("ok", False)
        return body
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


def yes(value: Any) -> bool:
    return value is True or str(value or "").lower() in {"true", "1", "yes", "ready", "healthy", "ok"}


def integer(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except Exception:
        return default


def model_label(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    # Model names are project metadata, but strip anything path-like just in case.
    raw = raw.replace("\\", "/").split("/")[-1]
    return raw[:120]


def doctor_path() -> Path | None:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    candidates = [base / "VexDoctor.exe", base / "dist" / "VexDoctor.exe"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def doctor_summary(deep: bool = False) -> dict:
    doctor = doctor_path()
    if not doctor:
        return {"available": False}
    args = [str(doctor), "--headless"]
    if deep:
        args.append("--deep")
    try:
        result = run_quiet(args, timeout=520 if deep else 120)
        last = (result.stdout or "").strip().splitlines()[-1:] or [""]
        payload = json.loads(last[0]) if last[0].startswith("{") else {}
        return {
            "available": True,
            "overall": str(payload.get("overall") or ("healthy" if result.returncode == 0 else "attention"))[:40],
            "exit_code": int(result.returncode),
            "deep": deep,
        }
    except subprocess.TimeoutExpired:
        return {"available": True, "overall": "timeout", "deep": deep}
    except Exception as exc:
        return {"available": True, "overall": "error", "error_class": exc.__class__.__name__, "deep": deep}


def disk_summary() -> dict:
    try:
        usage = shutil.disk_usage(Path.home().anchor or r"C:\")
        return {
            "total_gb": round(usage.total / (1024 ** 3), 1),
            "free_gb": round(usage.free / (1024 ** 3), 1),
            "free_percent": round((usage.free / usage.total) * 100, 1) if usage.total else 0.0,
        }
    except Exception:
        return {}


def learning_public(value: dict) -> dict:
    counts = value.get("queue_counts") if isinstance(value.get("queue_counts"), dict) else {}
    queue = value.get("queue") if isinstance(value.get("queue"), list) else []
    recent = value.get("recent") if isinstance(value.get("recent"), list) else []
    return {
        "ok": yes(value.get("ok")),
        "notes": integer(value.get("notes")),
        "queue_counts": {str(k)[:40]: integer(v) for k, v in counts.items()},
        "queued_items": len(queue),
        "recent_note_count": len(recent),
    }


def maintenance_public(value: dict) -> dict:
    return {
        "ok": yes(value.get("ok")),
        "safe_reclaimable_bytes": integer(value.get("safe_reclaimable_bytes")),
        "approval_required_files": integer(value.get("approval_required_files")),
        "approval_required_bytes": integer(value.get("approval_required_bytes")),
        "auto_maintenance": yes(value.get("auto_maintenance")),
        "safe_cleanup_interval_hours": integer(value.get("safe_cleanup_interval_hours")),
        "drive_optimize_interval_days": integer(value.get("drive_optimize_interval_days")),
    }


def audit_public(value: dict) -> dict:
    return {
        "ok": yes(value.get("ok")),
        "safe_temp_files": integer(value.get("safe_temp_files")),
        "safe_cache_files": integer(value.get("safe_cache_files")),
        "auto_installer_files": integer(value.get("auto_installer_files")),
        "approval_required_files": integer(value.get("approval_required_files")),
        "safe_reclaimable_bytes": integer(value.get("safe_reclaimable_bytes")),
        "approval_required_bytes": integer(value.get("approval_required_bytes")),
    }


def collect_snapshot(include_doctor: bool = False, deep: bool = False) -> dict:
    status = bridge_get("/status", timeout=8)
    llm = bridge_get("/llm/status", timeout=8)
    art = bridge_get("/art/health", timeout=8)
    learning = bridge_get("/learning/status", timeout=10)
    maintenance = bridge_get("/maintenance/status", timeout=20)
    snap = {
        "protocol": "vex-support-v1",
        "agent_version": VERSION,
        "node_id": node_id(),
        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bridge": {
            "reachable": integer(status.get("http_status")) in range(200, 300),
            "version": str(status.get("version") or "")[:40] or None,
            "indexed_files": integer(status.get("indexed_files")),
            "uptime_seconds": integer(status.get("uptime_seconds")),
        },
        "cognition": {
            "ok": yes(llm.get("ok")),
            "model": model_label(llm.get("model")),
            "available_model_count": len(llm.get("available_models") or []) if isinstance(llm.get("available_models"), list) else 0,
        },
        "art": {
            "ok": yes(art.get("ok")),
            "installed": yes(art.get("installed")),
            "running": yes(art.get("running")),
            "model": model_label(art.get("model")),
        },
        "learning": learning_public(learning),
        "maintenance": maintenance_public(maintenance),
        "storage": disk_summary(),
    }
    if include_doctor:
        snap["doctor"] = doctor_summary(deep=deep)
    return snap


def gh_api(args: list[str], timeout: int = 30, input_json: dict | None = None) -> Any:
    gh = gh_path()
    if not gh:
        raise RuntimeError("GitHub CLI is not installed")
    cmd = [gh, "api", *args]
    input_text = None
    if input_json is not None:
        cmd += ["--input", "-"]
        input_text = json.dumps(input_json, ensure_ascii=False)
    result = run_quiet(cmd, timeout=timeout, input_text=input_text)
    if result.returncode != 0:
        raise RuntimeError((result.stdout or "GitHub API request failed")[-1200:])
    text = (result.stdout or "").strip()
    return json.loads(text) if text else {}


def fetch_comments() -> list[dict]:
    data = gh_api([f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments?per_page=100"], timeout=30)
    return data if isinstance(data, list) else []


def post_comment(kind: str, payload: dict) -> None:
    envelope = {
        "kind": kind,
        "node_id": node_id(),
        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "payload": payload,
    }
    body = "VEXRESULT\n```json\n" + json.dumps(envelope, ensure_ascii=False, indent=2) + "\n```"
    gh_api(["-X", "POST", f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments"], timeout=30, input_json={"body": body})


TECHNICAL_TERMS = {
    "python", "swift", "swiftui", "coding", "programming", "software", "debug", "debugging", "git", "github",
    "windows", "powershell", "network", "http", "https", "tls", "api", "json", "sql", "sqlite", "algorithm",
    "data structure", "testing", "security", "performance", "comfyui", "pytorch", "ollama", "qwen", "linux",
    "javascript", "typescript", "html", "css", "c++", "cpp", "c language", "architecture", "database", "concurrency",
}


def technical_topic(topic: str) -> bool:
    low = topic.lower()
    return len(topic) <= 500 and any(term in low for term in TECHNICAL_TERMS)


def clean_result(value: Any) -> Any:
    # Only explicit, non-sensitive fields are returned from remote commands.
    if not isinstance(value, dict):
        return {"ok": False, "error": "unexpected local response"}
    return {
        "ok": yes(value.get("ok")),
        "http_status": integer(value.get("http_status")),
        "error_class": str(value.get("error") or "")[:120] if value.get("error") else None,
    }


def execute_command(command: dict, allow_maintenance: bool) -> dict:
    action = str(command.get("action") or "").strip().lower()
    if action == "status":
        return collect_snapshot(include_doctor=False)
    if action == "doctor":
        return {"doctor": doctor_summary(deep=False)}
    if action == "doctor_deep":
        return {"doctor": doctor_summary(deep=True)}
    if action == "bridge_status":
        s = bridge_get("/status")
        return {
            "bridge": {
                "reachable": integer(s.get("http_status")) in range(200, 300),
                "version": str(s.get("version") or "")[:40] or None,
                "indexed_files": integer(s.get("indexed_files")),
                "uptime_seconds": integer(s.get("uptime_seconds")),
            }
        }
    if action == "art_health":
        a = bridge_get("/art/health")
        return {"art": {"ok": yes(a.get("ok")), "installed": yes(a.get("installed")), "running": yes(a.get("running")), "model": model_label(a.get("model"))}}
    if action == "learning_status":
        return {"learning": learning_public(bridge_get("/learning/status", timeout=12))}
    if action == "learning_queue":
        topic = str(command.get("topic") or "").strip()
        if not technical_topic(topic):
            return {"ok": False, "error": "remote learning queue accepts technical topics only"}
        result = bridge_post("/learning/queue", {"topic": topic, "reason": "remote-support", "priority": 82}, timeout=20)
        return {"ok": yes(result.get("ok")), "queued": yes(result.get("queued")), "http_status": integer(result.get("http_status"))}
    if action == "learning_run":
        result = bridge_post("/learning/run", {}, timeout=190)
        return {"ok": yes(result.get("ok")), "detail": str(result.get("detail") or "")[:180], "http_status": integer(result.get("http_status"))}
    if action == "maintenance_status":
        return {"maintenance": maintenance_public(bridge_get("/maintenance/status", timeout=20))}
    if action == "housekeeping_audit":
        return {"housekeeping": audit_public(bridge_get("/housekeeping/audit", timeout=30))}
    if action == "maintenance_run":
        if not allow_maintenance:
            return {"ok": False, "error": "local safe-maintenance permission is OFF"}
        result = bridge_post("/maintenance/run", {"confirm": True, "optimize": bool(command.get("optimize") is True)}, timeout=1900)
        return {
            "ok": yes(result.get("ok")),
            "deleted_safe_files": integer(result.get("deleted_safe_files")),
            "reclaimed_bytes": integer(result.get("reclaimed_bytes")),
            "approval_required_files": integer(result.get("approval_required_files")),
            "optimized_drives": integer(result.get("optimized_drives")),
            "skipped": integer(result.get("skipped")),
            "http_status": integer(result.get("http_status")),
        }
    return {"ok": False, "error": f"unsupported action: {action}"}


def parse_command(body: str) -> dict | None:
    # Commands are deliberately one-line JSON so public relay comments are easy to audit.
    match = re.search(r"(?:^|\n)VEXCMD\s+(\{[^\r\n]+\})", str(body or ""))
    if not match:
        return None
    try:
        value = json.loads(match.group(1))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


class SupportWorker:
    def __init__(self, allow_maintenance) -> None:
        self.allow_maintenance = allow_maintenance
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.started_at = 0.0
        self.on_status = lambda text: None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.started_at = time.time()
        self.thread = threading.Thread(target=self.loop, daemon=True, name="VexRemoteSupport")
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def loop(self) -> None:
        try:
            ready, detail = gh_ready()
            if not ready:
                self.on_status(detail)
                return
            state = load_state()
            last_id = integer(state.get("last_comment_id"))
            post_comment("session_started", collect_snapshot(include_doctor=False))
            self.on_status("Support session is active")
            while not self.stop_event.wait(POLL_SECONDS):
                if time.time() - self.started_at >= SESSION_SECONDS:
                    self.on_status("Support session ended after 2 hours")
                    break
                comments = fetch_comments()
                for comment in comments:
                    cid = integer(comment.get("id"))
                    if cid <= last_id:
                        continue
                    last_id = max(last_id, cid)
                    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
                    if str(user.get("login") or "").lower() != OWNER.lower():
                        continue
                    command = parse_command(str(comment.get("body") or ""))
                    if not command:
                        continue
                    target = str(command.get("node_id") or "").strip()
                    if target and target != node_id() and target != "all":
                        continue
                    command_id = str(command.get("id") or f"comment-{cid}")[:80]
                    self.on_status(f"Running {str(command.get('action') or 'command')}…")
                    result = execute_command(command, allow_maintenance=bool(self.allow_maintenance()))
                    post_comment("command_result", {"command_id": command_id, "action": str(command.get("action") or "")[:80], "result": result})
                    self.on_status("Support session is active")
                state = load_state()
                state["last_comment_id"] = last_id
                save_state(state)
        except Exception as exc:
            self.on_status(f"Support error: {exc.__class__.__name__}")
        finally:
            try:
                post_comment("session_ended", {"reason": "stopped" if self.stop_event.is_set() else "timeout_or_error"})
            except Exception:
                pass


def main() -> int:
    import tkinter as tk
    from tkinter import messagebox
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title(f"Vex Remote Support v{VERSION}")
    root.geometry("760x640")
    root.minsize(680, 560)

    tk.Label(root, text="Vex Remote Support", font=("Segoe UI", 18, "bold")).pack(pady=(16, 4))
    tk.Label(root, text="Opt-in support relay for diagnostics, technical learning, and explicitly allowed safe maintenance.", wraplength=700).pack(pady=(0, 6))
    tk.Label(root, text="The project repository is public. This app publishes sanitized health only—never tokens, IPs, usernames, personal paths/files, or chat contents.", wraplength=700, justify="center").pack(padx=16, pady=(0, 12))

    ident = tk.Label(root, text=f"Node: {node_id()}   •   Relay: {REPO} issue #{ISSUE_NUMBER}", font=("Consolas", 10))
    ident.pack(pady=(0, 8))

    status_var = tk.StringVar(value=gh_ready()[1])
    tk.Label(root, textvariable=status_var, font=("Segoe UI", 11, "bold")).pack(pady=(0, 8))

    allow_maintenance_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        root,
        text="Allow remote SAFE maintenance during this session (safe junk only; protected/review files stay untouched)",
        variable=allow_maintenance_var,
        wraplength=700,
        justify="left",
    ).pack(anchor="w", padx=22, pady=(0, 10))

    worker = SupportWorker(lambda: allow_maintenance_var.get())

    def set_status(value: str) -> None:
        root.after(0, lambda: status_var.set(value))

    worker.on_status = set_status

    buttons = tk.Frame(root)
    buttons.pack(fill="x", padx=18, pady=8)

    def setup_github() -> None:
        launch_github_setup()
        messagebox.showinfo("Vex Remote Support", "A setup window opened. Finish the GitHub browser sign-in once, then come back here and press Test GitHub.")

    def test_github() -> None:
        ready, detail = gh_ready()
        status_var.set(detail)
        if ready:
            messagebox.showinfo("Vex Remote Support", "GitHub relay access is ready.")
        else:
            messagebox.showwarning("Vex Remote Support", detail)

    def start_session() -> None:
        ready, detail = gh_ready()
        if not ready:
            messagebox.showwarning("Vex Remote Support", detail + ". Use Set Up GitHub first.")
            return
        worker.start()
        status_var.set("Starting support session…")

    def stop_session() -> None:
        worker.stop()
        status_var.set("Stopping support session…")

    tk.Button(buttons, text="Set Up GitHub", command=setup_github, width=16).pack(side="left", padx=4)
    tk.Button(buttons, text="Test GitHub", command=test_github, width=14).pack(side="left", padx=4)
    tk.Button(buttons, text="Start 2-Hour Session", command=start_session, width=18).pack(side="left", padx=4)
    tk.Button(buttons, text="Stop Session", command=stop_session, width=14).pack(side="left", padx=4)

    output = ScrolledText(root, height=20, wrap="word", font=("Consolas", 9))
    output.pack(fill="both", expand=True, padx=18, pady=(8, 14))

    def refresh_local() -> None:
        output.delete("1.0", "end")
        output.insert("end", json.dumps(collect_snapshot(include_doctor=False), indent=2, ensure_ascii=False))

    lower = tk.Frame(root)
    lower.pack(fill="x", padx=18, pady=(0, 14))
    tk.Button(lower, text="Refresh Local Snapshot", command=refresh_local, width=20).pack(side="left", padx=4)

    def publish_now() -> None:
        ready, detail = gh_ready()
        if not ready:
            messagebox.showwarning("Vex Remote Support", detail)
            return
        try:
            post_comment("manual_snapshot", collect_snapshot(include_doctor=True))
            status_var.set("Sanitized snapshot published")
        except Exception as exc:
            messagebox.showerror("Vex Remote Support", str(exc))

    tk.Button(lower, text="Publish Sanitized Snapshot", command=publish_now, width=24).pack(side="left", padx=4)
    refresh_local()

    def on_close() -> None:
        worker.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
