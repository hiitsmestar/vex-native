#!/usr/bin/env python3
from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
installer_path = Path("Tools/VexAgentRuntimeInstall.py")
text = bridge_path.read_text(encoding="utf-8")
installer = installer_path.read_text(encoding="utf-8")

# v0.11.7.71 implements the locally staged self-improvement proposal:
# - authoritative /facts-only personal recall with natural non-list rendering
# - bounded personal-memory recovery/recheck
# - art-worker repair is actually included when art is the failed capability
# No optional Ollama call is introduced into foreground verified recall.

# ---------------------------------------------------------------------------
# 1) Fact-preserving conversational recall renderer.
# ---------------------------------------------------------------------------
start = text.find("def _verified_personal_memory_reply(message: str) -> tuple[str, str] | None:")
end = text.find("\n\ndef ", start + 10)
if start < 0 or end < 0:
    raise SystemExit("v0.11.7.71 verified personal-memory renderer missing")

renderer = r'''_V11771_RECALL_LOCK = threading.Lock()
_V11771_RECALL_VARIANT = 0


def _v11771_recall_variant() -> int:
    global _V11771_RECALL_VARIANT
    with _V11771_RECALL_LOCK:
        _V11771_RECALL_VARIANT = (_V11771_RECALL_VARIANT + 1) % 12
        return _V11771_RECALL_VARIANT


def _v11771_fact_text(item: dict) -> str:
    if not isinstance(item, dict):
        return ""
    return re.sub(r"\s+", " ", str(item.get("text") or "")).strip()[:1800]


def _v11771_render_verified_facts(facts: list[str], variant: int) -> str:
    # Every factual clause below is copied from an authoritative /facts row.
    clean = [re.sub(r"\s+", " ", str(x or "")).strip() for x in facts if str(x or "").strip()]
    if not clean:
        return ""
    intros = (
        "Yeah, I remember that. 🖤",
        "Yep — I’ve got that in memory. 🖤",
        "I do remember. Here’s the part that matches what you asked:",
        "Mhm. The memory I have for that says:",
    )
    # Rotate fact order only after relevance selection; never generate or paraphrase facts.
    if len(clean) > 1:
        shift = variant % len(clean)
        clean = clean[shift:] + clean[:shift]
    intro = intros[variant % len(intros)]
    if len(clean) == 1:
        return f"{intro} {clean[0]}"
    if len(clean) == 2:
        return f"{intro} {clean[0]} Also, {clean[1]}"
    body = " ".join(clean[:-1])
    return f"{intro} {body} And {clean[-1]}"


def _verified_personal_memory_reply(message: str) -> tuple[str, str] | None:
    parts = _personal_memory_query_parts(message)
    if not parts:
        return None

    selected: list[str] = []
    used: set[str] = set()
    for part in parts:
        data = _memory_post(
            "/facts",
            {"query": part[:5000], "limit": 8},
            timeout=1.4,
        )
        if not isinstance(data, dict):
            continue
        facts = data.get("facts") if isinstance(data.get("facts"), list) else []
        fact = _best_fact_for_query(part, facts, used)
        if fact:
            selected.append(fact)
            used.add(fact)

    # Generic recall: facts still come exclusively from authoritative /facts.
    if not selected and len(parts) == 1:
        data = _memory_post(
            "/facts",
            {"query": str(message or "")[:5000], "limit": 6},
            timeout=1.4,
        )
        if isinstance(data, dict):
            facts = data.get("facts") if isinstance(data.get("facts"), list) else []
            for item in facts:
                fact = _v11771_fact_text(item)
                if fact and fact not in used:
                    selected.append(fact)
                    used.add(fact)
                if len(selected) >= 3:
                    break

    if not selected:
        return None
    reply = _v11771_render_verified_facts(selected[:4], _v11771_recall_variant())
    if not reply:
        return None
    return reply, "pc-memory-facts-v11771"
'''
text = text[:start] + renderer.rstrip() + text[end:]

# ---------------------------------------------------------------------------
# 2) Bounded recovery for local memory and art capabilities.
# ---------------------------------------------------------------------------
probe_start = text.find("def _autonomy_probe_capability(name: str) -> tuple[bool, str]:")
probe_end = text.find("\n\ndef ", probe_start + 10)
if probe_start < 0 or probe_end < 0:
    raise SystemExit("v0.11.7.71 autonomy capability probe missing")

