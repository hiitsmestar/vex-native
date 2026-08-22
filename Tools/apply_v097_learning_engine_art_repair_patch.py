#!/usr/bin/env python3
from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    text = text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 1) Persistent, source-aware Learning Engine.
#
# This is intentionally NOT arbitrary self-modifying code. Vex may browse public
# web results, retain source/date/confidence, revisit stale knowledge, and feed
# validated notes back into cognition. Learned knowledge is data, not executable
# code. Technical procedures only become Bridge learned-skills through the
# existing skill validator/compiler path.
# ---------------------------------------------------------------------------
insert_marker = "def _vex_background_services() -> None:\n"
if insert_marker not in text:
    raise SystemExit("background service marker missing")

learning_engine = r'''LEARNING_ROOT = CONFIG_PATH.parent / "learning"
LEARNING_DB = LEARNING_ROOT / "vex-learning.sqlite3"
LEARNING_IDLE_SECONDS = 120
LEARNING_LOOP_SECONDS = 45
LEARNING_STALE_SECONDS = 30 * 86400
LEARNING_MAX_QUEUE = 80
_LEARNING_DB_LOCK = threading.RLock()
_LEARNING_LAST_FOREGROUND = time.time()


def _learning_conn():
    import sqlite3
    LEARNING_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(LEARNING_DB), timeout=12, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            norm TEXT NOT NULL UNIQUE,
            reason TEXT NOT NULL DEFAULT 'curiosity',
            priority INTEGER NOT NULL DEFAULT 30,
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_run REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            last_error TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            norm TEXT NOT NULL UNIQUE,
            summary TEXT NOT NULL,
            confidence REAL NOT NULL,
            source_count INTEGER NOT NULL,
            domains_json TEXT NOT NULL,
            sources_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            refreshed_at REAL NOT NULL,
            expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            kind TEXT NOT NULL,
            detail TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_topics_status ON topics(status, priority, next_run);
        CREATE INDEX IF NOT EXISTS idx_notes_refresh ON notes(refreshed_at);
        CREATE INDEX IF NOT EXISTS idx_activity_time ON activity(created_at);
        """
    )
    conn.commit()
    return conn


def _learning_norm(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    value = re.sub(r"[^a-z0-9 ._+\-/]", "", value)
    return value[:360]


def _learning_activity(kind: str, detail: str, payload: dict | None = None) -> None:
    try:
        with _LEARNING_DB_LOCK:
            conn = _learning_conn()
            conn.execute(
                "INSERT INTO activity(created_at, kind, detail, payload_json) VALUES (?, ?, ?, ?)",
                (time.time(), str(kind)[:80], str(detail)[:1600], json.dumps(payload or {}, ensure_ascii=False)[:8000]),
            )
            conn.execute(
                "DELETE FROM activity WHERE id NOT IN (SELECT id FROM activity ORDER BY id DESC LIMIT 500)"
            )
            conn.commit()
            conn.close()
    except Exception as exc:
        print(f"[learning] activity warning: {exc}", flush=True)


def _learning_note_foreground(message: str = "") -> None:
    global _LEARNING_LAST_FOREGROUND
    _LEARNING_LAST_FOREGROUND = time.time()


def _learning_queue_topic(topic: str, reason: str = "curiosity", priority: int = 30) -> bool:
    topic = re.sub(r"\s+", " ", str(topic or "")).strip()[:700]
    norm = _learning_norm(topic)
    if len(norm) < 8:
        return False
    now = time.time()
    try:
        with _LEARNING_DB_LOCK:
            conn = _learning_conn()
            row = conn.execute("SELECT id, status, priority FROM topics WHERE norm = ?", (norm,)).fetchone()
            if row is None:
                queued = conn.execute("SELECT COUNT(*) AS n FROM topics WHERE status IN ('queued','working','retry')").fetchone()["n"]
                if int(queued or 0) >= LEARNING_MAX_QUEUE:
                    conn.close()
                    return False
                conn.execute(
                    "INSERT INTO topics(topic,norm,reason,priority,status,attempts,next_run,created_at,updated_at,last_error) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (topic, norm, reason[:80], int(priority), "queued", 0, 0.0, now, now, ""),
                )
                conn.commit()
                conn.close()
                _learning_activity("queue", topic, {"reason": reason, "priority": priority})
                print(f"[learning] queued: {topic}", flush=True)
                return True
            # If a completed note is stale, allow the topic to be refreshed.
            note = conn.execute("SELECT expires_at FROM notes WHERE norm = ?", (norm,)).fetchone()
            if note is not None and float(note["expires_at"] or 0) <= now:
                conn.execute(
                    "UPDATE topics SET status='queued', priority=?, next_run=0, updated_at=?, reason=? WHERE norm=?",
                    (max(int(priority), int(row["priority"] or 0)), now, "refresh", norm),
                )
                conn.commit()
                conn.close()
                return True
            conn.close()
    except Exception as exc:
        print(f"[learning] queue warning: {exc}", flush=True)
    return False


def _learning_maybe_queue(message: str) -> None:
    value = re.sub(r"\s+", " ", str(message or "")).strip()
    lower = value.lower()
    if len(value) < 12:
        return
    explicit = [
        "learn about", "learn how", "research ", "look into ", "figure out ",
        "find out ", "teach yourself", "study ", "remember how", "investigate ",
    ]
    failure = [
        "traceback", "error ", " error", "failed", "failure", "crash", "timeout",
        "won't work", "wont work", "doesn't work", "doesnt work", "not working",
    ]
    if any(x in lower for x in explicit):
        _learning_queue_topic(value, reason="explicit-request", priority=90)
        return
    if any(x in lower for x in failure):
        _learning_queue_topic(value, reason="problem-solving", priority=78)
        return
    questionish = lower.endswith("?") or lower.startswith(("how ", "why ", "what ", "which ", "can "))
    technical = any(x in lower for x in [
        "windows", "python", "ollama", "comfy", "computer", "pc ", "drive", "disk",
        "youtube", "render", "model", "bridge", "network", "install", "program", "file",
    ])
    if questionish and technical:
        _learning_queue_topic(value, reason="technical-curiosity", priority=48)


def _learning_sources_for_prompt(sources: list[dict], max_chars: int = 10500) -> str:
    parts = []
    for index, source in enumerate(sources[:6], 1):
        title = str(source.get("title") or "")[:220]
        url = str(source.get("url") or "")[:800]
        content = re.sub(r"\s+", " ", str(source.get("content") or "")).strip()[:2200]
        parts.append(f"SOURCE {index}: {title}\nURL: {url}\nEVIDENCE: {content}")
    return "\n\n".join(parts)[:max_chars]


def _learning_synthesize(topic: str, sources: list[dict]) -> str:
    model = _choose_ollama_model()
    if not model:
        return ""
    evidence = _learning_sources_for_prompt(sources)
    prompt = f"""Research topic: {topic}\n\n{evidence}\n\nSynthesize durable knowledge for future use. Use only the evidence above. State concrete facts/procedures, disagreements or uncertainty, and anything that must be rechecked because it can change. Do not invent missing details. Do not write conversational filler. Keep it under 450 words."""
    try:
        import requests
        response = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are Vex's background research librarian. Produce source-grounded durable notes, not guesses."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "keep_alive": "20m",
                "options": {"temperature": 0.22, "top_p": 0.78, "num_ctx": 4096, "num_predict": 520},
            },
            timeout=150,
        )
        response.raise_for_status()
        payload = response.json()
        return _strip_reasoning_markup(str(((payload.get("message") or {}).get("content")) or ""))[:9000]
    except Exception as exc:
        print(f"[learning] synthesis deferred: {exc}", flush=True)
        return ""


def _learning_research_topic(row) -> tuple[bool, str]:
    topic = str(row["topic"])
    norm = str(row["norm"])
    try:
        results = web_search(topic, limit=6)
    except Exception as exc:
        return False, f"web search failed: {exc}"
    usable = [x for x in results if str(x.get("url") or "").startswith("https://") and str(x.get("content") or "").strip()]
    domains = []
    for item in usable:
        try:
            host = (urllib.parse.urlparse(str(item.get("url"))).hostname or "").lower()
            host = host[4:] if host.startswith("www.") else host
            if host and host not in domains:
                domains.append(host)
        except Exception:
            pass
    if not usable:
        return False, "no usable public web evidence"

    summary = _learning_synthesize(topic, usable)
    if not summary:
        # Retain evidence even if local synthesis was temporarily unavailable.
        summary = "\n".join(
            f"{str(x.get('title') or '')}: {re.sub(r'\s+', ' ', str(x.get('content') or '')).strip()[:800]}"
            for x in usable[:4]
        )[:7000]

    source_count = len(usable)
    independent = len(domains)
    confidence = min(0.94, 0.38 + 0.11 * min(independent, 4) + 0.035 * min(source_count, 6))
    if independent < 2:
        confidence = min(confidence, 0.49)
    now = time.time()
    expires = now + (LEARNING_STALE_SECONDS if confidence >= 0.62 else 7 * 86400)
    source_payload = [
        {
            "title": str(x.get("title") or "")[:300],
            "url": str(x.get("url") or "")[:1200],
            "snippet": re.sub(r"\s+", " ", str(x.get("content") or "")).strip()[:2200],
        }
        for x in usable[:6]
    ]
    with _LEARNING_DB_LOCK:
        conn = _learning_conn()
        conn.execute(
            """INSERT INTO notes(topic,norm,summary,confidence,source_count,domains_json,sources_json,created_at,refreshed_at,expires_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(norm) DO UPDATE SET topic=excluded.topic, summary=excluded.summary,
                 confidence=excluded.confidence, source_count=excluded.source_count,
                 domains_json=excluded.domains_json, sources_json=excluded.sources_json,
                 refreshed_at=excluded.refreshed_at, expires_at=excluded.expires_at""",
            (topic, norm, summary, float(confidence), source_count, json.dumps(domains), json.dumps(source_payload, ensure_ascii=False), now, now, expires),
        )
        conn.execute(
            "UPDATE topics SET status='done', updated_at=?, last_error='' WHERE id=?",
            (now, int(row["id"])),
        )
        conn.commit()
        conn.close()
    _learning_activity("learned", topic, {"confidence": confidence, "domains": domains, "source_count": source_count})
    print(f"[learning] learned ({confidence:.2f}, {independent} domains): {topic}", flush=True)
    return True, f"learned from {source_count} results across {independent} domains"


def _learning_next_topic():
    now = time.time()
    with _LEARNING_DB_LOCK:
        conn = _learning_conn()
        # Automatically requeue stale retained knowledge for refresh.
        stale = conn.execute("SELECT topic,norm FROM notes WHERE expires_at <= ? ORDER BY expires_at ASC LIMIT 3", (now,)).fetchall()
        for item in stale:
            conn.execute(
                "INSERT INTO topics(topic,norm,reason,priority,status,attempts,next_run,created_at,updated_at,last_error) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(norm) DO UPDATE SET status='queued', reason='refresh', priority=MAX(priority,35), next_run=0, updated_at=?",
                (item["topic"], item["norm"], "refresh", 35, "queued", 0, 0.0, now, now, "", now),
            )
        row = conn.execute(
            "SELECT * FROM topics WHERE status IN ('queued','retry') AND next_run <= ? ORDER BY priority DESC, created_at ASC LIMIT 1",
            (now,),
        ).fetchone()
        if row is not None:
            conn.execute("UPDATE topics SET status='working', updated_at=? WHERE id=?", (now, int(row["id"])))
        conn.commit()
        conn.close()
        return row


def _learning_worker_once(force: bool = False) -> dict:
    if not force and time.time() - _LEARNING_LAST_FOREGROUND < LEARNING_IDLE_SECONDS:
        return {"ok": True, "idle": False, "detail": "foreground activity is recent"}
    row = _learning_next_topic()
    if row is None:
        return {"ok": True, "idle": True, "detail": "learning queue empty"}
    ok, detail = _learning_research_topic(row)
    if not ok:
        attempts = int(row["attempts"] or 0) + 1
        delay = min(12 * 3600, 300 * (2 ** min(attempts, 6)))
        status = "retry" if attempts < 5 else "failed"
        with _LEARNING_DB_LOCK:
            conn = _learning_conn()
            conn.execute(
                "UPDATE topics SET status=?, attempts=?, next_run=?, updated_at=?, last_error=? WHERE id=?",
                (status, attempts, time.time() + delay, time.time(), detail[:1200], int(row["id"])),
            )
            conn.commit()
            conn.close()
        _learning_activity("research-failed", str(row["topic"]), {"detail": detail, "attempts": attempts})
    return {"ok": ok, "topic": str(row["topic"]), "detail": detail}


def _learning_worker_loop() -> None:
    time.sleep(240)
    while True:
        try:
            _learning_worker_once(force=False)
        except Exception as exc:
            print(f"[learning] worker warning: {exc}", flush=True)
        time.sleep(LEARNING_LOOP_SECONDS)


def _learning_context(message: str, limit: int = 4) -> str:
    norm_words = set(words(str(message or "")))
    recent_request = any(x in str(message or "").lower() for x in [
        "what have you learned", "what did you learn", "learned recently", "researching", "research queue"
    ])
    try:
        with _LEARNING_DB_LOCK:
            conn = _learning_conn()
            rows = conn.execute(
                "SELECT topic,summary,confidence,sources_json,refreshed_at FROM notes ORDER BY refreshed_at DESC LIMIT 80"
            ).fetchall()
            conn.close()
    except Exception:
        return ""
    scored = []
    for row in rows:
        topic_words = set(words(str(row["topic"])))
        summary_words = set(words(str(row["summary"])[:1800]))
        overlap = len(norm_words & (topic_words | summary_words))
        if recent_request:
            score = float(row["refreshed_at"] or 0) / 1e10
        else:
            score = overlap + len(norm_words & topic_words) * 1.5
        if recent_request or score > 0:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    parts = []
    for _, row in scored[:limit]:
        try:
            sources = json.loads(row["sources_json"] or "[]")
        except Exception:
            sources = []
        source_text = ", ".join(str(x.get("url") or "") for x in sources[:3] if x.get("url"))
        parts.append(
            f"LEARNED TOPIC: {row['topic']}\nCONFIDENCE: {float(row['confidence']):.2f}\nNOTE: {str(row['summary'])[:2600]}\nSOURCES: {source_text}"
        )
    return "\n\n".join(parts)[:9500]


def _learning_status() -> dict:
    try:
        with _LEARNING_DB_LOCK:
            conn = _learning_conn()
            counts = {row["status"]: int(row["n"]) for row in conn.execute("SELECT status, COUNT(*) AS n FROM topics GROUP BY status")}
            notes = int(conn.execute("SELECT COUNT(*) AS n FROM notes").fetchone()["n"])
            recent = [dict(row) for row in conn.execute("SELECT topic,confidence,refreshed_at FROM notes ORDER BY refreshed_at DESC LIMIT 8")]
            queue = [dict(row) for row in conn.execute("SELECT topic,reason,priority,status,attempts,last_error FROM topics WHERE status IN ('queued','working','retry') ORDER BY priority DESC,created_at ASC LIMIT 12")]
            conn.close()
        return {
            "ok": True,
            "node_name": socket.gethostname(),
            "notes": notes,
            "queue_counts": counts,
            "recent": recent,
            "queue": queue,
            "idle_seconds_required": LEARNING_IDLE_SECONDS,
            "policy": "Public-web research is retained with source/date/confidence. Learned data cannot execute arbitrary code or bypass approval rules.",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


'''
text = text.replace(insert_marker, learning_engine + insert_marker, 1)


