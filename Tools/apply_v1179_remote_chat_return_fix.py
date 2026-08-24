#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")
bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")

if '"version": "0.11.7.6"' not in bridge:
    raise SystemExit("v0.11.7.9 expected Bridge v0.11.7.6 source")
if 'VERSION = "0.11.7.7"' not in remote:
    raise SystemExit("v0.11.7.9 expected Remote Support v0.11.7.7 source")

helper_anchor = '\n\ndef _ollama_models() -> list[str]:\n'
helper = r'''

def _remote_partner_chat(message: str) -> tuple[str, str] | None:
    """Small, bounded cognition path reserved for Remote Support.

    This deliberately bypasses the normal foreground memory/research pipeline so a
    wedged retrieval worker cannot prevent a technical relay reply.
    """
    model = _choose_ollama_model()
    if not model:
        return None
    prompt = str(message or "").strip()[:5000]
    if not prompt:
        return None
    try:
        import requests
        response = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are Vex inside VexNative answering the remote technical partner. "
                            "Answer only the technical/project question. Be concise and factual. "
                            "Do not expose private personal memory, addresses, secrets, tokens, local paths, or private chat content."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.55,
                    "top_p": 0.9,
                    "num_ctx": 4096,
                    "num_predict": 320,
                    "repeat_penalty": 1.08,
                },
            },
            timeout=(3.0, 70.0),
        )
        response.raise_for_status()
        payload = response.json()
        raw = str(((payload.get("message") or {}).get("content")) or "")
        reply = _strip_reasoning_markup(raw)
        if not reply:
            return None
        return reply[:6000], model
    except Exception as exc:
        print(f"[remote-chat] bounded Ollama call failed: {exc.__class__.__name__}", flush=True)
        return None
'''

if helper_anchor not in bridge:
    raise SystemExit("v0.11.7.9 Bridge Ollama helper anchor missing")
bridge = bridge.replace(helper_anchor, helper + helper_anchor, 1)

post_anchor = '        if parsed.path == "/llm/chat":\n'
route = r'''        if parsed.path == "/llm/remote-chat":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 32_000:
                    self._json(413, {"ok": False, "error": "remote chat payload too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                message = str(payload.get("message") or "").strip()
                if not message:
                    self._json(400, {"ok": False, "error": "remote chat message required"})
                    return
                result = _remote_partner_chat(message)
                if result is None:
                    self._json(503, {"ok": False, "error": "remote cognition unavailable"})
                    return
                reply, model = result
                self._json(200, {
                    "ok": True,
                    "reply": reply,
                    "model": model,
                    "grounding": "remote-technical-direct-v1179",
                })
            except Exception as exc:
                self._json(500, {"ok": False, "error": f"remote cognition failed: {exc.__class__.__name__}"})
            return

'''
if post_anchor not in bridge:
    raise SystemExit("v0.11.7.9 Bridge /llm/chat route anchor missing")
bridge = bridge.replace(post_anchor, route + post_anchor, 1)
bridge = bridge.replace('"version": "0.11.7.6"', '"version": "0.11.7.9"')

old_call = 'result = bridge_post("/llm/chat", {"message": marked_prompt, "history": []}, timeout=190)'
new_call = 'result = bridge_post("/llm/remote-chat", {"message": marked_prompt}, timeout=85)'
if old_call not in remote:
    raise SystemExit("v0.11.7.9 Remote Support chat call anchor missing")
remote = remote.replace(old_call, new_call, 1)
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.9"', remote, count=1, flags=re.M)

BRIDGE.write_text(bridge, encoding="utf-8")
REMOTE.write_text(remote, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(remote, str(REMOTE), "exec")

checks = [
    '"version": "0.11.7.9"',
    'parsed.path == "/llm/remote-chat"',
    'def _remote_partner_chat(',
    '"grounding": "remote-technical-direct-v1179"',
    'timeout=(3.0, 70.0)',
]
for marker in checks:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.9 Bridge verifier missing: {marker}")
for marker in ['VERSION = "0.11.7.9"', 'bridge_post("/llm/remote-chat"', 'timeout=85']:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.9 Remote Support verifier missing: {marker}")

print("Applied v0.11.7.9 dedicated bounded remote-chat return path")
