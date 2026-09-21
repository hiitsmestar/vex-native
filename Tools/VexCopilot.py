from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
APPDATA = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
ROOT = LOCALAPPDATA / "VexNative" / "Copilot"
LEDGER = ROOT / "vex-copilot-ledger.jsonl"
VERIFIED = ROOT / "verified-lessons.jsonl"
LATEST = ROOT / "latest.json"
CONFIG = APPDATA / "VexBridge" / "config.json"
ADAPTIVE_DB = APPDATA / "VexBridge" / "adaptive" / "vex-adaptive.sqlite3"
BASE = "http://127.0.0.1:8766"
OLLAMA = "http://127.0.0.1:11434"
FAST_MODEL = "vex-qwen3-4b:latest"
SMART_MODEL = "vex-qwen35-9b:latest"

ROOT.mkdir(parents=True, exist_ok=True)

def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))

def endpoint(path: str) -> str:
    token = str(config().get("token") or "").strip()
    if not token:
        raise RuntimeError("VexBridge token missing")
    sep = "&" if "?" in path else "?"
    return f"{BASE}{path}{sep}token={token}"

def post(path: str, payload: dict[str, Any], timeout: int = 600, retries: int = 1) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last: Exception | None = None
    for attempt in range(max(0, retries) + 1):
        req = urllib.request.Request(endpoint(path), data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code != 503 or attempt >= retries:
                raise
            time.sleep(2.0 + attempt * 3.0)
    raise RuntimeError(f"Bridge request failed: {last}")

def prewarm(tier: str) -> dict[str, Any]:
    model = FAST_MODEL if tier == "fast" else SMART_MODEL if tier == "smart" else ""
    if not model:
        return {"ok": True, "skipped": True}
    body = json.dumps({
        "model": model,
        "prompt": "ready",
        "stream": False,
        "think": False,
        "keep_alive": "20m",
        "options": {"num_ctx": 2048, "num_predict": 1, "temperature": 0.0},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA + "/api/generate", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        payload = json.loads(r.read().decode("utf-8"))
    return {"ok": True, "model": model, "load_seconds": round(float(payload.get("load_duration") or 0) / 1e9, 3)}

def get(path: str, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(endpoint(path), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def install_verified_lesson(task_id: str, cue: str, lesson: str, notes: str) -> int:
    ts = time.time()
    cue_text = ("copilot verified " + str(cue or "").strip())[:900]
    guidance = str(lesson or "").strip()[:5000]
    evidence = (f"externally verified copilot task={task_id}; " + str(notes or "").strip())[:5000]
    if not guidance:
        raise ValueError("verified lesson is empty")
    conn = sqlite3.connect(str(ADAPTIVE_DB), timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            """INSERT INTO lessons
               (created_at, updated_at, kind, cue, guidance, confidence, evidence, active, hits)
               VALUES (?, ?, 'capability', ?, ?, 0.99, ?, 1, 0)
               ON CONFLICT(kind, cue, guidance) DO UPDATE SET
                 updated_at=excluded.updated_at,
                 confidence=0.99,
                 evidence=excluded.evidence,
                 active=1""",
            (ts, ts, cue_text, guidance, evidence),
        )
        row = conn.execute(
            "SELECT id FROM lessons WHERE kind='capability' AND cue=? AND guidance=?",
            (cue_text, guidance),
        ).fetchone()
        conn.commit()
        if not row:
            raise RuntimeError("verified lesson insert could not be confirmed")
        return int(row[0])
    finally:
        conn.close()


def read_ledger() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                out.append(item)
        except Exception:
            pass
    return out


def verified_context(task: str, extra: str = "", limit: int = 6) -> str:
    if not VERIFIED.exists():
        return ""
    import re
    def words(value: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9_.-]+", str(value or "").lower()) if len(w) >= 4}
    target = words(task + " " + extra)
    items = []
    seen_lessons = set()
    for line in VERIFIED.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        lesson = str(obj.get("lesson") or "").strip()
        if not lesson or lesson in seen_lessons:
            continue
        seen_lessons.add(lesson)
        notes = str(obj.get("notes") or "").strip()
        score = len(target & words(lesson + " " + notes))
        items.append((score, str(obj.get("time_utc") or ""), lesson, notes))
    items.sort(key=lambda x: (x[0], x[1]), reverse=True)
    chosen = [x for x in items if x[0] > 0][:limit]
    if not chosen:
        chosen = items[:min(2, limit)]
    if not chosen:
        return ""
    lines = ["EXTERNALLY VERIFIED COPILOT LESSONS"]
    for _, _, lesson, notes in chosen:
        lines.append("- " + lesson)
        if notes:
            lines.append("  Evidence: " + notes)
    return "\n".join(lines)

def find_task(task_id: str) -> dict[str, Any] | None:
    for item in reversed(read_ledger()):
        if item.get("task_id") == task_id and item.get("event") == "ask":
            return item
    return None

def parse_reply(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return {"answer": text, "evidence": [], "confidence": 0.0, "proposed_lesson": "", "action_requests": [], "parse_warning": True}

COPILOT_PERSONA = """You are VexNative operating as a supervised local copilot for ChatGPT and Star.
Use your persistent PC memory and any context genuinely available to you.
Never claim a file, process, tool result, or fact was inspected unless it actually was.
Separate known facts from inference. Mark unknowns plainly.
Do not write lessons or change system state merely because you were asked a question.
Return exactly one JSON object and no markdown."""

def do_ask(args: argparse.Namespace) -> int:
    task_id = f"vc-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    schema = {
        "answer": "concise useful answer",
        "evidence": ["specific evidence actually available to VexNative"],
        "confidence": 0.0,
        "unknowns": ["anything material not verified"],
        "proposed_lesson": "one reusable lesson, or empty string",
        "action_requests": ["optional concrete follow-up actions"],
    }
    trusted = verified_context(args.task, args.context or "")
    task_context = (
        f"COPILOT TASK DETAILS {task_id}\n"
        f"TASK: {args.task}\n"
        f"CONTEXT FROM CHATGPT: {args.context or '(none)'}\n"
        f"REQUESTED TIER: {args.tier}\n"
        + (trusted + "\n" if trusted else "")
        + "Return JSON only using this schema:\n"
        + json.dumps(schema, ensure_ascii=False)
    )
    verified_inline = ("\\nVERIFIED LOCAL STATE:\\n" + trusted) if trusted else ""
    if args.tier == "fast":
        message = f"COPILOT FAST TASK {task_id}. TASK: {args.task}{verified_inline}\\nReturn JSON only."
    elif args.tier == "smart":
        message = f"Use the 9B. COPILOT TASK {task_id}. TASK: {args.task}{verified_inline}\\nReturn JSON only."
    elif args.tier == "deep":
        message = f"Use 35B. COPILOT TASK {task_id}. TASK: {args.task}{verified_inline}\\nReturn JSON only."
    else:
        message = f"COPILOT TASK {task_id}: {args.task}{verified_inline}\\nReturn JSON only."
    copilot_history = []
    if trusted:
        copilot_history.append({
            "role": "assistant",
            "content": ("Externally verified local state for this copilot task:\n" + trusted)[:6000],
        })
    if args.context:
        copilot_history.append({
            "role": "user",
            "content": ("ChatGPT delegation context:\n" + str(args.context))[:3000],
        })
    payload = {
        "message": message[:2400],
        "history": copilot_history[-5:],
        "persona": (COPILOT_PERSONA + "\n\n" + task_context)[:8000],
        "user_profile": "",
        "state": {
            "mode": "supervised-copilot",
            "task_id": task_id,
            "requested_tier": args.tier,
            "learning_policy": "verify-before-commit",
        },
    }
    warm = prewarm(args.tier)
    reply = post("/llm/chat", payload, timeout=args.timeout, retries=1)
    raw = str(reply.get("reply") or "")
    parsed = parse_reply(raw)
    record = {
        "event": "ask",
        "time_utc": now(),
        "task_id": task_id,
        "task": args.task,
        "context": args.context or "",
        "requested_tier": args.tier,
        "prewarm": warm,
        "bridge_model": reply.get("model"),
        "memory": reply.get("memory"),
        "raw_reply": raw,
        "parsed": parsed,
        "verification": "pending",
    }
    append_jsonl(LEDGER, record)
    LATEST.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0

def do_inspect(args: argparse.Namespace) -> int:
    if args.task_id:
        item = find_task(args.task_id)
        if item is None:
            print(json.dumps({"ok": False, "error": "task_not_found", "task_id": args.task_id}, indent=2))
            return 2
        print(json.dumps(item, indent=2, ensure_ascii=False))
        return 0
    if LATEST.exists():
        print(LATEST.read_text(encoding="utf-8"))
        return 0
    print(json.dumps({"ok": True, "detail": "no copilot tasks yet"}, indent=2))
    return 0

def feedback_exchange(task_id: str, status: str, lesson: str, notes: str) -> dict[str, Any]:
    message = (
        f"COPILOT VERIFIED FEEDBACK {task_id}\n"
        f"VERDICT: {status}\n"
        f"REUSABLE LESSON: {lesson}\n"
        f"VERIFICATION NOTES: {notes or '(none)'}\n"
        "This feedback has been externally checked. Treat the reusable lesson as guidance, "
        "not as permission to invent facts. Reply with exactly COPILOT_FEEDBACK_ACK."
    )
    return post("/llm/chat", {
        "message": message[:5000],
        "history": [],
        "persona": COPILOT_PERSONA,
        "user_profile": "",
        "state": {"mode": "copilot-feedback", "task_id": task_id, "verification": status},
    }, timeout=600)

def do_verify(args: argparse.Namespace) -> int:
    original = find_task(args.task_id)
    if original is None:
        print(json.dumps({"ok": False, "error": "task_not_found", "task_id": args.task_id}, indent=2))
        return 2
    proposed = str((original.get("parsed") or {}).get("proposed_lesson") or "").strip()
    lesson = str(args.lesson or proposed).strip()
    if not lesson:
        print(json.dumps({"ok": False, "error": "verified_lesson_required"}, indent=2))
        return 2
    lesson_id = install_verified_lesson(
        args.task_id,
        str(original.get("task") or ""),
        lesson,
        args.notes or "",
    )
    item = {
        "event": "verify",
        "time_utc": now(),
        "task_id": args.task_id,
        "lesson": lesson,
        "notes": args.notes or "",
        "adaptive_lesson_id": lesson_id,
        "feedback_model": "deterministic-verified-copilot",
        "feedback_ack": "COPILOT_VERIFIED_LESSON_INSTALLED",
    }
    append_jsonl(LEDGER, item)
    append_jsonl(VERIFIED, item)
    item["adaptive_run"] = {
        "ok": True,
        "skipped": True,
        "reason": "externally verified lesson installed deterministically; full adaptive review not forced"
    }
    LATEST.write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(item, indent=2, ensure_ascii=False))
    return 0

def do_reject(args: argparse.Namespace) -> int:
    original = find_task(args.task_id)
    if original is None:
        print(json.dumps({"ok": False, "error": "task_not_found", "task_id": args.task_id}, indent=2))
        return 2
    reason = str(args.reason or "result was not verified").strip()
    ack = feedback_exchange(args.task_id, "rejected", f"Do not reuse the rejected result. Failure mode: {reason}", args.notes or "")
    item = {
        "event": "reject",
        "time_utc": now(),
        "task_id": args.task_id,
        "reason": reason,
        "notes": args.notes or "",
        "feedback_model": ack.get("model"),
        "feedback_ack": ack.get("reply"),
    }
    append_jsonl(LEDGER, item)
    LATEST.write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(item, indent=2, ensure_ascii=False))
    return 0

def do_status(_: argparse.Namespace) -> int:
    asks = sum(1 for x in read_ledger() if x.get("event") == "ask")
    verified = sum(1 for x in read_ledger() if x.get("event") == "verify")
    rejected = sum(1 for x in read_ledger() if x.get("event") == "reject")
    out = {"ok": True, "root": str(ROOT), "asks": asks, "verified": verified, "rejected": rejected}
    for name, path in (("adaptive", "/adaptive/status"), ("memory", "/memory/status"), ("bridge", "/status")):
        try:
            out[name] = get(path)
        except Exception as exc:
            out[name] = {"ok": False, "error": exc.__class__.__name__}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0

def main() -> int:
    p = argparse.ArgumentParser(description="Supervised ChatGPT <-> VexNative copilot bridge")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("ask")
    a.add_argument("task")
    a.add_argument("--context", default="")
    a.add_argument("--tier", choices=("auto", "fast", "smart", "deep"), default="auto")
    a.add_argument("--timeout", type=int, default=600)
    a.set_defaults(func=do_ask)

    i = sub.add_parser("inspect")
    i.add_argument("--task-id", default="")
    i.set_defaults(func=do_inspect)

    v = sub.add_parser("verify")
    v.add_argument("task_id")
    v.add_argument("--lesson", default="")
    v.add_argument("--notes", default="")
    v.set_defaults(func=do_verify)

    r = sub.add_parser("reject")
    r.add_argument("task_id")
    r.add_argument("--reason", default="")
    r.add_argument("--notes", default="")
    r.set_defaults(func=do_reject)

    s = sub.add_parser("status")
    s.set_defaults(func=do_status)

    args = p.parse_args()
    return int(args.func(args))

if __name__ == "__main__":
    raise SystemExit(main())