# Feed retained knowledge into ordinary PC cognition and build curiosity from
# actual user turns. This keeps learning useful in conversation without requiring
# a new iPhone build.
old_safe = '    safe_messages = [{"role": "system", "content": VEX_COGNITION_SYSTEM}]\n'
new_safe = '''    _learning_note_foreground(message)\n    _learning_maybe_queue(message)\n    learned_context = _learning_context(message)\n    system_text = VEX_COGNITION_SYSTEM\n    if learned_context:\n        system_text += "\\n\\nRETAINED RESEARCH MEMORY (source-aware; prefer newer/high-confidence notes, and say when a claim is uncertain):\\n" + learned_context\n    safe_messages = [{"role": "system", "content": system_text}]\n'''
replace_once(old_safe, new_safe, "learning context into cognition")

# Teach the persona what retained learning means so it doesn't describe research
# memory as magic or invent status when asked about it.
persona_marker = 'If Star refers back to something from the recent conversation, resolve the reference instead of pretending it is a new topic. Use concrete wording. Do not mention being Ollama, a local model, a prompt, or an overlay unless Star explicitly asks how the system works.\n"""'
persona_new = 'If Star refers back to something from the recent conversation, resolve the reference instead of pretending it is a new topic. Use concrete wording. Do not mention being Ollama, a local model, a prompt, or an overlay unless Star explicitly asks how the system works.\n\nVex also has persistent source-aware research memory on the connected PC. When RETAINED RESEARCH MEMORY is supplied, use it naturally, preserve its uncertainty/confidence, and never invent having learned something that is not present in memory or current evidence.\n"""'
replace_once(persona_marker, persona_new, "learning persona rule")

