#!/usr/bin/env python3
from pathlib import Path

src = Path("Tools/VexWindowsHost-v11736.py").read_text(encoding="utf-8")

if 'VERSION = "0.11.7.40"' in src and 'def ping_phone(' in src and 'CHAT_HISTORY' in src:
    Path("Tools/VexWindowsHost-v11740.py").write_text(src, encoding="utf-8")
    raise SystemExit(0)

if 'VERSION = "0.11.7.36"' not in src:
    raise SystemExit("v0.11.7.36 version marker missing")
src = src.replace('VERSION = "0.11.7.36"', 'VERSION = "0.11.7.40"', 1)

state_anchor = 'BRIDGE_CFG = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexBridge" / "config.json"\n'
state_replacement = state_anchor + 'REMOTE_SUPPORT_STATE = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexRemoteSupport" / "state.json"\nNTFY_SERVER = "https://ntfy.sh"\n'
if state_anchor not in src:
    raise SystemExit("Bridge config anchor missing")
src = src.replace(state_anchor, state_replacement, 1)

helper_anchor = '''def bridge_post(path: str, payload: dict, timeout: int = 190) -> dict:\n    targets = bridge_targets(path)\n    if not targets:\n        return {"ok": False, "error": "bridge config unavailable"}\n    last_error = "unreachable"\n    for url, params in targets:\n        try:\n            r = BRIDGE_SESSION.post(url, params=params, json=payload, timeout=timeout, verify=False)\n            body = r.json() if r.content else {}\n            if not isinstance(body, dict):\n                body = {"value": body}\n            body["http_status"] = r.status_code\n            body["transport"] = "local-control" if url.startswith("http://") else "lan-tls"\n            return body\n        except Exception as exc:\n            last_error = exc.__class__.__name__\n    return {"ok": False, "error": last_error}\n\n\n'''
helper_replacement = helper_anchor + '''def phone_notify_settings() -> tuple[str, str]:\n    state = load_json(REMOTE_SUPPORT_STATE)\n    topic = str(state.get("ntfy_topic") or "").strip()\n    if not topic or len(topic) > 180 or not all(ch.isalnum() or ch in "_-" for ch in topic):\n        return "", "Vex PC"\n    label = str(state.get("node_label") or "Upstairs").strip()[:48] or "Upstairs"\n    return topic, label\n\n\ndef send_phone_notification(message: str) -> tuple[bool, str]:\n    topic, label = phone_notify_settings()\n    if not topic:\n        return False, "phone notification topic is not configured"\n    try:\n        response = requests.post(\n            f"{NTFY_SERVER}/{topic}",\n            data=str(message)[:500].encode("utf-8"),\n            headers={"Title": f"Vex - {label}", "Priority": "default", "Tags": "computer"},\n            timeout=12,\n        )\n        if 200 <= response.status_code < 300:\n            return True, "sent"\n        return False, f"ntfy HTTP {response.status_code}"\n    except Exception as exc:\n        return False, exc.__class__.__name__\n\n\n'''
if helper_anchor not in src:
    raise SystemExit("bridge_post helper anchor missing")
src = src.replace(helper_anchor, helper_replacement, 1)

# The original Host sent history=[] for every request, which made second-turn
# continuity impossible no matter how good the Bridge recall logic was.
history_anchor = 'LOCK = threading.Lock()\nBRIDGE_SESSION = requests.Session()\n'
history_replacement = 'LOCK = threading.Lock()\nCHAT_HISTORY: list[dict] = []\nBRIDGE_SESSION = requests.Session()\n'
if history_anchor not in src:
    raise SystemExit("Host history state anchor missing")
src = src.replace(history_anchor, history_replacement, 1)

