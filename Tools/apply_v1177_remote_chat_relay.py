#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


REMOTE_PATH = Path("Tools/VexRemoteSupport.py")
remote = REMOTE_PATH.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.5"' not in remote:
    raise SystemExit("v0.11.7.7 expected v0.11.7.5 Remote Support source")

remote = re.sub(
    r'^VERSION = "[^"]+"',
    'VERSION = "0.11.7.7"',
    remote,
    count=1,
    flags=re.M,
)

constants_anchor = 'SESSION_SECONDS = 2 * 60 * 60\n'
constants = '''SESSION_SECONDS = 2 * 60 * 60
REMOTE_CHAT_MAX_PROMPT = 4000
REMOTE_CHAT_MAX_REPLY = 6000
'''
if constants_anchor not in remote:
    raise SystemExit("v0.11.7.7 session constants anchor missing")
remote = remote.replace(constants_anchor, constants, 1)

execute_anchor = 'def execute_command(command: dict, allow_maintenance: bool) -> dict:\n'
helpers = r'''REMOTE_CHAT_TERMS = {
    "vexnative", "vexbridge", "bridge", "remote support", "learning", "adaptive", "autonomy", "initiative",
    "memory worker", "memory retrieval", "cognition", "ollama", "qwen", "model", "prompt", "context",
    "routing", "router", "debug", "debugging", "error", "failure", "timeout", "latency", "performance",
    "python", "swift", "swiftui", "windows", "powershell", "github", "api", "http", "https", "tls",
    "json", "sqlite", "database", "software", "code", "coding", "programming", "architecture", "testing",
    "test", "worker", "service", "process", "thread", "concurrency", "queue", "research", "tool", "tools",
    "index", "search", "art worker", "comfyui", "self learning", "self-learning", "self improvement",
    "self-improvement", "natural conversation", "naturalness", "conversation behavior", "persona consistency",
}


def remote_chat_topic_ok(prompt: str) -> bool:
    low = re.sub(r"\s+", " ", str(prompt or "").lower()).strip()
    if not low or len(low) > REMOTE_CHAT_MAX_PROMPT:
        return False
    return technical_topic(low) or any(term in low for term in REMOTE_CHAT_TERMS)


def remote_chat_public(command: dict) -> dict:
    prompt = str(command.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "remote chat prompt is required"}
    if len(prompt) > REMOTE_CHAT_MAX_PROMPT:
        return {"ok": False, "error": f"remote chat prompt exceeds {REMOTE_CHAT_MAX_PROMPT} characters"}
    if not remote_chat_topic_ok(prompt):
        return {
            "ok": False,
            "error": "remote chat accepts technical/project prompts only; private or personal chat must not use the public GitHub relay",
        }

    marked_prompt = (
        "REMOTE TECHNICAL PARTNER MESSAGE\n"
        "This message arrived through Vex Remote Support from the remote technical partner, not from Star. "
        "Treat it as a VexNative/project debugging or research conversation. Do not attribute this message to Star. "
        "Do not expose private personal-memory facts, saved biography, addresses, secrets, tokens, local paths, or private chat content. "
        "Answer the technical/project question directly and ground claims in your current runtime state when available.\n\n"
        + prompt
    )
    result = bridge_post(
        "/llm/chat",
        {"message": marked_prompt, "history": []},
        timeout=190,
    )
    reply = str(result.get("reply") or "").strip()
    clipped = reply[:REMOTE_CHAT_MAX_REPLY]
    return {
        "ok": yes(result.get("ok")) and bool(reply),
        "reply": clipped,
        "model": model_label(result.get("model")),
        "grounding": str(result.get("grounding") or "")[:80] or None,
        "http_status": integer(result.get("http_status")),
        "truncated": len(reply) > REMOTE_CHAT_MAX_REPLY,
        "source": "remote-technical-partner",
        "error_class": str(result.get("error") or "")[:120] if result.get("error") else None,
    }


def run_remote_chat_command(command: dict, command_id: str, allow_maintenance: bool) -> None:
    """Run model-backed chat off the polling thread so a slow model cannot freeze support."""
    try:
        result = execute_command(command, allow_maintenance=allow_maintenance)
    except Exception as exc:
        result = {"remote_chat": {"ok": False, "error_class": exc.__class__.__name__, "source": "remote-technical-partner"}}
    try:
        post_comment("command_result", {"command_id": command_id, "action": "remote_chat", "result": result})
    except Exception:
        pass


'''
if execute_anchor not in remote:
    raise SystemExit("v0.11.7.7 execute_command anchor missing")
remote = remote.replace(execute_anchor, helpers + execute_anchor, 1)

status_anchor = '''    if action == "status":
        return collect_snapshot(include_doctor=False)
'''
chat_action = status_anchor + '''    if action == "remote_chat":
        return {"remote_chat": remote_chat_public(command)}
'''
if status_anchor not in remote:
    raise SystemExit("v0.11.7.7 status action anchor missing")
remote = remote.replace(status_anchor, chat_action, 1)

loop_anchor = '''                    self.on_status(f"Running {str(command.get('action') or 'command')}…")
                    result = execute_command(command, allow_maintenance=bool(self.allow_maintenance()))
                    post_comment("command_result", {"command_id": command_id, "action": str(command.get("action") or "")[:80], "result": result})
                    self.on_status("Support session is active")
'''
loop_replacement = '''                    action = str(command.get("action") or "").strip().lower()
                    self.on_status(f"Running {action or 'command'}…")
                    if action == "remote_chat":
                        threading.Thread(
                            target=run_remote_chat_command,
                            args=(command, command_id, bool(self.allow_maintenance())),
                            daemon=True,
                            name=f"VexRemoteChat-{command_id[:24]}",
                        ).start()
                        post_comment("command_accepted", {"command_id": command_id, "action": "remote_chat", "status": "running"})
                        self.on_status("Remote chat running; support session remains active")
                        continue
                    result = execute_command(command, allow_maintenance=bool(self.allow_maintenance()))
                    post_comment("command_result", {"command_id": command_id, "action": action[:80], "result": result})
                    self.on_status("Support session is active")
'''
if loop_anchor not in remote:
    raise SystemExit("v0.11.7.7 command-loop anchor missing")
remote = remote.replace(loop_anchor, loop_replacement, 1)

REMOTE_PATH.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE_PATH), "exec")

checks = [
    'VERSION = "0.11.7.7"',
    "REMOTE_CHAT_MAX_PROMPT = 4000",
    "REMOTE_CHAT_MAX_REPLY = 6000",
    "def remote_chat_topic_ok(",
    "def remote_chat_public(",
    "def run_remote_chat_command(",
    'action == "remote_chat"',
    'bridge_post(\n        "/llm/chat"',
    '"history": []',
    "REMOTE TECHNICAL PARTNER MESSAGE",
    "not from Star",
    "private or personal chat must not use the public GitHub relay",
    '"command_accepted"',
    "Remote chat running; support session remains active",
    "for page in range(1, 101)",
    'action == "memory_status"',
    "session remains active",
]
final = REMOTE_PATH.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"v0.11.7.7 Remote Support verifier missing: {marker}")

print("Applied v0.11.7.7 bounded non-blocking remote technical chat relay")
