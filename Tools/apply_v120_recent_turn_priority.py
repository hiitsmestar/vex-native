#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")

if 'def _v120_context(message: str) -> dict:' not in text:
    raise SystemExit("v0.12 recent-turn priority missing context builder")

old = '''    # Give ordinary conversation a small trusted-memory grounding window so the\n    # model can *reason with* continuity instead of only answering explicit recall.\n    facts = _v120_fact_rows(text, 5)\n    if not facts:\n        facts = _v120_fact_rows("", 4)\n    for item in facts[:5]:\n'''
new = '''    # Recent-turn questions must be answered from conversation history first.\n    # Do not pollute them with unrelated long-term/profile rows from an empty\n    # memory query; that caused the 1.7B model to dump Star's profile instead of\n    # recalling the immediately preceding phrase.\n    recent_turn = bool(re.search(\n        r"\\b(just|previous|last|earlier|a moment ago)\\b", text, flags=re.I\n    )) or bool(re.search(\n        r"\\bwhat did i (?:just )?(?:say|ask|tell you|tell you to remember)\\b",\n        text, flags=re.I,\n    ))\n    facts = [] if recent_turn else _v120_fact_rows(text, 5)\n    for item in facts[:5]:\n'''
if old in text:
    text = text.replace(old, new, 1)
elif 'recent_turn = bool(re.search(' not in text:
    raise SystemExit("v0.12 recent-turn priority could not patch memory fallback")

contract_old = '''- The user's newest message is the task. Answer every question/request it contains; do not silently skip one part.\n- Persona, profile, memory, and state blocks are silent background grounding. Never dump, enumerate, quote, or mechanically paraphrase those blocks unless Star explicitly asks to inspect the stored data itself.\n'''
contract_new = '''- The user's newest message is the task. Answer every question/request it contains; do not silently skip one part.\n- For questions about what Star just said, asked, or told you to remember, RECENT CONVERSATION HISTORY outranks all long-term memory/profile grounding. Answer from the immediately preceding turns first.\n- Persona, profile, memory, and state blocks are silent background grounding. Never dump, enumerate, quote, or mechanically paraphrase those blocks unless Star explicitly asks to inspect the stored data itself.\n'''
if contract_old in text:
    text = text.replace(contract_old, contract_new, 1)
elif 'RECENT CONVERSATION HISTORY outranks all long-term memory/profile grounding' not in text:
    raise SystemExit("v0.12 recent-turn priority could not patch response contract")

BRIDGE.write_text(text, encoding="utf-8")
compile(text, str(BRIDGE), "exec")

for marker in [
    'recent_turn = bool(re.search(',
    'facts = [] if recent_turn else _v120_fact_rows(text, 5)',
    'RECENT CONVERSATION HISTORY outranks all long-term memory/profile grounding',
]:
    if marker not in text:
        raise SystemExit(f"v0.12 recent-turn priority missing marker: {marker}")

if 'facts = _v120_fact_rows("", 4)' in text:
    raise SystemExit("v0.12 recent-turn priority left empty-query memory fallback active")

print("Applied v0.12 recent-turn conversation priority over long-term memory")
