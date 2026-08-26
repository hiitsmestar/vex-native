from __future__ import annotations
import json, os, queue, secrets, threading, time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import requests

VERSION = "0.11.7.31"
HOST_PORT = 8768
APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexWindows"
APP_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = APP_DIR / "state.json"
BRIDGE_CFG = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexBridge" / "config.json"


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return {}


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), "utf-8")


def app_state() -> dict:
    s = load_json(STATE_PATH)
    if not s.get("relay_token"):
        s["relay_token"] = secrets.token_urlsafe(32)
        save_json(STATE_PATH, s)
    return s

STATE = app_state()
INBOX: queue.Queue[dict] = queue.Queue()
EVENTS: list[dict] = []
LOCK = threading.Lock()


def bridge_target(path: str) -> tuple[str, dict] | None:
    cfg = load_json(BRIDGE_CFG)
    token = str(cfg.get("token") or "").strip()
    port = int(cfg.get("port") or 8765)
    if not token:
        return None
    return f"https://127.0.0.1:{port}{path}", {"token": token}


def bridge_get(path: str, timeout: int = 4) -> dict:
    target = bridge_target(path)
    if not target:
        return {"ok": False, "error": "bridge config unavailable"}
    url, params = target
    try:
        r = requests.get(url, params=params, timeout=timeout, verify=False)
        body = r.json() if r.content else {}
        if not isinstance(body, dict):
            body = {"value": body}
        body["http_status"] = r.status_code
        return body
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


def add_event(kind: str, text: str, source: str = "windows") -> dict:
    event = {
        "id": secrets.token_hex(8),
        "kind": kind,
        "text": text[:8000],
        "source": source,
        "time": datetime.now().isoformat(timespec="seconds"),
    }
    with LOCK:
        EVENTS.append(event)
        del EVENTS[:-200]
    INBOX.put(event)
    return event


class RelayHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def reply(self, code: int, value: dict):
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Vex-Token", ""), str(STATE.get("relay_token") or ""))

    def do_GET(self):
        if not self.authorized():
            return self.reply(401, {"ok": False, "error": "unauthorized"})
        if self.path.startswith("/status"):
            b = bridge_get("/status")
            return self.reply(200, {"ok": True, "version": VERSION, "bridge": b, "event_count": len(EVENTS)})
        if self.path.startswith("/events"):
            with LOCK:
                value = list(EVENTS[-100:])
            return self.reply(200, {"ok": True, "events": value})
        return self.reply(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if not self.authorized():
            return self.reply(401, {"ok": False, "error": "unauthorized"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            body = {}
        if self.path == "/message":
            text = str(body.get("text") or "").strip()
            if not text:
                return self.reply(400, {"ok": False, "error": "empty message"})
            return self.reply(200, {"ok": True, "event": add_event("message", text, str(body.get("source") or "iphone"))})
        if self.path == "/ping":
            return self.reply(200, {"ok": True, "event": add_event("ping", str(body.get("text") or "ping"), str(body.get("source") or "iphone"))})
        return self.reply(404, {"ok": False, "error": "not found"})


def run_relay():
    server = ThreadingHTTPServer(("0.0.0.0", HOST_PORT), RelayHandler)
    server.serve_forever()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Vex Windows {VERSION}")
        self.geometry("820x620")
        self.minsize(680, 480)
        self.configure(bg="#140b18")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#140b18")
        style.configure("TLabel", background="#140b18", foreground="#eadcf0", font=("Segoe UI", 11))
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"), foreground="#ffffff")
        style.configure("TButton", font=("Segoe UI", 10, "bold"))

        top = ttk.Frame(self)
        top.pack(fill="x", padx=18, pady=14)
        ttk.Label(top, text="Vex ✦ Windows Host", style="Title.TLabel").pack(side="left")
        self.status = ttk.Label(top, text="Bridge: checking…")
        self.status.pack(side="right")

        self.log = tk.Text(self, bg="#1f1125", fg="#f7edf9", insertbackground="white", relief="flat", wrap="word", font=("Segoe UI", 12))
        self.log.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.log.insert("end", "Vex Windows host ready. Shared relay is listening on port 8768.\n\n")
        self.log.configure(state="disabled")

        row = ttk.Frame(self)
        row.pack(fill="x", padx=18, pady=(0, 16))
        self.entry = tk.Entry(row, bg="#2a1831", fg="white", insertbackground="white", relief="flat", font=("Segoe UI", 12))
        self.entry.pack(side="left", fill="x", expand=True, ipady=9)
        self.entry.bind("<Return>", lambda e: self.send())
        ttk.Button(row, text="Send", command=self.send).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Ping phone", command=lambda: self.local_event("ping", "Windows ping")).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Bridge status", command=self.refresh_status).pack(side="left", padx=(8, 0))

        relay = ttk.Frame(self)
        relay.pack(fill="x", padx=18, pady=(0, 12))
        ttk.Label(relay, text=f"Relay port: {HOST_PORT}   Token: {STATE['relay_token'][:8]}…   (full token stored in %APPDATA%\\VexWindows\\state.json)").pack(side="left")

        threading.Thread(target=run_relay, daemon=True).start()
        self.after(300, self.drain)
        self.after(800, self.refresh_status)

    def append(self, who: str, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", f"{who}: {text}\n\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def local_event(self, kind: str, text: str):
        event = add_event(kind, text, "windows")
        self.append("Windows", f"[{kind}] {event['text']}")

    def send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        add_event("message", text, "windows")
        self.append("Star", text)
        self.append("Vex Host", "Message queued for the shared Vex relay. Local-model routing is the next layer; this host already gives phone/PC a common transport and state surface.")

    def drain(self):
        try:
            while True:
                event = INBOX.get_nowait()
                if event.get("source") != "windows":
                    self.append(event.get("source", "remote").title(), f"[{event.get('kind')}] {event.get('text')}")
        except queue.Empty:
            pass
        self.after(300, self.drain)

    def refresh_status(self):
        def work():
            b = bridge_get("/status")
            reachable = int(b.get("http_status") or 0) in range(200, 300)
            text = f"Bridge: {'online' if reachable else 'offline'}"
            if reachable:
                text += f" • v{b.get('version','?')} • {b.get('indexed_files',0)} files"
            self.after(0, lambda: self.status.configure(text=text))
        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    requests.packages.urllib3.disable_warnings()
    App().mainloop()
