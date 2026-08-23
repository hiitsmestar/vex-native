#!/usr/bin/env python3
"""VexMemoryWorker v0.11.0

Lightweight local-only persistent memory service for VexNative.

Design goals:
- Keep long-term personal history on the PC instead of stuffing it into the LLM prompt.
- Retrieve only a small relevant slice for each turn.
- Keep authoritative memories separate from raw conversation history.
- Preserve provenance so model-generated text never silently becomes a fact.
- Stay local: loopback HTTP + SQLite, no paid API or cloud dependency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

VERSION = "0.11.0"
HOST = "127.0.0.1"
DEFAULT_PORT = 8766
MAX_BODY_BYTES = 16 * 1024 * 1024


def _data_root() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
    else:
        base = Path.home() / ".local" / "share"
    root = base / "VexNative" / "Memory"
    root.mkdir(parents=True, exist_ok=True)
    return root


ROOT = _data_root()
DB_PATH = ROOT / "vex-memory.sqlite3"
LOG_PATH = ROOT / "memory-worker.log"


def _bundle_dir() -> Path:
    # PyInstaller one-file apps run from a temp extraction directory, but sys.executable
    # points at the actual installed EXE beside optional private seed files.
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def _now() -> float:
    return time.time()


def _clean(value: Any, limit: int = 12000) -> str:
    text = str(value or "").replace("\x00", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _hash(*parts: Any) -> str:
    joined = "\x1f".join(_clean(part, 50000) for part in parts)
    return hashlib.sha256(joined.encode("utf-8", "ignore")).hexdigest()


def _timestamp(value: Any, fallback: float | None = None) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if text:
        # Swift's ISO-8601 JSON encoder normally emits ...Z. Keep this parser tiny.
        try:
            from datetime import datetime
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    return _now() if fallback is None else fallback


def _log(message: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass
    print(message, flush=True)


class MemoryDB:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.fts_available = False
        self._setup()

    def _setup(self) -> None:
        with self.lock:
            c = self.conn
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA busy_timeout=5000")
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    canonical_key TEXT UNIQUE NOT NULL,
                    subject TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL DEFAULT 'note',
                    text TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL DEFAULT 'unknown',
                    source_ref TEXT NOT NULL DEFAULT '',
                    authority INTEGER NOT NULL DEFAULT 50,
                    confidence REAL NOT NULL DEFAULT 0.70,
                    importance REAL NOT NULL DEFAULT 0.65,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_memories_active_kind ON memories(active, kind);
                CREATE INDEX IF NOT EXISTS idx_memories_subject ON memories(subject);
                CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at DESC);

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL DEFAULT 'vexnative',
                    ordinal INTEGER NOT NULL DEFAULT 0,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    source TEXT NOT NULL DEFAULT 'vexnative-iphone'
                );
                CREATE INDEX IF NOT EXISTS idx_chat_thread_ordinal ON chat_messages(thread_id, ordinal);
                CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at DESC);

                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL DEFAULT 'vexnative',
                    ordinal INTEGER NOT NULL DEFAULT 0,
                    text TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    source TEXT NOT NULL DEFAULT 'vexnative-iphone'
                );
                CREATE INDEX IF NOT EXISTS idx_episode_thread_ordinal ON episodes(thread_id, ordinal);
                CREATE INDEX IF NOT EXISTS idx_episode_created ON episodes(created_at DESC);

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            try:
                c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(memory_id UNINDEXED, text, tags, subject, tokenize='unicode61')")
                c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(episode_id UNINDEXED, text, tokenize='unicode61')")
                self.fts_available = True
            except sqlite3.OperationalError:
                self.fts_available = False
            c.commit()

    def _sync_memory_fts(self, memory_id: str, text: str, tags: str, subject: str) -> None:
        if not self.fts_available:
            return
        self.conn.execute("DELETE FROM memories_fts WHERE memory_id = ?", (memory_id,))
        self.conn.execute(
            "INSERT INTO memories_fts(memory_id, text, tags, subject) VALUES(?,?,?,?)",
            (memory_id, text, tags, subject),
        )

    def _sync_episode_fts(self, episode_id: str, text: str) -> None:
        if not self.fts_available:
            return
        self.conn.execute("DELETE FROM episodes_fts WHERE episode_id = ?", (episode_id,))
        self.conn.execute("INSERT INTO episodes_fts(episode_id, text) VALUES(?,?)", (episode_id, text))

    def set_meta(self, key: str, value: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        with self.lock:
            row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return str(row[0]) if row else None

    def upsert_memory(self, item: dict[str, Any], default_source: str = "import") -> bool:
        text = _clean(item.get("text"), 24000)
        if not text:
            return False
        subject = _clean(item.get("subject"), 200).lower()
        kind = _clean(item.get("kind"), 80).lower() or "note"
        tags_value = item.get("tags")
        if isinstance(tags_value, list):
            tags = " ".join(_clean(v, 120) for v in tags_value if _clean(v, 120))
        else:
            tags = _clean(tags_value, 1000)
        source_type = _clean(item.get("source_type") or item.get("source") or default_source, 120)
        source_ref = _clean(item.get("source_ref"), 500)
        canonical_key = _clean(item.get("canonical_key"), 500)
        if not canonical_key:
            canonical_key = "mem:" + _hash(subject, kind, text)
        memory_id = _clean(item.get("id"), 200) or _hash(canonical_key)[:32]
        authority = max(0, min(100, int(item.get("authority") or 60)))
        confidence = max(0.0, min(1.0, float(item.get("confidence") if item.get("confidence") is not None else 0.78)))
        importance = max(0.0, min(1.0, float(item.get("importance") if item.get("importance") is not None else 0.72)))
        created_at = _timestamp(item.get("created_at"))
        updated_at = _timestamp(item.get("updated_at"), created_at)

        with self.lock:
            existing = self.conn.execute(
                "SELECT * FROM memories WHERE canonical_key=?", (canonical_key,)
            ).fetchone()
            if existing:
                # Newer/higher-authority evidence wins. This is what lets explicit
                # corrections replace stale descriptions without deleting history.
                should_replace = (
                    authority > int(existing["authority"])
                    or updated_at >= float(existing["updated_at"])
                    or confidence > float(existing["confidence"]) + 0.08
                )
                if should_replace:
                    memory_id = str(existing["id"])
                    self.conn.execute(
                        """
                        UPDATE memories SET subject=?, kind=?, text=?, tags=?, source_type=?, source_ref=?,
                            authority=?, confidence=?, importance=?, updated_at=?, active=1
                        WHERE id=?
                        """,
                        (
                            subject, kind, text, tags, source_type, source_ref,
                            authority, confidence, importance, updated_at, memory_id,
                        ),
                    )
                    self._sync_memory_fts(memory_id, text, tags, subject)
                    self.conn.commit()
                return should_replace

            self.conn.execute(
                """
                INSERT INTO memories(
                    id, canonical_key, subject, kind, text, tags, source_type, source_ref,
                    authority, confidence, importance, created_at, updated_at, active
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                (
                    memory_id, canonical_key, subject, kind, text, tags, source_type, source_ref,
                    authority, confidence, importance, created_at, updated_at,
                ),
            )
            self._sync_memory_fts(memory_id, text, tags, subject)
            self.conn.commit()
            return True

    def _upsert_chat_message(self, item: dict[str, Any], ordinal: int, thread_id: str, source: str) -> bool:
        role = _clean(item.get("role"), 40).lower()
        content = _clean(item.get("content"), 50000)
        if role not in {"user", "assistant"} or not content:
            return False
        created_at = _timestamp(item.get("createdAt") or item.get("created_at"))
        message_id = _clean(item.get("id"), 200) or _hash(thread_id, ordinal, role, content, created_at)[:32]
        with self.lock:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO chat_messages(id,thread_id,ordinal,role,content,created_at,source) VALUES(?,?,?,?,?,?,?)",
                (message_id, thread_id, ordinal, role, content, created_at, source),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def sync_messages(self, messages: list[Any], thread_id: str = "vexnative", source: str = "vexnative-iphone", start_ordinal: int = 0) -> int:
        added = 0
        normalized: list[dict[str, Any]] = []
        for offset, raw in enumerate(messages):
            if not isinstance(raw, dict):
                continue
            ordinal = int(raw.get("ordinal") if raw.get("ordinal") is not None else start_ordinal + offset)
            item = dict(raw)
            if self._upsert_chat_message(item, ordinal, thread_id, source):
                added += 1
            role = _clean(item.get("role"), 40).lower()
            content = _clean(item.get("content"), 50000)
            if role in {"user", "assistant"} and content:
                normalized.append({"role": role, "content": content, "ordinal": ordinal, "created_at": _timestamp(item.get("createdAt") or item.get("created_at"))})

        # Build compact user/assistant episodes for retrieval. Raw messages remain in
        # chat_messages for complete history/export.
        i = 0
        while i < len(normalized):
            first = normalized[i]
            parts = []
            if first["role"] == "user":
                parts.append("Star: " + first["content"])
            else:
                parts.append("Vex: " + first["content"])
            last = first
            if i + 1 < len(normalized) and first["role"] == "user" and normalized[i + 1]["role"] == "assistant":
                last = normalized[i + 1]
                parts.append("Vex: " + last["content"])
                i += 1
            episode_text = "\n".join(parts)
            episode_id = _hash(thread_id, first["ordinal"], last["ordinal"], episode_text)[:32]
            with self.lock:
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO episodes(id,thread_id,ordinal,text,created_at,source) VALUES(?,?,?,?,?,?)",
                    (episode_id, thread_id, int(first["ordinal"]), episode_text, float(first["created_at"]), source),
                )
                if cur.rowcount > 0:
                    self._sync_episode_fts(episode_id, episode_text)
                self.conn.commit()
            i += 1
        return added

    def sync_profile(self, payload: dict[str, Any], source: str = "vexnative-iphone") -> dict[str, int]:
        profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else payload
        counts = {"memories": 0, "messages": 0}

        persona = _clean(profile.get("persona"), 24000)
        if persona:
            counts["memories"] += int(self.upsert_memory({
                "canonical_key": "core:vex:persona",
                "subject": "vex",
                "kind": "persona",
                "text": persona,
                "source_type": source,
                "authority": 100,
                "confidence": 1.0,
                "importance": 1.0,
            }, source))

        user_profile = _clean(profile.get("userProfile") or profile.get("user_profile"), 24000)
        if user_profile:
            counts["memories"] += int(self.upsert_memory({
                "canonical_key": "core:star:profile",
                "subject": "star",
                "kind": "profile",
                "text": user_profile,
                "source_type": source,
                "authority": 100,
                "confidence": 1.0,
                "importance": 1.0,
            }, source))

        state = profile.get("state") if isinstance(profile.get("state"), dict) else {}
        for field in ("mood", "outfit", "location", "scene"):
            value = _clean(state.get(field), 12000)
            if value:
                counts["memories"] += int(self.upsert_memory({
                    "canonical_key": f"current:vex:{field}",
                    "subject": "vex",
                    "kind": "state",
                    "text": f"Current Vex {field}: {value}",
                    "tags": ["current", "state", field],
                    "source_type": source,
                    "authority": 98,
                    "confidence": 0.99,
                    "importance": 0.95,
                    "updated_at": _now(),
                }, source))

        for raw in profile.get("memories") or []:
            if isinstance(raw, str):
                item = {"text": raw, "kind": "note"}
            elif isinstance(raw, dict):
                item = dict(raw)
            else:
                continue
            text = _clean(item.get("text"), 24000)
            if not text:
                continue
            ident = _clean(item.get("id"), 200)
            item.update({
                "canonical_key": "iphone-memory:" + (ident or _hash(text)),
                "source_type": _clean(item.get("source"), 120) or source,
                "authority": 92 if str(item.get("kind") or "").lower() in {"rule", "lesson"} else 82,
                "confidence": item.get("confidence") if item.get("confidence") is not None else 0.84,
                "importance": item.get("importance") if item.get("importance") is not None else 0.78,
            })
            counts["memories"] += int(self.upsert_memory(item, source))

        for rule in profile.get("semanticRules") or profile.get("semantic_rules") or []:
            text = _clean(rule, 12000)
            if not text:
                continue
            counts["memories"] += int(self.upsert_memory({
                "canonical_key": "iphone-rule:" + _hash(text),
                "subject": "vex-star",
                "kind": "rule",
                "text": text,
                "tags": ["rule", "relationship", "behavior"],
                "source_type": source,
                "authority": 97,
                "confidence": 0.98,
                "importance": 0.98,
            }, source))

        for example in profile.get("examples") or []:
            if not isinstance(example, dict):
                continue
            user = _clean(example.get("user"), 8000)
            assistant = _clean(example.get("assistant"), 8000)
            if not user or not assistant:
                continue
            lesson = f"Teaching example — Star: {user} | Vex: {assistant}"
            counts["memories"] += int(self.upsert_memory({
                "canonical_key": "iphone-example:" + _hash(lesson),
                "subject": "vex-star",
                "kind": "lesson",
                "text": lesson,
                "tags": example.get("tags") or [],
                "source_type": source,
                "authority": 88,
                "confidence": 0.90,
                "importance": max(0.65, min(1.0, float(example.get("weight") or 0.85))),
            }, source))

        messages = payload.get("messages") if isinstance(payload.get("messages"), list) else profile.get("messages")
        if isinstance(messages, list):
            counts["messages"] = self.sync_messages(
                messages,
                thread_id=_clean(payload.get("thread_id"), 200) or "vexnative",
                source=source,
                start_ordinal=int(payload.get("start_ordinal") or 0),
            )
        return counts

    def import_seed(self, payload: dict[str, Any], source: str = "private-seed") -> dict[str, int]:
        counts = {"memories": 0, "messages": 0}
        for item in payload.get("memories") or []:
            if isinstance(item, str):
                item = {"text": item}
            if isinstance(item, dict):
                counts["memories"] += int(self.upsert_memory(item, source))
        messages = payload.get("messages") or []
        if isinstance(messages, list):
            counts["messages"] = self.sync_messages(
                messages,
                thread_id=_clean(payload.get("thread_id"), 200) or "chatgpt-continuity",
                source=source,
                start_ordinal=int(payload.get("start_ordinal") or 0),
            )
        return counts

    @staticmethod
    def _fts_query(query: str) -> str:
        tokens = [t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9_'-]{1,}", query.lower()) if len(t) > 1]
        stop = {"the", "and", "for", "with", "that", "this", "what", "who", "are", "you", "your", "about", "right", "now"}
        tokens = [t for t in tokens if t not in stop][:18]
        return " OR ".join('"' + t.replace('"', '') + '"' for t in tokens)

    def search(self, query: str, memory_limit: int = 8, episode_limit: int = 4) -> dict[str, Any]:
        query = _clean(query, 5000)
        memories: list[dict[str, Any]] = []
        episodes: list[dict[str, Any]] = []
        fts_query = self._fts_query(query)
        with self.lock:
            if self.fts_available and fts_query:
                rows = self.conn.execute(
                    """
                    SELECT m.*, bm25(memories_fts) AS fts_rank
                    FROM memories_fts JOIN memories m ON m.id = memories_fts.memory_id
                    WHERE memories_fts MATCH ? AND m.active=1
                    ORDER BY (bm25(memories_fts) - (m.importance * 1.7) - (m.confidence * 1.2) - (m.authority / 100.0)) ASC,
                             m.updated_at DESC
                    LIMIT ?
                    """,
                    (fts_query, max(1, min(30, memory_limit))),
                ).fetchall()
            else:
                like = "%" + (query[:160] or " ") + "%"
                rows = self.conn.execute(
                    """
                    SELECT *, 0 AS fts_rank FROM memories
                    WHERE active=1 AND (text LIKE ? OR tags LIKE ? OR subject LIKE ?)
                    ORDER BY importance DESC, confidence DESC, authority DESC, updated_at DESC LIMIT ?
                    """,
                    (like, like, like, max(1, min(30, memory_limit))),
                ).fetchall()
            for row in rows:
                memories.append({
                    "id": row["id"],
                    "subject": row["subject"],
                    "kind": row["kind"],
                    "text": row["text"],
                    "tags": row["tags"],
                    "source_type": row["source_type"],
                    "source_ref": row["source_ref"],
                    "authority": row["authority"],
                    "confidence": row["confidence"],
                    "importance": row["importance"],
                    "updated_at": row["updated_at"],
                })

            if self.fts_available and fts_query:
                erows = self.conn.execute(
                    """
                    SELECT e.*, bm25(episodes_fts) AS fts_rank
                    FROM episodes_fts JOIN episodes e ON e.id = episodes_fts.episode_id
                    WHERE episodes_fts MATCH ?
                    ORDER BY bm25(episodes_fts) ASC, e.created_at DESC LIMIT ?
                    """,
                    (fts_query, max(0, min(20, episode_limit))),
                ).fetchall()
            else:
                like = "%" + (query[:160] or " ") + "%"
                erows = self.conn.execute(
                    "SELECT * FROM episodes WHERE text LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (like, max(0, min(20, episode_limit))),
                ).fetchall()
            for row in erows:
                episodes.append({
                    "id": row["id"],
                    "text": row["text"],
                    "created_at": row["created_at"],
                    "source": row["source"],
                    "thread_id": row["thread_id"],
                })
        return {"memories": memories, "episodes": episodes}

    def stats(self) -> dict[str, Any]:
        with self.lock:
            memory_count = int(self.conn.execute("SELECT COUNT(*) FROM memories WHERE active=1").fetchone()[0])
            message_count = int(self.conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0])
            episode_count = int(self.conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0])
        try:
            db_bytes = self.path.stat().st_size
        except Exception:
            db_bytes = 0
        return {
            "memories": memory_count,
            "messages": message_count,
            "episodes": episode_count,
            "db_bytes": db_bytes,
            "fts": self.fts_available,
        }


