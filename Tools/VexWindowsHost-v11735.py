from __future__ import annotations
import json, os, queue, secrets, threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import requests

VERSION = "0.11.7.35"
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
    changed = False
    if not s.get("relay_token"):
        s["relay_token"] = secrets.token_urlsafe(32)
        changed = True
    if not isinstance(s.get("nodes"), list):
        s["nodes"] = []
        changed = True
    if changed:
        save_json(STATE_PATH, s)
    return s


STATE = app_state()
INBOX: queue.Queue[dict] = queue.Queue()
EVENTS: list[dict] = []
LOCK = threading.Lock()
BRIDGE_SESSION = requests.Session()
BRIDGE_SESSION.trust_env = False


def bridge_targets(path: str) -> list[tuple[str, dict]]:
    cfg = load_json(BRIDGE_CFG)
    token = str(cfg.get("token") or "").strip()
    if not token:
        return []
    external_port = int(cfg.get("port") or 8765)
    local_port = int(cfg.get("local_control_port") or (external_port + 1))
    return [
        (f"http://127.0.0.1:{local_port}{path}", {"token": token}),
        (f"https://127.0.0.1:{external_port}{path}", {"token": token}),
    ]


def bridge_get(path: str, timeout: int = 4) -> dict:
    targets = bridge_targets(path)
    if not targets:
        return {"ok": False, "error": "bridge config unavailable"}
    last_error = "unreachable"
    for url, params in targets:
        try:
            r = BRIDGE_SESSION.get(url, params=params, timeout=timeout, verify=False)
            body = r.json() if r.content else {}
            if not isinstance(body, dict):
                body = {"value": body}
            body["http_status"] = r.status_code
            body["transport"] = "local-control" if url.startswith("http://") else "lan-tls"
            return body
        except Exception as exc:
            last_error = exc.__class__.__name__
    return {"ok": False, "error": last_error}


def bridge_post(path: str, payload: dict, timeout: int = 190) -> dict:
    targets = bridge_targets(path)
    if not targets:
        return {"ok": False, "error": "bridge config unavailable"}
    last_error = "unreachable"
    for url, params in targets:
        try:
            r = BRIDGE_SESSION.post(url, params=params, json=payload, timeout=timeout, verify=False)
            body = r.json() if r.content else {}
            if not isinstance(body, dict):
                body = {"value": body}
            body["http_status"] = r.status_code
            body["transport"] = "local-control" if url.startswith("http://") else "lan-tls"
            return body
        except Exception as exc:
            last_error = exc.__class__.__name__
    return {"ok": False, "error": last_error}


def add_event(kind: str, text: str, source: str = "windows", extra: dict | None = None) -> dict:
    event = {
        "id": secrets.token_hex(8),
        "kind": kind,
        "text": text[:8000],
        "source": source,
        "time": datetime.now().isoformat(timespec="seconds"),
    }
    if extra:
        event["payload"] = extra
    with LOCK:
        EVENTS.append(event)
        del EVENTS[:-300]
    INBOX.put(event)
    return event


def route_chat(text: str, source: str) -> None:
    result = bridge_post("/llm/chat", {"message": text, "history": []}, timeout=190)
    reply = str(result.get("reply") or "").strip()
    if reply:
        add_event(
            "assistant",
            reply,
            "vex",
            {
                "model": result.get("model"),
                "grounding": result.get("grounding"),
                "transport": result.get("transport"),
                "reply_to": source,
            },
        )
    else:
        err = str(result.get("error") or result.get("error_class") or "PC Brain did not return a reply")
        add_event("system", f"PC Brain error: {err}", "vex-host", {"reply_to": source})


def node_list() -> list[dict]:
    with LOCK:
        return list(STATE.get("nodes") or [])


def save_nodes(nodes: list[dict]) -> None:
    with LOCK:
        STATE["nodes"] = nodes
        save_json(STATE_PATH, STATE)


def register_node(name: str, host: str, port: int, token: str) -> dict:
    name, host, token = name.strip(), host.strip(), token.strip()
    if not name or not host or not token:
        raise ValueError("name, host and token are required")
    nodes = node_list()
    value = {"name": name[:100], "host": host[:255], "port": int(port), "token": token}
    nodes = [n for n in nodes if n.get("name") != value["name"]]
    nodes.append(value)
    save_nodes(nodes)
    return {k: v for k, v in value.items() if k != "token"}


