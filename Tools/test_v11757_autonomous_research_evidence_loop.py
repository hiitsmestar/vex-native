#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")

bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(remote, str(REMOTE), "exec")
compile(installer, str(INSTALLER), "exec")

# Preserve the complete .56 Doctor installed-layout/startup-probe regression while
# advancing only its expected exposed bundle identities to .57.
doctor_path = Path("Tools/test_v11756_remote_doctor_startup_probe_hotfix.py")
doctor_source = doctor_path.read_text(encoding="utf-8").replace("0.11.7.56", "0.11.7.57")
exec(
    compile(doctor_source, str(doctor_path) + "[v11757]", "exec"),
    {"__name__": "__main__", "__file__": str(doctor_path)},
)

required_bridge = [
    '"agent_runtime_bundle": "0.11.7.57"',
    "PROJECT_PROPOSAL_PER_TASK_CAP = 6",
    "PROJECT_SAME_EVIDENCE_COOLDOWN_SECONDS = 6 * 3600",
    "def _project_v55_evidence_fingerprint_from_receipts(",
    "evidence has not materially changed since the existing proposal",
    "per-task proposal cap reached",
    "def _windows_native_powershell_windows(",
    "_v11756_windows_native_capabilities_base",
    "CREATE TABLE IF NOT EXISTS project_research_jobs",
    "CREATE TABLE IF NOT EXISTS project_research_notes",
    "_v11757_learning_queue_topic_base = _learning_queue_topic",
    "_v11757_learning_research_topic_base = _learning_research_topic",
    "_v11757_project_queue_task_base = _project_queue_task",
    "_v11757_project_learning_evidence_base = _project_learning_evidence",
    "_project_v57_backfill_jobs(limit=12)",
    'result["mode"] = "autonomous-source-grounded-project-learning-evidence-loop"',
    'result["research_job_dedupe"] = True',
    'result["source_backed_research_notes"] = True',
    'result["confidence_only_on_evidence_change"] = True',
]
for marker in required_bridge:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.57 Bridge regression marker missing: {marker}")

for marker in [
    'VERSION = "0.11.7.57"',
    "_v11756_collect_snapshot_base = collect_snapshot",
    "_v11757_autolearn_public_base = autolearn_public",
    '"research_jobs_enqueued"',
    '"research_jobs_deduped"',
    '"research_jobs_completed"',
    '"research_notes_written"',
    '"evidence_changed"',
    '"evidence_unchanged"',
    '"proposals_emitted"',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.57 Remote regression marker missing: {marker}")

for marker in [
    'BUNDLE_VERSION = "0.11.7.57"',
    'REMOTE_VERSION = "0.11.7.57"',
    "Vex Agent Runtime v0.11.7.57 installed.",
    "Keep VexNative v0.11.7.49 on the iPhone",
]:
    if marker not in installer:
        raise SystemExit(f"v0.11.7.57 installer regression marker missing: {marker}")


def latest_function_source(text: str, name: str) -> str:
    tree = ast.parse(text)
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if not nodes:
        raise SystemExit(f"function not found: {name}")
    node = nodes[-1]
    lines = text.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno]) + "\n"


# .55's material-evidence proposal guard remains underneath .57. Refresh time or
# URL fragments do not create a new proposal; a genuinely new source does.
fingerprint_src = latest_function_source(bridge, "_project_v55_evidence_fingerprint_from_receipts")
fingerprint_ns = {"json": json, "re": re}
exec(compile(fingerprint_src, "<v11757-evidence-fingerprint>", "exec"), fingerprint_ns)
fingerprint = fingerprint_ns["_project_v55_evidence_fingerprint_from_receipts"]
a = [
    {"url": "https://learn.microsoft.com/a#one", "title": "Automation", "retrieved_at": 1},
    {"url": "https://docs.python.org/b", "title": "Runtime", "retrieved_at": 2},
]
b = [
    {"url": "https://learn.microsoft.com/a#two", "title": "Automation", "retrieved_at": 9000},
    {"url": "https://docs.python.org/b", "title": "Runtime", "retrieved_at": 8000},
]
c = b + [{"url": "https://sqlite.org/c", "title": "SQLite", "retrieved_at": 7000}]
if fingerprint(a) != fingerprint(b):
    raise SystemExit("v0.11.7.57 same evidence changed fingerprint on timestamp/fragment only")