# Start the idle learner beside the self-repair and maintenance workers.
old_threads = '    threading.Thread(target=_sr_supervisor_loop, daemon=True, name="VexSelfRepairSupervisor").start()\n'
new_threads = old_threads + '    threading.Thread(target=_learning_worker_loop, daemon=True, name="VexLearningEngine").start()\n'
replace_once(old_threads, new_threads, "learning worker startup")

# Authenticated learning inspection/control endpoints for future VexNative UI and
# for deterministic diagnostics now.
get_marker = '        if parsed.path == "/repair/status":\n'
get_add = '''        if parsed.path == "/learning/status":\n            self._json(200, _learning_status())\n            return\n\n        if parsed.path == "/learning/recent":\n            self._json(200, _learning_status())\n            return\n\n'''
replace_once(get_marker, get_add + get_marker, "learning GET routes")

post_marker = '        if parsed.path == "/repair/run":\n'
post_add = r'''        if parsed.path == "/learning/run":
            self._json(200, _learning_worker_once(force=True))
            return

        if parsed.path == "/learning/queue":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 80_000:
                    self._json(400, {"ok": False, "error": "invalid learning payload"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                topic = str(payload.get("topic") or "").strip()
                if not topic:
                    self._json(400, {"ok": False, "error": "topic is required"})
                    return
                queued = _learning_queue_topic(topic, reason=str(payload.get("reason") or "manual"), priority=int(payload.get("priority") or 70))
                self._json(200, {"ok": True, "queued": queued, "topic": topic, "status": _learning_status()})
            except Exception as exc:
                self._json(500, {"ok": False, "error": f"learning queue failed: {exc}"})
            return

'''
replace_once(post_marker, post_add + post_marker, "learning POST routes")