def node_request(node: dict, path: str, timeout: int = 3) -> dict:
    try:
        url = f"http://{node['host']}:{int(node.get('port') or 8770)}{path}"
        r = requests.get(url, headers={"X-Vex-Node-Token": str(node.get("token") or "")}, timeout=timeout)
        body = r.json() if r.content else {}
        if not isinstance(body, dict):
            body = {"value": body}
        body["http_status"] = r.status_code
        return body
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


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
            return self.reply(200, {
                "ok": True,
                "version": VERSION,
                "brain_mode": "PC Brain" if int(b.get("http_status") or 0) in range(200, 300) else "Bridge offline",
                "bridge": b,
                "event_count": len(EVENTS),
                "nodes": [{k:v for k,v in n.items() if k != 'token'} for n in node_list()],
            })
        if self.path.startswith("/events"):
            with LOCK:
                value = list(EVENTS[-150:])
            return self.reply(200, {"ok": True, "events": value})
        if self.path.startswith("/nodes"):
            public = [{k:v for k,v in n.items() if k != "token"} for n in node_list()]
            return self.reply(200, {"ok": True, "nodes": public})
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
            source = str(body.get("source") or "iphone")
            event = add_event("message", text, source)
            threading.Thread(target=route_chat, args=(text, source), daemon=True, name="VexPCBrainRelay").start()
            return self.reply(202, {"ok": True, "event": event, "brain_mode": "PC Brain", "status": "accepted"})
        if self.path == "/ping":
            return self.reply(200, {"ok": True, "event": add_event("ping", str(body.get("text") or "ping"), str(body.get("source") or "iphone"))})
        if self.path == "/node/register":
            try:
                node = register_node(str(body.get("name") or ""), str(body.get("host") or ""), int(body.get("port") or 8770), str(body.get("token") or ""))
                return self.reply(200, {"ok": True, "node": node})
            except Exception as exc:
                return self.reply(400, {"ok": False, "error": exc.__class__.__name__})
        if self.path == "/node/ping":
            name = str(body.get("name") or "")
            node = next((n for n in node_list() if n.get("name") == name), None)
            if not node:
                return self.reply(404, {"ok": False, "error": "node not found"})
            return self.reply(200, {"ok": True, "node": name, "result": node_request(node, "/status")})
        return self.reply(404, {"ok": False, "error": "not found"})


def run_relay():
    server = ThreadingHTTPServer(("0.0.0.0", HOST_PORT), RelayHandler)
    server.serve_forever()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Vex Windows {VERSION}")
        self.geometry("900x660")
        self.minsize(720, 520)
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
        self.log.insert("end", "Vex Windows host ready. PC Brain routing enabled; shared phone/PC relay and lightweight LAN nodes are attached to the same Bridge.\n\n")
        self.log.configure(state="disabled")

        row = ttk.Frame(self)
        row.pack(fill="x", padx=18, pady=(0, 16))
        self.entry = tk.Entry(row, bg="#2a1831", fg="white", insertbackground="white", relief="flat", font=("Segoe UI", 12))
        self.entry.pack(side="left", fill="x", expand=True, ipady=9)
        self.entry.bind("<Return>", lambda e: self.send())
        ttk.Button(row, text="Send", command=self.send).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Ping phone", command=lambda: self.local_event("ping", "Windows ping")).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Bridge status", command=self.refresh_status).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="LAN nodes", command=self.show_nodes).pack(side="left", padx=(8, 0))

        relay = ttk.Frame(self)
        relay.pack(fill="x", padx=18, pady=(0, 12))
        ttk.Label(relay, text=f"Relay port: {HOST_PORT}   Token: {STATE['relay_token'][:8]}…   Nodes: {len(node_list())}").pack(side="left")

        threading.Thread(target=run_relay, daemon=True).start()
        self.after(300, self.drain)
        self.after(800, self.refresh_status)
        self.after(5000, self.poll_status)

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
        self.append("Vex Host", "PC Brain thinking…")
        threading.Thread(target=route_chat, args=(text, "windows"), daemon=True, name="VexPCBrainLocal").start()

    def drain(self):
        try:
            while True:
                event = INBOX.get_nowait()
                source = event.get("source", "remote")
                if source == "windows":
                    continue
                if event.get("kind") == "assistant" and source == "vex":
                    self.append("Vex", event.get("text", ""))
                elif source == "vex-host":
                    self.append("Vex Host", event.get("text", ""))
                else:
                    self.append(source.title(), f"[{event.get('kind')}] {event.get('text')}")
        except queue.Empty:
            pass
        self.after(300, self.drain)

    def poll_status(self):
        self.refresh_status()
        self.after(5000, self.poll_status)

    def refresh_status(self):
        def work():
            b = bridge_get("/status")
            reachable = int(b.get("http_status") or 0) in range(200, 300)
            text = f"Bridge: {'online' if reachable else 'offline'}"
            if reachable:
                text += f" • PC Brain • v{b.get('version','?')} • {b.get('indexed_files',0)} files • {b.get('transport','?')}"
            self.after(0, lambda: self.status.configure(text=text))
        threading.Thread(target=work, daemon=True).start()

    def show_nodes(self):
        nodes = node_list()
        if not nodes:
            self.append("Vex Host", "No LAN node agents are registered yet.")
            return
        for node in nodes:
            result = node_request(node, "/status")
            self.append("Vex Node", f"{node.get('name')} @ {node.get('host')}:{node.get('port')} → {'online' if result.get('ok') else result.get('error','offline')}")


if __name__ == "__main__":
    requests.packages.urllib3.disable_warnings()
    App().mainloop()