DB = MemoryDB(DB_PATH)


def _auto_import_private_seeds() -> None:
    for path in sorted(_bundle_dir().glob("VexPersonalMemorySeed*.json")):
        try:
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            key = "seed:" + digest
            if DB.get_meta(key) == "imported":
                continue
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                continue
            counts = DB.import_seed(payload, source="private-seed")
            DB.set_meta(key, "imported")
            _log(f"[memory] imported private seed {path.name}: {counts}")
        except Exception as exc:
            _log(f"[memory] seed import failed for {path.name}: {exc}")


class Handler(BaseHTTPRequestHandler):
    server_version = f"VexMemoryWorker/{VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except Exception:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            return None
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] in {"/", "/health", "/status"}:
            self._json(200, {"ok": True, "version": VERSION, "db": str(DB_PATH), **DB.stats()})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        payload = self._payload()
        if payload is None:
            self._json(400, {"ok": False, "error": "invalid json payload"})
            return
        try:
            if path == "/search":
                query = _clean(payload.get("query"), 5000)
                result = DB.search(
                    query,
                    memory_limit=int(payload.get("memory_limit") or 8),
                    episode_limit=int(payload.get("episode_limit") or 4),
                )
                self._json(200, {"ok": True, **result, "stats": DB.stats()})
                return
            if path == "/sync":
                counts = DB.sync_profile(payload, source=_clean(payload.get("source"), 120) or "vexnative-iphone")
                self._json(200, {"ok": True, "imported": counts, "stats": DB.stats()})
                return
            if path == "/import":
                counts = DB.import_seed(payload, source=_clean(payload.get("source"), 120) or "private-import")
                self._json(200, {"ok": True, "imported": counts, "stats": DB.stats()})
                return
            if path == "/episode":
                messages = payload.get("messages") or []
                added = DB.sync_messages(
                    messages if isinstance(messages, list) else [],
                    thread_id=_clean(payload.get("thread_id"), 200) or "vexnative-live",
                    source=_clean(payload.get("source"), 120) or "bridge-live",
                    start_ordinal=int(payload.get("start_ordinal") or 0),
                )
                self._json(200, {"ok": True, "messages_added": added, "stats": DB.stats()})
                return
        except Exception as exc:
            _log(f"[memory] {path} failed: {exc}")
            self._json(500, {"ok": False, "error": str(exc)[:500]})
            return
        self._json(404, {"ok": False, "error": "not found"})


def serve(port: int) -> None:
    _auto_import_private_seeds()
    server = ThreadingHTTPServer((HOST, int(port)), Handler)
    _log(f"VexMemoryWorker v{VERSION} listening on {HOST}:{port} — {DB.stats()}")
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


def import_file(path: Path) -> None:
    payload = json.loads(path.read_text("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("seed must be a JSON object")
    counts = DB.import_seed(payload, source="manual-import")
    print(json.dumps({"ok": True, "imported": counts, "stats": DB.stats()}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="VexNative local personal memory worker")
    parser.add_argument("--serve", action="store_true", help="run the local memory HTTP service")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--import", dest="import_path", default=None)
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    if args.import_path:
        import_file(Path(args.import_path))
        return
    if args.stats:
        print(json.dumps(DB.stats(), indent=2))
        return
    serve(args.port)


if __name__ == "__main__":
    main()