# ---------------------------------------------------------------------------
# 2) Art runtime repair for the live WinError 1114 / torch c10.dll failure.
#
# First free Ollama RAM before launching Torch/SDXL on memory-constrained nodes.
# If torch itself cannot import and the log matches the c10.dll/1114 failure,
# rebuild only the VexArt venv's free CPU PyTorch wheels. Never touch personal
# files or installed user apps, and rate-limit the heavy repair.
# ---------------------------------------------------------------------------
art_helper_marker = 'def _art_runtime_mode() -> str:\n'
if art_helper_marker not in text:
    raise SystemExit("art runtime mode marker missing")
art_helpers = r'''def _art_release_cognition_memory() -> None:
    try:
        model = _choose_ollama_model()
        if not model:
            return
        import requests
        requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
            timeout=12,
        )
        print(f"[art] released Ollama model before heavy art startup: {model}", flush=True)
        time.sleep(2)
    except Exception:
        pass


def _art_torch_smoke() -> tuple[bool, str]:
    try:
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            [str(ART_PYTHON), "-c", "import torch; print(torch.__version__); print('cuda=' + str(torch.cuda.is_available()))"],
            cwd=str(ART_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=50,
            creationflags=flags,
        )
        output = str(result.stdout or "").strip()[-5000:]
        return result.returncode == 0, output
    except Exception as exc:
        return False, str(exc)


def _art_runtime_repair_needed(detail: str = "") -> bool:
    haystack = (str(detail or "") + "\n" + _art_log_tail(9000)).lower()
    return "winerror 1114" in haystack or "c10.dll" in haystack or "dll initialization routine failed" in haystack


def _art_repair_cpu_torch(force: bool = False) -> tuple[bool, str]:
    ART_ROOT.mkdir(parents=True, exist_ok=True)
    state_path = ART_ROOT / "torch-runtime-repair.json"
    now = time.time()
    if not force and state_path.exists():
        try:
            state = json.loads(state_path.read_text("utf-8"))
            last = float(state.get("attempted_at") or 0)
            if now - last < 24 * 3600:
                return False, "PyTorch runtime repair is rate-limited after a recent attempt"
        except Exception:
            pass
    try:
        state_path.write_text(json.dumps({"attempted_at": now, "status": "running"}, indent=2), "utf-8")
    except Exception:
        pass
    _art_release_cognition_memory()
    try:
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        commands = [
            [str(ART_PYTHON), "-m", "pip", "install", "--upgrade", "pip"],
            [
                str(ART_PYTHON), "-m", "pip", "install", "--upgrade", "--force-reinstall", "--no-cache-dir",
                "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cpu",
            ],
        ]
        logs = []
        for command in commands:
            result = subprocess.run(
                command,
                cwd=str(ART_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=1800,
                creationflags=flags,
            )
            logs.append(str(result.stdout or "")[-5000:])
            if result.returncode != 0:
                detail = "\n".join(logs)[-8500:]
                state_path.write_text(json.dumps({"attempted_at": now, "status": "failed", "detail": detail}, indent=2), "utf-8")
                return False, f"CPU PyTorch reinstall failed: {detail[-1800:]}"
        ok, smoke = _art_torch_smoke()
        state_path.write_text(json.dumps({"attempted_at": now, "status": "ok" if ok else "failed", "detail": smoke}, indent=2), "utf-8")
        if ok:
            _learning_queue_topic("PyTorch Windows c10.dll WinError 1114 DLL initialization failure causes and prevention", reason="self-repair-learn", priority=65)
            return True, f"rebuilt CPU PyTorch runtime; smoke test: {smoke[-800:]}"
        return False, f"PyTorch still cannot import after reinstall: {smoke[-1600:]}"
    except Exception as exc:
        try:
            state_path.write_text(json.dumps({"attempted_at": now, "status": "failed", "detail": str(exc)}, indent=2), "utf-8")
        except Exception:
            pass
        return False, f"PyTorch repair failed: {exc}"


'''
text = text.replace(art_helper_marker, art_helpers + art_helper_marker, 1)

