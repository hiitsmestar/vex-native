#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")


def function_bounds(source: str, name: str) -> tuple[int, int] | None:
    marker = f"def {name}("
    start = source.find(marker)
    if start < 0:
        return None
    next_def = re.search(r"(?m)^def [A-Za-z0-9_]+\(", source[start + 1:])
    end = len(source) if next_def is None else start + 1 + next_def.start()
    return start, end


def harden_chat_function(source: str, name: str) -> tuple[str, bool]:
    bounds = function_bounds(source, name)
    if bounds is None:
        return source, False
    start, end = bounds
    body = source[start:end]

    # Normalize any requests Session already introduced by an older field patch.
    if "session = requests.Session()" in body and "session.trust_env = False" not in body:
        body = body.replace(
            "session = requests.Session()",
            "session = requests.Session()\n        session.trust_env = False",
            1,
        )

    # Normalize the original raw requests.post transport used by both the legacy
    # overlay and the v0.12 agent cognition path.
    if "requests.post(" in body:
        raw_anchor = "        response = requests.post(\n"
        if raw_anchor not in body:
            raise SystemExit(f"v0.12 Ollama chat transport found unexpected requests.post shape in {name}")
        prefix = "        session = requests.Session()\n        session.trust_env = False\n"
        body = body.replace(raw_anchor, prefix + "        response = session.post(\n", 1)

    # Some inherited field layers already changed requests.post to session.post but
    # did not disable environment proxies. Enforce the proxy-free invariant either way.
    if "response = session.post(" in body and "session.trust_env = False" not in body:
        import_anchor = "        import requests\n"
        if import_anchor not in body:
            raise SystemExit(f"v0.12 Ollama chat transport cannot place proxy-safe session in {name}")
        body = body.replace(
            import_anchor,
            import_anchor + "        session = requests.Session()\n        session.trust_env = False\n",
            1,
        )

    if "response = session.post(" not in body or "session.trust_env = False" not in body:
        raise SystemExit(f"v0.12 Ollama chat transport could not make {name} proxy-safe")

    # The field machine is CPU-only/low-memory. Cold first-token generation can
    # exceed the older 42/55-second limits even when Ollama and the model are healthy.
    body, changed = re.subn(r"timeout=(?:42|55|60|90|120)(?:\.0)?", "timeout=180", body, count=1)
    if changed == 0 and "timeout=180" not in body:
        raise SystemExit(f"v0.12 Ollama chat transport could not set patient timeout in {name}")

    return source[:start] + body + source[end:], True


patched = []
for function_name in ["_ollama_chat", "_v120_agent_chat"]:
    text, found = harden_chat_function(text, function_name)
    if found:
        patched.append(function_name)

if "_v120_agent_chat" not in patched:
    raise SystemExit("v0.12 Ollama chat transport requires the active _v120_agent_chat path")

# The old endpoint maps a None generation result to 'no model' even when the
# chooser can see an installed model. Make the 503 truthful for either active call.
if "local cognition generation failed" not in text:
    error_pattern = re.compile(
        r'(?P<indent>\s+)result = (?P<call>_v120_agent_chat\([^\n]+\)|_ollama_chat\([^\n]+\))\n'
        r'(?P=indent)if result is None:\n'
        r'(?P=indent)    self\._json\(503, \{\n'
        r'(?P=indent)        "ok": False,\n'
        r'(?P=indent)        "error": "no local cognition model available",\n'
        r'(?P=indent)        "setup": "Run VexBrainSetup\.ps1 on this PC",\n'
        r'(?P=indent)    \}\)\n'
        r'(?P=indent)    return\n'
    )
    match = error_pattern.search(text)
    if not match:
        raise SystemExit("v0.12 Ollama chat transport could not find active cognition 503 block")
    indent = match.group("indent")
    call = match.group("call")
    replacement = (
        f"{indent}result = {call}\n"
        f"{indent}if result is None:\n"
        f"{indent}    visible_model = _choose_ollama_model()\n"
        f"{indent}    self._json(503, {{\n"
        f"{indent}        \"ok\": False,\n"
        f"{indent}        \"error\": \"local cognition generation failed\" if visible_model else \"no local cognition model available\",\n"
        f"{indent}        \"model\": visible_model,\n"
        f"{indent}        \"setup\": None if visible_model else \"Run VexBrainSetup.ps1 on this PC\",\n"
        f"{indent}    }})\n"
        f"{indent}    return\n"
    )
    text = text[:match.start()] + replacement + text[match.end():]

BRIDGE.write_text(text, encoding="utf-8")
compile(text, str(BRIDGE), "exec")

tree = ast.parse(text)
functions = {
    node.name: ast.get_source_segment(text, node) or ""
    for node in tree.body
    if isinstance(node, ast.FunctionDef)
}
for name in patched:
    body = functions.get(name, "")
    for marker in ["session.trust_env = False", "response = session.post(", "timeout=180"]:
        if marker not in body:
            raise SystemExit(f"v0.12 Ollama chat transport final {name} missing marker: {marker}")
    if "requests.post(" in body:
        raise SystemExit(f"v0.12 Ollama chat transport final {name} still uses proxy-aware requests.post")

for marker in [
    "local cognition generation failed",
    "visible_model = _choose_ollama_model()",
]:
    if marker not in text:
        raise SystemExit(f"v0.12 Ollama chat transport missing marker: {marker}")

print("Applied v0.12 proxy-safe patient Ollama transport to legacy + active agent chat paths with truthful generation errors")
