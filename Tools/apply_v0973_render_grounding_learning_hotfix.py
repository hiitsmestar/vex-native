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
# v0.9.7.3 field hotfix
# - CPU ComfyUI got through startup but failed inside the render workflow.
# - local cognition was alive again but invented nonexistent recent history.
# - broad requests such as "learn everything you can about coding" did not
#   reliably seed the background learning queue.
# ---------------------------------------------------------------------------

# 1) Stronger grounding for the local cognition model. It may infer from supplied
# history, but it must never manufacture a previous task/event just to sound alive.
ground_marker = (
    "If Star refers back to something from the recent conversation, resolve the reference instead of pretending it is a new topic. "
    "Use concrete wording. Do not mention being Ollama, a local model, a prompt, or an overlay unless Star explicitly asks how the system works."
)
ground_new = (
    "If Star refers back to something from the recent conversation, resolve the reference instead of pretending it is a new topic. "
    "Use concrete wording. Never invent prior tasks, results, conversations, schedules, projects, promises, preferences, or real-world events. "
    "If the supplied history does not support a claimed past event, do not claim it happened; answer from what is actually present. "
    "Do not say you were waiting for Star to finish some task unless that task really appears in the supplied history. "
    "Do not mention being Ollama, a local model, a prompt, or an overlay unless Star explicitly asks how the system works."
)
replace_once(ground_marker, ground_new, "cognition grounding prompt")

ollama_start = text.find("def _ollama_chat(")
if ollama_start < 0:
    raise SystemExit("ollama chat function missing")
ollama_end = text.find("\n\ndef ", ollama_start + 20)
if ollama_end < 0:
    ollama_end = len(text)
ollama = text[ollama_start:ollama_end]
ollama = ollama.replace('"temperature": 0.72', '"temperature": 0.58')
ollama = ollama.replace('"top_p": 0.90', '"top_p": 0.86')
text = text[:ollama_start] + ollama + text[ollama_end:]


# 2) CPU art execution mode. ComfyUI already starts with --cpu on these machines,
# but the live test reached execution and then errored. Force full precision on
# CPU hosts, keep VAE in fp32, disable xformers, and skip previews. This avoids
# unsupported half-precision CPU kernels and saves needless preview work.
cpu_args_old = '''    if mode == "cpu":\n        args.append("--cpu")\n'''
cpu_args_new = '''    if mode == "cpu":\n        args.extend(["--cpu", "--force-fp32", "--fp32-vae", "--disable-xformers", "--preview-method", "none"])\n'''
replace_once(cpu_args_old, cpu_args_new, "CPU ComfyUI precision flags")


# 3) Preserve the actual ComfyUI execution error instead of collapsing everything
# to the useless string "ComfyUI reported a render error". The next failure, if
# any, will identify the node/type/message directly in VexNative and the log.
run_marker = "def _art_run_job(job_id: str) -> None:\n"
if run_marker not in text:
    raise SystemExit("art run-job marker missing")

error_helper = r'''def _art_execution_error_detail(record: dict) -> str:
    try:
        status = record.get("status") or {}
        messages = status.get("messages") or [] if isinstance(status, dict) else []
        for item in reversed(messages):
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            kind = str(item[0] or "")
            payload = item[1] if isinstance(item[1], dict) else {}
            if kind != "execution_error" and not payload.get("exception_message"):
                continue
            node_id = str(payload.get("node_id") or "?")
            node_type = str(payload.get("node_type") or payload.get("class_type") or "unknown node")
            exc_type = str(payload.get("exception_type") or "RenderError")
            message = str(payload.get("exception_message") or payload.get("message") or "ComfyUI execution failed")
            trace = payload.get("traceback") or []
            if isinstance(trace, list):
                trace_tail = " | ".join(str(x).strip() for x in trace[-2:] if str(x).strip())
            else:
                trace_tail = str(trace or "").strip()[-1200:]
            detail = f"ComfyUI render error at node {node_id} ({node_type}): {exc_type}: {message}"
            if trace_tail:
                detail += f" | {trace_tail}"
            return detail[:2600]
    except Exception:
        pass
    return "ComfyUI reported a render error"


def _art_record_execution_error(detail: str, record: dict) -> None:
    try:
        ART_ROOT.mkdir(parents=True, exist_ok=True)
        target = ART_ROOT / "comfyui-render-errors.log"
        payload = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "detail": str(detail)[:3000],
            "record": record,
        }
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str)[:18000] + "\n")
    except Exception:
        pass


'''
text = text.replace(run_marker, error_helper + run_marker, 1)

render_error_old = '                raise RuntimeError("ComfyUI reported a render error")\n'
render_error_new = '''                detail = _art_execution_error_detail(record)\n                _art_record_execution_error(detail, record)\n                raise RuntimeError(detail)\n'''
replace_once(render_error_old, render_error_new, "ComfyUI execution error detail")


# 4) Broad-domain learning requests become an actual curriculum instead of a
# single vague web query. Learned material is still retained as source-grounded
# notes, not executable self-modifying code.
learn_marker = "def _learning_maybe_queue(message: str) -> None:\n"
if learn_marker not in text:
    raise SystemExit("learning queue marker missing")