route_old = '''def route_chat(text: str, source: str) -> None:\n    result = bridge_post("/llm/chat", {"message": text, "history": []}, timeout=190)\n    reply = str(result.get("reply") or "").strip()\n    if reply:\n        add_event(\n            "assistant",\n            reply,\n            "vex",\n            {\n                "model": result.get("model"),\n                "grounding": result.get("grounding"),\n                "transport": result.get("transport"),\n                "reply_to": source,\n            },\n        )\n    else:\n        err = str(result.get("error") or result.get("error_class") or "PC Brain did not return a reply")\n        add_event("system", f"PC Brain error: {err}", "vex-host", {"reply_to": source})\n\n\n'''
route_new = '''def route_chat(text: str, source: str) -> None:\n    # Send bounded real conversation history to Bridge. The newest user message\n    # stays in the dedicated message field so history contains only prior turns.\n    with LOCK:\n        history = [dict(row) for row in CHAT_HISTORY[-12:]]\n        CHAT_HISTORY.append({"role": "user", "content": str(text)[:4000]})\n        del CHAT_HISTORY[:-12]\n    result = bridge_post("/llm/chat", {"message": text, "history": history}, timeout=190)\n    reply = str(result.get("reply") or "").strip()\n    if reply:\n        with LOCK:\n            CHAT_HISTORY.append({"role": "assistant", "content": reply[:6000]})\n            del CHAT_HISTORY[:-12]\n        add_event(\n            "assistant",\n            reply,\n            "vex",\n            {\n                "model": result.get("model"),\n                "grounding": result.get("grounding"),\n                "transport": result.get("transport"),\n                "reply_to": source,\n            },\n        )\n    else:\n        err = str(result.get("error") or result.get("error_class") or "PC Brain did not return a reply")\n        add_event("system", f"PC Brain error: {err}", "vex-host", {"reply_to": source})\n\n\n'''
if route_old not in src:
    raise SystemExit("Host route_chat history anchor missing")
src = src.replace(route_old, route_new, 1)

button_old = '        ttk.Button(row, text="Ping phone", command=lambda: self.local_event("ping", "Windows ping")).pack(side="left", padx=(8, 0))\n'
button_new = '        ttk.Button(row, text="Ping phone", command=self.ping_phone).pack(side="left", padx=(8, 0))\n'
if button_old not in src:
    raise SystemExit("Ping phone button anchor missing")
src = src.replace(button_old, button_new, 1)

method_anchor = '''    def local_event(self, kind: str, text: str):\n        event = add_event(kind, text, "windows")\n        self.append("Windows", f"[{kind}] {event['text']}")\n\n'''
method_replacement = method_anchor + '''    def ping_phone(self):\n        self.append("Vex Host", "Sending phone ping…")\n\n        def work():\n            ok, detail = send_phone_notification("Ping from Vex Windows Host — PC Brain is online.")\n            if ok:\n                add_event("ping", "Phone ping sent", "windows")\n                self.after(0, lambda: self.append("Vex Host", "Phone ping sent."))\n            else:\n                self.after(0, lambda: self.append("Vex Host", f"Phone ping failed: {detail}"))\n\n        threading.Thread(target=work, daemon=True, name="VexPhonePing").start()\n\n'''
if method_anchor not in src:
    raise SystemExit("local_event method anchor missing")
src = src.replace(method_anchor, method_replacement, 1)

for marker in [
    'VERSION = "0.11.7.40"',
    'REMOTE_SUPPORT_STATE',
    'NTFY_SERVER = "https://ntfy.sh"',
    'def phone_notify_settings(',
    'def send_phone_notification(',
    'CHAT_HISTORY: list[dict] = []',
    'history = [dict(row) for row in CHAT_HISTORY[-12:]]',
    '"history": history',
    'text="Ping phone", command=self.ping_phone',
    'def ping_phone(',
    'text="Copy reply"',
    'bridge_post("/llm/chat"',
]:
    if marker not in src:
        raise SystemExit(f"missing marker: {marker}")

if '{"message": text, "history": []}' in src:
    raise SystemExit("Host still sends empty chat history")

Path("Tools/VexWindowsHost-v11740.py").write_text(src, encoding="utf-8")
compile(src, "Tools/VexWindowsHost-v11740.py", "exec")
print("Built v0.11.7.40 Host with bounded conversation history + phone ping + clipboard support")
