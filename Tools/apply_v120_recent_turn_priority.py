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

# Exact recent-turn recall should not depend on the tiny local model following a
# crowded prompt. Resolve it directly from the real conversation history first.
agent_sig = 'def _v120_agent_chat(history: list[dict], message: str, phone_context: dict | None = None) -> tuple[str, str] | None:\n'
if agent_sig not in text:
    raise SystemExit("v0.12 recent-turn priority missing agent chat signature")
agent_guard = '''def _v120_agent_chat(history: list[dict], message: str, phone_context: dict | None = None) -> tuple[str, str] | None:\n    newest = str(message or "").strip()\n    recent_turn_query = bool(re.search(\n        r"\\b(just|previous|last|earlier|a moment ago)\\b", newest, flags=re.I\n    )) or bool(re.search(\n        r"\\bwhat did i (?:just )?(?:say|ask|tell you|tell you to remember)\\b",\n        newest, flags=re.I,\n    ))\n    if recent_turn_query and isinstance(history, list):\n        prior_user = []\n        for row in reversed(history):\n            if not isinstance(row, dict):\n                continue\n            if str(row.get("role") or "").lower().strip() != "user":\n                continue\n            content = str(row.get("content") or "").strip()\n            if not content:\n                continue\n            prior_user.append(content)\n            exact = re.search(\n                r"remember(?:\\s+this)?(?:\\s+exact)?(?:\\s+test)?\\s+phrase\\s*:\\s*(.+)",\n                content,\n                flags=re.I | re.S,\n            )\n            if exact and re.search(r"\\b(?:phrase|remember)\\b", newest, flags=re.I):\n                value = exact.group(1).strip().strip('\\"\\' .!?')\n                if value:\n                    return value[:1200], "vex-agent-recent-turn"\n        if prior_user and re.search(r"\\bwhat did i (?:just )?(?:say|ask|tell you)\\b", newest, flags=re.I):\n            return prior_user[0][:2200], "vex-agent-recent-turn"\n\n'''
if 'vex-agent-recent-turn' not in text:
    text = text.replace(agent_sig, agent_guard, 1)

# The phone profile is useful background for normal conversation, but for a
# recent-turn question it is precisely the distracting blob we do not want.
profile_line = '    user_profile = str(phone_context.get("user_profile") or "").strip()[:3500]\n'
profile_guard = '''    user_profile = str(phone_context.get("user_profile") or "").strip()[:3500]\n    if recent_turn_query:\n        user_profile = ""\n'''
if profile_line in text:
    text = text.replace(profile_line, profile_guard, 1)
elif 'if recent_turn_query:\n        user_profile = ""' not in text:
    raise SystemExit("v0.12 recent-turn priority could not mute profile grounding")

BRIDGE.write_text(text, encoding="utf-8")
compile(text, str(BRIDGE), "exec")

for marker in [
    'recent_turn = bool(re.search(',
    'facts = [] if recent_turn else _v120_fact_rows(text, 5)',
    'RECENT CONVERSATION HISTORY outranks all long-term memory/profile grounding',
    'vex-agent-recent-turn',
    'exact = re.search(',
    'if recent_turn_query:',
    'user_profile = ""',
]:
    if marker not in text:
        raise SystemExit(f"v0.12 recent-turn priority missing marker: {marker}")

if 'facts = _v120_fact_rows("", 4)' in text:
    raise SystemExit("v0.12 recent-turn priority left empty-query memory fallback active")

print("Applied deterministic v0.12 recent-turn recall before profile/model grounding")
