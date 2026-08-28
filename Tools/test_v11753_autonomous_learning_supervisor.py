#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "Bridge" / "vex_bridge.py"
INSTALLER = ROOT / "Tools" / "VexAgentRuntimeInstall.py"

source = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")
compile(source, str(BRIDGE), "exec")
compile(installer, str(INSTALLER), "exec")

checks = {
    "proven bridge identity": '"version": "0.11.7.39"' in source,
    "bundle version": '"agent_runtime_bundle": "0.11.7.53"' in source,
    "installer version": 'BUNDLE_VERSION = "0.11.7.53"' in installer,
    "separate project database": "PROJECT_LEARNING_DB" in source and "vex-project-learning.sqlite3" in source,
    "separate proposal root": "PROJECT_PROPOSAL_ROOT" in source,
    "source receipt table": "evidence_receipts" in source and "source_url" in source and "retrieved_at" in source,
    "proposal table": "project_proposals" in source and "approval_required" in source,
    "source-backed learning gate": "def _project_learning_evidence(" in source and "source_count" in source and "sources_json" in source,
    "privacy scrubber": "def _project_redact_for_artifact(" in source,
    "risk classifier": "def _project_risk_classification(" in source,
    "safe test allowlist": "def _project_safe_test_command(" in source,
    "local ollama planner": "def _project_local_proposal(" in source and "OLLAMA_BASE" in source,
    "persistent retry": "PROJECT_SUPERVISOR_RETRY_BASE" in source and "next_run" in source and "attempts" in source,
    "autonomous worker": 'name="VexAutonomousLearningSupervisor"' in source and "def _project_supervisor_loop(" in source,
    "status route": 'parsed.path == "/autolearn/status"' in source,
    "queue route": 'parsed.path == "/autolearn/queue"' in source,
    "run route": 'parsed.path == "/autolearn/run"' in source,
    "field correction preserved": '"explicit-personal-memory-correction-v11752"' in source and "def _explicit_memory_replace(" in source,
    "explicit memory write preserved": '"explicit-personal-memory-write-v11751"' in source,
    "adaptive learning preserved": "ADAPTIVE_DB" in source and 'name="VexAdaptiveLearning"' in source,
    "learning engine preserved": "LEARNING_DB" in source and 'name="VexLearningEngine"' in source,
    "existing autonomy preserved": 'name="VexAutonomousImprovement"' in source,
}

missing = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + name)
if missing:
    raise SystemExit("v0.11.7.53 missing regressions: " + ", ".join(missing))

# Extract the pure boundary helpers from the generated Bridge and execute them in
# isolation. This proves behavior rather than only checking marker strings.
tree = ast.parse(source)
wanted = {"_project_redact_for_artifact", "_project_risk_classification", "_project_safe_test_command"}
nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
if {node.name for node in nodes} != wanted:
    raise SystemExit("v0.11.7.53 could not isolate boundary helpers")
module = ast.Module(body=nodes, type_ignores=[])
ast.fix_missing_locations(module)
ns = {"re": re}
exec(compile(module, "<v11753-boundary-helpers>", "exec"), ns)

redact = ns["_project_redact_for_artifact"]
risk = ns["_project_risk_classification"]
safe_test = ns["_project_safe_test_command"]

samples = [
    ("https://192.168.42.16:8765?token=supersecret", "supersecret"),
    (r"C:\Users\PrivateName\Documents\secret.txt", "PrivateName"),
    ("authorization=BearerSuperSecret", "BearerSuperSecret"),
]
for raw, forbidden in samples:
    cleaned = redact(raw)
    if forbidden in cleaned:
        raise SystemExit(f"privacy scrubber leaked {forbidden}: {cleaned}")
print("PASS privacy scrubber behavior")

for text in [
    "install the new runtime",
    "delete old files",
    "change firewall security setting",
    "deploy release to production",
    "merge this into main branch",
    "overwrite executable in the running runtime",
]:
    level, approval = risk(text)
    if level != "high" or approval is not True:
        raise SystemExit(f"risk boundary failed for {text!r}: {(level, approval)}")
print("PASS protected action approval boundary")

if risk("refine conversational response synthesis")[0] != "low":
    raise SystemExit("benign proposal should remain low risk")
print("PASS benign risk classification")

allowed = [
    "python -m py_compile Tools/example.py",
    "python Tools/test_example.py",
    "git diff --check",
    "git status --short",
]
for cmd in allowed:
    if not safe_test(cmd):
        raise SystemExit(f"allowlisted test rejected: {cmd}")
blocked = [
    "del /Q important.txt",
    "python Tools/test_example.py && git push",
    "powershell Remove-Item -Recurse C:\\",
    "git push --force",
    "python -c \"import os; os.remove('x')\"",
]
for cmd in blocked:
    if safe_test(cmd):
        raise SystemExit(f"unsafe test command accepted: {cmd}")
print("PASS safe test command allowlist")

# The .53 layer may consume technical Learning Engine notes but must not mutate
# authoritative personal Memory Worker rows or use paid cloud inference.
start = source.find("# v0.11.7.53 Autonomous Learning Supervisor")
end = source.find("def _vex_background_services() -> None:", start)
if start < 0 or end < 0:
    raise SystemExit("v0.11.7.53 layer boundaries not found")
layer = source[start:end]
for forbidden in [
    '_memory_post("/import"',
    '_memory_post("/sync"',
    "api.openai.com",
    "OPENAI_API_KEY",
    "subprocess.run(\"git push",
    "os.system(",
]:
    if forbidden in layer:
        raise SystemExit(f"v0.11.7.53 forbidden behavior found in supervisor: {forbidden}")
print("PASS no personal-memory mutation / paid API / automatic remote push")

print("v0.11.7.53 autonomous learning supervisor regressions verified")
