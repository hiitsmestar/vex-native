#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VERSION = "0.9.8"


def root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def expand(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def manifest() -> dict:
    path = root_dir() / "VexToolManifest.json"
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception:
            pass
    return {"tools": []}


def launch_path(path: Path, args: list[str] | None = None) -> None:
    args = args or []
    if not path.exists():
        raise FileNotFoundError(str(path))
    if path.suffix.lower() in {".cmd", ".bat"}:
        subprocess.Popen(["cmd.exe", "/c", "start", "", str(path), *args], cwd=str(path.parent))
    else:
        subprocess.Popen([str(path), *args], cwd=str(path.parent))


def main() -> int:
    import tkinter as tk
    from tkinter import messagebox

    data = manifest()
    app = tk.Tk()
    app.title(f"Vex Toolbox v{VERSION}")
    app.geometry("760x620")
    app.minsize(650, 500)

    tk.Label(app, text="Vex Toolbox", font=("Segoe UI", 19, "bold")).pack(pady=(16, 2))
    tk.Label(app, text="On-demand apps for VexNative. Closed tools consume no background resources.").pack(pady=(0, 8))

    clock = tk.Label(app, font=("Consolas", 11))
    clock.pack(pady=(0, 12))

    def tick() -> None:
        now = datetime.now().astimezone()
        clock.configure(text=now.strftime("%A, %Y-%m-%d  %I:%M:%S %p  %Z"))
        app.after(1000, tick)

    tick()

    frame = tk.Frame(app)
    frame.pack(fill="both", expand=True, padx=18, pady=8)

    def add_row(title: str, description: str, callback, enabled: bool = True) -> None:
        row = tk.Frame(frame, bd=1, relief="groove")
        row.pack(fill="x", pady=5)
        left = tk.Frame(row)
        left.pack(side="left", fill="both", expand=True, padx=12, pady=10)
        tk.Label(left, text=title, font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(left, text=description, anchor="w", justify="left", wraplength=500).pack(fill="x")
        button = tk.Button(row, text="Open", width=12, command=callback)
        button.pack(side="right", padx=12)
        if not enabled:
            button.configure(state="disabled")

    def safe(callback):
        def wrapped():
            try:
                callback()
            except Exception as exc:
                messagebox.showerror("Vex Toolbox", str(exc))
        return wrapped

    doctor = root_dir() / "VexDoctor.exe"
    add_row(
        "Vex Doctor",
        "Deterministic Bridge/Ollama/ComfyUI/learning/storage diagnostics. It reads the PC directly instead of asking the language model to guess.",
        safe(lambda: launch_path(doctor)),
        doctor.exists(),
    )

    art_root = expand(r"%LOCALAPPDATA%\VexArt")
    art_cmd = art_root / "RUN-VEX-ART.cmd"
    add_row(
        "Vex Art / ComfyUI",
        "Local image renderer. Start it only when needed; it can stay closed the rest of the time.",
        safe(lambda: launch_path(art_cmd)),
        art_cmd.exists(),
    )

    start_heal = root_dir() / "START-VEX-SELF-HEAL.cmd"
    add_row(
        "Vex Core + Self Heal",
        "Starts the lightweight always-on Bridge/watchdog layer.",
        safe(lambda: launch_path(start_heal)),
        start_heal.exists(),
    )

    reports = expand(r"%APPDATA%\VexBridge\diagnostics")
    add_row(
        "Diagnostic Reports",
        "Open the folder containing latest.json and latest.txt from Vex Doctor.",
        safe(lambda: os.startfile(str(reports if reports.exists() else reports.parent))),
        True,
    )

    learning = expand(r"%APPDATA%\VexBridge\learning")
    add_row(
        "Learning Store",
        "Open Vex's source-grounded local learning database folder. The database remains persistent even when workers are idle.",
        safe(lambda: os.startfile(str(learning if learning.exists() else learning.parent))),
        True,
    )

    info = tk.Text(app, height=7, wrap="word")
    info.pack(fill="x", padx=18, pady=(6, 14))
    info.insert("1.0", "Architecture rule: Bridge + watchdog + cognition routing + time grounding stay lightweight and available. Specialized work moves into separate apps/workers that Vex can launch, inspect, repair, and close independently.\n\n")
    planned = data.get("planned_extractions") or []
    if planned:
        info.insert("end", "Planned next extractions: " + ", ".join(str(x) for x in planned))
    info.configure(state="disabled")

    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
