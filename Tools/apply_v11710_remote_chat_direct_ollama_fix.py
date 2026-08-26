#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.7"' not in remote:
    raise SystemExit("v0.11.7.10 expected Remote Support v0.11.7.7 source")

anchor = 'def remote_chat_public(command: dict) -> dict:\n'
start = remote.find(anchor)
if start < 0:
    raise SystemExit("v0.11.7.10 remote_chat_public anchor missing")
end = remote.find('\n\ndef run_remote_chat_command(', start)
if end < 0:
    raise SystemExit("v0.11.7.10 remote_chat_public end missing")

replacement = r'''def remote_chat_public(command: dict) -> dict:
    prompt = str(command.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "remote chat prompt is required"}
    if len(prompt) > REMOTE_CHAT_MAX_PROMPT:
        return {"ok": False, "error": f"remote chat prompt exceeds {REMOTE_CHAT_MAX_PROMPT} characters"}
    if not remote_chat_topic_ok(prompt):
        return {"ok": False, "error": "remote chat accepts technical/project prompts only; private or personal chat must not use the public GitHub relay"}

    marked_prompt = (
        "REMOTE TECHNICAL PARTNER MESSAGE\n"
        "This message arrived through Vex Remote Support from the remote technical partner, not from Star. "
        "Treat it as a VexNative/project debugging or research conversation. Do not attribute this message to Star. "
        "Do not expose private personal-memory facts, saved biography, addresses, secrets, tokens, local paths, or private chat content. "
        "Answer the technical/project question directly and ground claims in current runtime state when available.\n\n"
        + prompt
    )

    # v0.11.7.10 deliberately talks to the local Ollama service directly.
    # Remote Support and Ollama are on the same PC; nothing is exposed to LAN/GitHub.
    # This bypasses a wedged Bridge HTTP/TLS request path while preserving Bridge for the phone.
    try:
        tags = requests.get("http://127.0.0.1:11434/api/tags", timeout=(2.0, 4.0))
        tags.raise_for_status()
        models = []
        for item in (tags.json().get("models") or []):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                models.append(name)
        if not models:
            return {"ok": False, "error_class": "NoLocalModel", "source": "remote-technical-partner"}
        preferred = ["vex-qwen3-4b:latest", "qwen3:4b", "qwen3:8b", "gemma3:4b", "llama3.2:3b"]
        lower_map = {name.lower(): name for name in models}
        model = next((lower_map[p.lower()] for p in preferred if p.lower() in lower_map), None)
        if not model:
            model = next((name for name in models if any(f in name.lower() for f in ("qwen", "gemma", "llama"))), models[0])

        response = requests.post(
            "http://127.0.0.1:11434/api/chat",
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
                    {"role": "user", "content": marked_prompt[:5000]},
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
            timeout=(3.0, 75.0),
        )
        response.raise_for_status()
        payload = response.json()
        raw = str(((payload.get("message") or {}).get("content")) or "").strip()
        reply = re.sub(r"<think>[\\s\\S]*?</think>", "", raw, flags=re.I).strip()
        reply = re.sub(r"^\\s*(?:assistant|vex)\\s*:\\s*", "", reply, flags=re.I).strip()
        return {
            "ok": bool(reply),
            "reply": reply[:REMOTE_CHAT_MAX_REPLY],
            "model": model_label(model),
            "grounding": "remote-technical-direct-ollama-v11710",
            "http_status": int(response.status_code),
            "truncated": len(reply) > REMOTE_CHAT_MAX_REPLY,
            "source": "remote-technical-partner",
            "error_class": None if reply else "EmptyReply",
        }
    except Exception as exc:
        return {
            "ok": False,
            "reply": "",
            "model": None,
            "grounding": "remote-technical-direct-ollama-v11710",
            "http_status": 0,
            "truncated": False,
            "source": "remote-technical-partner",
            "error_class": exc.__class__.__name__,
        }
'''

remote = remote[:start] + replacement + remote[end:]
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.10"', remote, count=1, flags=re.M)

REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")

for marker in [
    'VERSION = "0.11.7.10"',
    'http://127.0.0.1:11434/api/chat',
    'remote-technical-direct-ollama-v11710',
    '"command_accepted"',
    'for page in range(1, 101)',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.10 verifier missing: {marker}")

print("Applied v0.11.7.10 direct local-Ollama remote chat fix")