probe = r'''def _v11771_resolve_gap(request_text: str) -> None:
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            conn.execute(
                "UPDATE gaps SET status='resolved',updated_at=? WHERE status='open' AND request_text=?",
                (time.time(), str(request_text)),
            )
            conn.commit()
            conn.close()
    except Exception:
        pass


def _v11771_memory_probe() -> tuple[bool, str]:
    try:
        health = _memory_worker_health(start_if_needed=True)
        if health.get("ok"):
            _v11771_resolve_gap("local capability personal_memory is unhealthy")
            return True, f"worker={health.get('version') or 'healthy'}"
        # One bounded supervisor pass, then a patient recheck. The worker helper itself
        # owns spawning/cooldown and prevents duplicate worker processes.
        try:
            _sr_run_once(force=False, include_art=False)
        except Exception:
            pass
        time.sleep(0.6)
        health = _memory_worker_health(start_if_needed=True)
        if health.get("ok"):
            _v11771_resolve_gap("local capability personal_memory is unhealthy")
            return True, f"worker={health.get('version') or 'healthy-after-repair'}"
        detail = str(health.get("error") or "memory worker unavailable")[:220]
        return False, detail
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {str(exc)[:180]}"


def _v11771_art_probe() -> tuple[bool, str]:
    try:
        installed = bool(globals().get("_sr_art_installed") and _sr_art_installed())
        if not installed:
            _v11771_resolve_gap("local capability art_worker is unhealthy")
            return True, "art worker not installed on this node"
        health_fn = globals().get("_art_comfy_health")
        if callable(health_fn) and bool(health_fn(timeout=1.8)):
            _v11771_resolve_gap("local capability art_worker is unhealthy")
            return True, "healthy"

        # The previous curriculum called include_art=False even for an art failure.
        # This repair explicitly includes art while retaining the supervisor's own
        # low-memory guard/circuit breakers.
        try:
            _sr_run_once(force=False, include_art=True)
        except Exception:
            pass
        if callable(health_fn):
            for _ in range(4):
                time.sleep(1.0)
                try:
                    if bool(health_fn(timeout=2.5)):
                        _v11771_resolve_gap("local capability art_worker is unhealthy")
                        return True, "healthy-after-repair"
                except Exception:
                    pass
        return False, "installed but not answering after bounded repair"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {str(exc)[:180]}"


def _autonomy_probe_capability(name: str) -> tuple[bool, str]:
    try:
        if name == "personal_memory":
            return _v11771_memory_probe()
        if name == "art_worker":
            return _v11771_art_probe()
        if name == "local_cognition":
            model = _choose_ollama_model()
            return bool(model), f"model={model or 'none'}"
        if name == "web_research":
            return callable(globals().get("web_search")), "web_search available" if callable(globals().get("web_search")) else "web_search missing"
        if name == "learned_skills":
            data = _load_skills()
            skills = data.get("skills") if isinstance(data, dict) else []
            return isinstance(skills, list), f"saved_skills={len(skills or [])}"
        if name == "self_repair":
            status = _sr_status()
            return bool(status.get("ok")), "supervisor available"
        if name == "file_index":
            index = getattr(STATE, "index", None) if STATE is not None else None
            if index is None:
                return False, "index unavailable"
            docs = len(getattr(index, "documents", []) or [])
            return docs > 0, f"indexed_files={docs}"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {str(exc)[:180]}"
    return False, "unknown capability"
'''
text = text[:probe_start] + probe.rstrip() + text[probe_end:]

# Bundle identity advances while the proven Bridge protocol remains .39.
text = text.replace('"agent_runtime_bundle": "0.11.7.57"', '"agent_runtime_bundle": "0.11.7.71"')
installer = installer.replace('BUNDLE_VERSION = "0.11.7.57"', 'BUNDLE_VERSION = "0.11.7.71"')
installer = installer.replace('Vex Agent Runtime v0.11.7.57', 'Vex Agent Runtime v0.11.7.71')

bridge_path.write_text(text, encoding="utf-8")
installer_path.write_text(installer, encoding="utf-8")
compile(text, str(bridge_path), "exec")
compile(installer, str(installer_path), "exec")

final = bridge_path.read_text(encoding="utf-8")
for marker in [
    '"agent_runtime_bundle": "0.11.7.71"',
    "def _v11771_render_verified_facts(",
    '"/facts"',
    '"pc-memory-facts-v11771"',
    "def _v11771_memory_probe(",
    "def _v11771_art_probe(",
    "include_art=True",
    "status='resolved'",
]:
    if marker not in final:
        raise SystemExit(f"v0.11.7.71 verifier missing: {marker}")
if 'lines.append(f"{index}. {fact}")' in final:
    raise SystemExit("v0.11.7.71 numbered clipboard recall survived")
print("Applied v0.11.7.71 bounded self-repair + grounded conversational recall")
