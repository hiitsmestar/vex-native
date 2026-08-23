#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

# The model already knows Vex/Star persona and authoritative current state from
# v0.10.8. Add only factual runtime identity so implementation questions do not
# invite hallucinated "super smart brain" descriptions.
old_model = '''def _ollama_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:\n    model = _choose_ollama_model()\n    if not model:\n        return None\n'''
new_model = '''def _ollama_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:\n    model = _choose_ollama_model()\n    if not model:\n        return None\n    runtime_capacity = _cognition_capacity()\n'''
if old_model in text:
    text = text.replace(old_model, new_model, 1)
elif "runtime_capacity = _cognition_capacity()" not in text:
    raise SystemExit("v0.10.9.3 runtime model anchor missing")

old_dynamic = '''    dynamic_system = system_text + "\\n\\n" + grounding\n'''
new_dynamic = '''    dynamic_system = system_text + "\\n\\n" + grounding\n    runtime_grounding = (\n        "\\n\\nRUNTIME COGNITION FACTS\\n"\n        f"Current provider: local PC cognition via Ollama\\n"\n        f"Current model: {model}\\n"\n        f"Current hardware tier: {str(runtime_capacity.get('tier') or 'unknown')}\\n"\n        f"Current pressure state: {str(runtime_capacity.get('pressure') or 'unknown')}\\n"\n        f"Current model cap: {runtime_capacity.get('max_billions')}B\\n"\n        "These are verified runtime facts for this request. If Star explicitly asks what brain/model/provider "\n        "you are using right now, answer with these facts directly and naturally. Do not invent a different "\n        "model, vague AI buddy, cloud service, or fictional implementation. Keep Vex's normal personality while "\n        "being technically exact. Do not mention these implementation details unless Star asks or they are "\n        "directly relevant."\n    )\n    dynamic_system += runtime_grounding\n'''
if old_dynamic in text:
    text = text.replace(old_dynamic, new_dynamic, 1)
elif "RUNTIME COGNITION FACTS" not in text:
    raise SystemExit("v0.10.9.3 dynamic system anchor missing")

path.write_text(text, encoding="utf-8")
final = path.read_text(encoding="utf-8")
for marker in [
    "runtime_capacity = _cognition_capacity()",
    "RUNTIME COGNITION FACTS",
    "Current model: {model}",
    "verified runtime facts for this request",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.10.9.3 marker: {marker}")
compile(final, str(path), "exec")
print("Applied v0.10.9.3 runtime cognition identity grounding")