# Free the cognition model before a cold ComfyUI process launch when RAM is tight.
art_launch_marker = '    import subprocess\n    ART_ROOT.mkdir(parents=True, exist_ok=True)\n    log_path = ART_ROOT / "comfyui-bridge.log"\n'
art_launch_new = '''    try:\n        snapshot = _resource_snapshot()\n        available = snapshot.get("memory_available")\n        total = snapshot.get("memory_total")\n        if (available is not None and int(available) < 8 * 1024**3) or (total is not None and int(total) < 16 * 1024**3):\n            _art_release_cognition_memory()\n    except Exception:\n        pass\n\n    import subprocess\n    ART_ROOT.mkdir(parents=True, exist_ok=True)\n    log_path = ART_ROOT / "comfyui-bridge.log"\n'''
replace_once(art_launch_marker, art_launch_new, "memory-aware art startup")

# Replace the self-heal art routine with a bounded dependency-aware repair.
old_sr_art = r'''def _sr_repair_art(force: bool = False) -> tuple[bool, str]:
    if not _sr_art_installed():
        return True, "art engine not installed on this node"
    if _art_comfy_health(timeout=1.0):
        return True, "already healthy"
    if not _sr_can_attempt("art", force=force):
        return False, "restart circuit breaker active"
    _sr_mark_attempt("art")
    ok, error = _ensure_art_comfy()
    return bool(ok), "restarted ComfyUI" if ok else str(error or "ComfyUI restart failed")
'''
new_sr_art = r'''def _sr_repair_art(force: bool = False) -> tuple[bool, str]:
    if not _sr_art_installed():
        return True, "art engine not installed on this node"
    if _art_comfy_health(timeout=1.0):
        return True, "already healthy"
    if not _sr_can_attempt("art", force=force):
        return False, "restart circuit breaker active"
    _sr_mark_attempt("art")

    # A low-memory cold start can make Windows report c10.dll initialization
    # failure even when the files are intact. Unload the 4B model first and retry.
    _art_release_cognition_memory()
    ok, error = _ensure_art_comfy()
    if ok:
        return True, "restarted ComfyUI after freeing cognition memory"

    detail = str(error or "ComfyUI restart failed")
    if _art_runtime_repair_needed(detail):
        smoke_ok, smoke = _art_torch_smoke()
        if not smoke_ok:
            repaired, repair_detail = _art_repair_cpu_torch(force=force)
            if repaired:
                ok2, error2 = _ensure_art_comfy()
                if ok2:
                    _learning_queue_topic("ComfyUI CPU-only Windows startup reliability and memory management", reason="self-repair-learn", priority=60)
                    return True, "repaired CPU PyTorch runtime and restarted ComfyUI"
                return False, f"PyTorch repaired but ComfyUI still failed: {error2}"
            return False, f"ComfyUI torch runtime failure. {repair_detail}"
        # Torch imports now, so the original failure was likely transient memory
        # pressure. Give ComfyUI one clean retry with cognition unloaded.
        ok3, error3 = _ensure_art_comfy()
        if ok3:
            return True, "recovered transient PyTorch DLL startup failure"
        return False, str(error3 or detail)
    return False, detail
'''
replace_once(old_sr_art, new_sr_art, "dependency-aware art self-repair")

