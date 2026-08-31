#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
installer_path = Path("Tools/VexAgentRuntimeInstall.py")
bridge = bridge_path.read_text(encoding="utf-8")
installer = installer_path.read_text(encoding="utf-8")

# Field diagnosis after v0.11.7.79: MemoryWorker v0.11.4 is healthy and populated,
# but the exact acceptance prompt "What do you remember about me?" still missed.
# The Bridge's natural-memory route detector used space-delimited substrings such as
# " me ". A terminal question mark means the normalized input contains " me? ", so
# the explicit broad recall request can bypass verified memory entirely. Route by
# punctuation-normalized tokens/phrases instead of raw space-delimited substrings.

def replace_function(source: str, name: str, replacement: str) -> str:
    start = source.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.11.7.80 missing function: {name}")
    end = source.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"v0.11.7.80 could not bound function: {name}")
    return source[:start] + replacement.rstrip() + source[end:]

replacement = r'''def _personal_memory_fact_question(message: str) -> bool:
    raw = str(message or "").lower().replace("’", "'").strip()
    if not raw:
        return False

    normalized = re.sub(r"[^a-z0-9']+", " ", raw).strip()
    tokens = set(normalized.split())
    compact = " " + normalized + " "

    # Explicit personal recall must win regardless of terminal punctuation.
    # This covers the field acceptance prompt exactly as typed by Star.
    recall_shape = (
        "remember" in tokens
        or "memory" in tokens
        or "memories" in tokens
        or " know about me " in compact
        or " know about us " in compact
    )
    personal_tokens = {"me", "my", "i", "i'm", "i've", "im", "ive", "us", "our", "star", "girlfriend", "relationship"}
    if recall_shape and bool(tokens & personal_tokens):
        return True

    advice_words = {
        "should", "could", "would", "help", "recommend", "suggest", "plan", "need",
        "tonight", "tomorrow", "next"
    }
    if tokens & advice_words:
        return False

    has_personal_anchor = bool(tokens & {"me", "my", "i", "i'm", "i've", "im", "ive", "our", "us"})
    if not has_personal_anchor:
        return False

    fact_question_starts = {"what", "which", "where", "who", "when", "describe", "tell", "do", "am", "have", "did"}
    if not (tokens & fact_question_starts):
        return False

    factual_cues = {
        "color", "hair", "style", "wear", "look", "appearance", "home", "house", "live",
        "name", "age", "height", "size", "favorite", "prefer", "preference", "relationship",
        "girlfriend", "family", "pets", "animals", "music", "clothes", "clothing", "piercings",
        "tattoos", "nails", "voice", "work", "project", "vexnative"
    }
    return bool(tokens & factual_cues)
'''
bridge = replace_function(bridge, "_personal_memory_fact_question", replacement)

if '"agent_runtime_bundle": "0.11.7.79"' not in bridge:
    raise SystemExit("v0.11.7.80 expected .79 Bridge bundle identity missing")
bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.79"', '"agent_runtime_bundle": "0.11.7.80"', 1)
if 'BUNDLE_VERSION = "0.11.7.79"' not in installer:
    raise SystemExit("v0.11.7.80 expected .79 installer identity missing")
installer = installer.replace('BUNDLE_VERSION = "0.11.7.79"', 'BUNDLE_VERSION = "0.11.7.80"', 1)
installer = installer.replace('Vex Agent Runtime v0.11.7.79', 'Vex Agent Runtime v0.11.7.80')

bridge_path.write_text(bridge, encoding="utf-8")
installer_path.write_text(installer, encoding="utf-8")
compile(bridge, str(bridge_path), "exec")
compile(installer, str(installer_path), "exec")

checks = [
    ('bundle identity', '"agent_runtime_bundle": "0.11.7.80"' in bridge),
    ('installer identity', 'BUNDLE_VERSION = "0.11.7.80"' in installer),
    ('punctuation normalization', 're.sub(r"[^a-z0-9\']+", " ", raw)' in bridge),
    ('token personal route', 'recall_shape and bool(tokens & personal_tokens)' in bridge),
    ('facts caller preserved', 'pc-memory-star-query-v11775' in bridge),
    ('worker direct recall preserved', "subject='star' OR canonical_key='core:star:profile'" in Path("Tools/VexMemoryWorker.py").read_text(encoding="utf-8")),
    ('window broker preserved', 'def _v11777_window_action(' in bridge),
]
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.80 verifier failed: " + ", ".join(missing))

print("Applied v0.11.7.80 punctuation-safe verified-memory routing")