if fingerprint(c) == fingerprint(a):
    raise SystemExit("v0.11.7.57 genuinely new source did not change evidence fingerprint")

# The newest queue wrapper must delegate to the already-deduping Learning Engine
# exactly once and add project tracking only for project-autolearn work.
queue_source = latest_function_source(bridge, "_learning_queue_topic")
for marker in [
    "_v11757_learning_queue_topic_base(topic, reason=reason, priority=priority)",
    'str(reason or "") == "project-autolearn"',
    "_project_v57_track_queue(topic, accepted)",
]:
    if marker not in queue_source:
        raise SystemExit(f"v0.11.7.57 learning queue handoff marker missing: {marker}")
if queue_source.count("_v11757_learning_queue_topic_base(") != 1:
    raise SystemExit("v0.11.7.57 learning queue delegates more than once")

# Import the fully assembled Bridge without starting main(), point both local
# SQLite stores at an isolated temp root, and prove the complete no-network
# receipt handoff: one task -> one job, duplicate queue -> dedupe, HTTPS evidence
# -> note/completion, same evidence -> unchanged, new source -> changed note.
with tempfile.TemporaryDirectory(prefix="Vex11757ResearchLoop-") as td:
    root = Path(td)
    old_appdata = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(root / "Roaming")
    try:
        spec = importlib.util.spec_from_file_location("vex_bridge_v11757_test", BRIDGE)
        if spec is None or spec.loader is None:
            raise SystemExit("v0.11.7.57 could not create Bridge import spec")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        if old_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = old_appdata

    module.PROJECT_LEARNING_ROOT = root / "project-learning"
    module.PROJECT_LEARNING_DB = module.PROJECT_LEARNING_ROOT / "vex-project-learning.sqlite3"
    module.PROJECT_PROPOSAL_ROOT = module.PROJECT_LEARNING_ROOT / "proposals"
    module.LEARNING_ROOT = root / "learning"
    module.LEARNING_DB = module.LEARNING_ROOT / "vex-learning.sqlite3"

    topic = "supported Windows accessibility automation reliability evidence"
    now = time.time()
    with module._PROJECT_DB_LOCK:
        conn = module._project_conn()
        cur = conn.execute(
            """INSERT INTO project_tasks(
                   created_at,updated_at,source_gap_id,goal,detail,category,public_topic,status,attempts,next_run,last_error
               ) VALUES (?,?,?,?,?,?,?,?,0,0,'')""",
            (now, now, 57001, "Improve supported Windows accessibility automation reliability", "synthetic CI gap", "capability", topic, "research"),
        )
        task_id = int(cur.lastrowid)
        conn.commit()
        conn.close()

    original_queue_base = module._v11757_learning_queue_topic_base
    try:
        module._v11757_learning_queue_topic_base = lambda _topic, reason="curiosity", priority=30: True
        if module._learning_queue_topic(topic, reason="project-autolearn", priority=86) is not True:
            raise SystemExit("v0.11.7.57 first project research queue was not accepted")
        module._v11757_learning_queue_topic_base = lambda _topic, reason="curiosity", priority=30: False
        if module._learning_queue_topic(topic, reason="project-autolearn", priority=86) is not False:
            raise SystemExit("v0.11.7.57 duplicate project research queue was not deduplicated")
    finally:
        module._v11757_learning_queue_topic_base = original_queue_base

    with module._PROJECT_DB_LOCK:
        conn = module._project_conn()
        module._project_v57_ensure_schema(conn)
        jobs = conn.execute("SELECT * FROM project_research_jobs WHERE task_id=?", (task_id,)).fetchall()
        conn.close()
    if len(jobs) != 1:
        raise SystemExit(f"v0.11.7.57 expected one linked research job, got {len(jobs)}")
    if int(jobs[0]["enqueued_count"] or 0) != 1 or int(jobs[0]["deduped_count"] or 0) != 1:
        raise SystemExit(f"v0.11.7.57 enqueue/dedupe counters wrong: {dict(jobs[0])}")

    norm = module._learning_norm(topic)
    sources_one = [
        {"title": "Microsoft UI Automation", "url": "https://learn.microsoft.com/windows/win32/winauto/entry-uiauto-win32", "snippet": "Supported accessibility API evidence."},
    ]
    with module._LEARNING_DB_LOCK:
        conn = module._learning_conn()
        conn.execute(
            """INSERT INTO notes(topic,norm,summary,confidence,source_count,domains_json,sources_json,created_at,refreshed_at,expires_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (topic, norm, "Source-backed Windows accessibility note.", 0.71, 1, json.dumps(["learn.microsoft.com"]), json.dumps(sources_one), now, now, now + 86400),
        )
        conn.commit()
        conn.close()

    first = module._project_v57_sync_learning_note(task_id, topic, observe_change=False)
    if not first.get("ok") or not first.get("evidence_changed") or first.get("source_count") != 1:
        raise SystemExit(f"v0.11.7.57 first source-backed note handoff failed: {first}")
    same = module._project_v57_sync_learning_note(task_id, topic, observe_change=True)
    if not same.get("ok") or not same.get("evidence_unchanged") or same.get("evidence_changed"):
        raise SystemExit(f"v0.11.7.57 same-evidence observation was not deduped: {same}")

    sources_two = sources_one + [
        {"title": "Python sqlite3", "url": "https://docs.python.org/3/library/sqlite3.html", "snippet": "Independent persistence evidence."},
    ]
    with module._LEARNING_DB_LOCK:
        conn = module._learning_conn()
        conn.execute(
            """UPDATE notes SET summary=?,confidence=?,source_count=?,domains_json=?,sources_json=?,refreshed_at=? WHERE norm=?""",
            (
                "Updated source-backed note with independent persistence evidence.", 0.79, 2,
                json.dumps(["learn.microsoft.com", "docs.python.org"]), json.dumps(sources_two), now + 10, norm,
            ),
        )
        conn.commit()
        conn.close()

    changed = module._project_v57_sync_learning_note(task_id, topic, observe_change=True)
    if not changed.get("ok") or not changed.get("evidence_changed") or changed.get("source_count") != 2:
        raise SystemExit(f"v0.11.7.57 changed-evidence observation failed: {changed}")

    metrics = module._project_v57_metrics()
    expected = {
        "initiatives_seen": 1,
        "research_jobs": 1,
        "research_jobs_pending": 0,
        "research_jobs_enqueued": 1,
        "research_jobs_deduped": 1,
        "research_jobs_completed": 1,
        "research_notes_written": 2,
        "evidence_changed": 2,
        "evidence_unchanged": 1,
        "proposals_emitted": 0,
    }
    for key, value in expected.items():
        if int(metrics.get(key, -1)) != value:
            raise SystemExit(f"v0.11.7.57 metric {key} expected {value}, got {metrics}")

    status = module._project_supervisor_status()
    if status.get("version") != "0.11.7.57" or status.get("mode") != "autonomous-source-grounded-project-learning-evidence-loop":
        raise SystemExit(f"v0.11.7.57 autolearn identity wrong: {status}")
    for flag in ["proposal_dedupe", "evidence_change_required", "research_job_dedupe", "source_backed_research_notes", "confidence_only_on_evidence_change"]:
        if status.get(flag) is not True:
            raise SystemExit(f"v0.11.7.57 autolearn flag {flag} missing: {status}")

# Remote Support may expose only sanitized booleans/counts for the new loop.
remote_autolearn = latest_function_source(remote, "autolearn_public")
for forbidden in ["project_research_notes", "sources_json", "public_topic", "evidence_fingerprint", "summary"]:
    if forbidden in remote_autolearn:
        raise SystemExit(f"v0.11.7.57 Remote autolearn leaked local research detail: {forbidden}")

print("v0.11.7.57 regressions passed: one gap -> deduped research job -> source note -> material evidence counters + .56 Doctor recovery")