# On small-memory PCs don't eagerly keep both the 4B brain and SDXL resident.
old_warm_art_start = '''    def warm_art() -> None:\n        # Give cognition first claim on CPU/RAM. If Ollama is unusually slow,\n        # don't block art forever; proceed after the bounded wait.\n        cognition_settled.wait(timeout=165)\n        time.sleep(12)\n        if ART_PYTHON.exists() and (ART_COMFY_DIR / "main.py").exists() and not _art_comfy_health(timeout=0.8):\n'''
new_warm_art_start = '''    def warm_art() -> None:\n        # Give cognition first claim on CPU/RAM. Small-memory utility PCs keep art\n        # cold until a render is requested so Ollama and SDXL do not fight.\n        cognition_settled.wait(timeout=165)\n        time.sleep(12)\n        try:\n            snap = _resource_snapshot()\n            total = snap.get("memory_total")\n            available = snap.get("memory_available")\n            if (total is not None and int(total) < 16 * 1024**3) or (available is not None and int(available) < 6 * 1024**3):\n                print("[art] low-memory node: deferring ComfyUI warmup until a render is requested", flush=True)\n                return\n        except Exception:\n            pass\n        if ART_PYTHON.exists() and (ART_COMFY_DIR / "main.py").exists() and not _art_comfy_health(timeout=0.8):\n'''
replace_once(old_warm_art_start, new_warm_art_start, "low-memory art warmup policy")


# ---------------------------------------------------------------------------
# 3) Version bump and build-time invariants.
# ---------------------------------------------------------------------------
bridge_path.write_text(text, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.6.2"' not in full:
    raise SystemExit("full bridge v0.9.6.2 marker missing")
full = full.replace('VERSION = "0.9.6.2"', 'VERSION = "0.9.7"', 1)
full_path.write_text(full, encoding="utf-8")

checks = [
    "LEARNING_DB", "def _learning_worker_loop", "def _learning_context",
    'parsed.path == "/learning/status"', 'parsed.path == "/learning/queue"',
    "VexLearningEngine", "RETAINED RESEARCH MEMORY",
    "def _art_release_cognition_memory", "def _art_torch_smoke",
    "def _art_repair_cpu_torch", "WinError 1114", "low-memory node",
]
final = bridge_path.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"missing v0.9.7 marker: {marker}")
if 'VERSION = "0.9.7"' not in full_path.read_text(encoding="utf-8"):
    raise SystemExit("missing v0.9.7 launcher version")

print("Applied Vex v0.9.7 source-aware Learning Engine + WinError 1114 art runtime repair")