learning_expander = r'''def _learning_expand_broad_request(message: str) -> int:
    value = re.sub(r"\s+", " ", str(message or "")).strip()
    lower = value.lower()
    broad = any(token in lower for token in [
        "learn everything", "learn all you can", "learn as much as", "learn everything you can",
        "teach yourself everything", "study everything", "master everything", "learn the whole",
    ])
    coding = any(token in lower for token in [
        "coding", "programming", "software development", "computer programming", "developer", "code from the internet",
    ])
    if not (broad and coding):
        return 0

    topics = [
        "Python language fundamentals and standard library official documentation",
        "Git version control fundamentals branching merging rebasing and recovery official documentation",
        "algorithms and data structures practical implementation and complexity",
        "debugging techniques stack traces logging profilers and systematic fault isolation",
        "software testing unit integration property regression and end-to-end testing",
        "Windows PowerShell automation process management services files networking and security",
        "HTTP HTTPS REST APIs JSON TLS certificates sockets and client-server architecture",
        "SQL SQLite relational database design transactions indexes migrations and query optimization",
        "concurrency threading multiprocessing async IO race conditions locks and deadlocks",
        "software architecture modularity interfaces dependency injection design patterns and maintainability",
        "secure coding input validation authentication authorization secrets and least privilege",
        "performance profiling CPU memory disk network bottlenecks caching and benchmarking",
        "Python packaging virtual environments pip wheels dependency resolution and reproducible installs",
        "GitHub Actions continuous integration automated tests builds artifacts and release workflows",
        "Swift SwiftUI iOS application architecture networking concurrency persistence and debugging",
        "HTML CSS JavaScript TypeScript browser APIs accessibility and modern web application fundamentals",
        "C and C++ memory ownership compilation linking DLLs ABI debugging and Windows runtime dependencies",
        "local AI application engineering Ollama model serving prompting context memory and tool routing",
        "PyTorch inference CPU GPU precision model loading performance and Windows dependency troubleshooting",
        "ComfyUI architecture workflows nodes checkpoints samplers APIs CPU GPU modes and automation",
        "code review refactoring documentation API reading maintainable naming and technical debt management",
        "software licensing open source licenses dependency licenses and safe reuse of third-party code",
    ]
    queued = 0
    for index, topic in enumerate(topics):
        priority = 96 - min(index // 4, 5)
        if _learning_queue_topic(topic, reason="broad-coding-curriculum", priority=priority):
            queued += 1
    _learning_activity("curriculum", "coding curriculum seeded", {"queued": queued, "requested": len(topics)})
    print(f"[learning] coding curriculum seeded: {queued}/{len(topics)} topics queued", flush=True)
    return queued


'''
text = text.replace(learn_marker, learning_expander + learn_marker, 1)

maybe_start = text.find("def _learning_maybe_queue(message: str) -> None:\n")
maybe_end = text.find("\n\ndef ", maybe_start + 20)
if maybe_start < 0 or maybe_end < 0:
    raise SystemExit("learning maybe-queue function bounds missing")
maybe = text[maybe_start:maybe_end]
needle = '    lower = value.lower()\n    if len(value) < 12:\n        return\n'
replacement = '''    lower = value.lower()\n    if len(value) < 12:\n        return\n    if _learning_expand_broad_request(value):\n        return\n'''
if needle not in maybe:
    raise SystemExit("learning maybe-queue body marker missing")
maybe = maybe.replace(needle, replacement, 1)
maybe = maybe.replace(
    '"learn about", "learn how", "research ", "look into ", "figure out ",',
    '"learn about", "learn how", "learn everything", "learn all you can", "learn as much as", "research ", "look into ", "figure out ",',
    1,
)
maybe = maybe.replace(
    '"windows", "python", "ollama", "comfy", "computer", "pc ", "drive", "disk",',
    '"windows", "python", "coding", "programming", "software", "ollama", "comfy", "computer", "pc ", "drive", "disk",',
    1,
)
text = text[:maybe_start] + maybe + text[maybe_end:]


bridge_path.write_text(text, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.7.2"' not in full:
    raise SystemExit("v0.9.7.2 launcher marker missing")
full = full.replace('VERSION = "0.9.7.2"', 'VERSION = "0.9.7.3"', 1)
full_path.write_text(full, encoding="utf-8")

checks = [
    "Never invent prior tasks",
    '"temperature": 0.58',
    '"--force-fp32"',
    "def _art_execution_error_detail",
    "comfyui-render-errors.log",
    "def _learning_expand_broad_request",
    "broad-coding-curriculum",
]
final = bridge_path.read_text(encoding="utf-8")
for check in checks:
    if check not in final:
        raise SystemExit(f"v0.9.7.3 missing marker: {check}")
if 'VERSION = "0.9.7.3"' not in full_path.read_text(encoding="utf-8"):
    raise SystemExit("v0.9.7.3 launcher version missing")

print("Applied Vex v0.9.7.3 render + grounding + broad-learning hotfix")
