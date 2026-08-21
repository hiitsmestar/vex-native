#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# iPhone: remember which PC Star means, accept natural location-only wording,
# and route unknown commands into the Bridge workflow compiler.
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

old_target = r'''    private static func requestedTarget(_ lower: String) -> NodeTarget? {
        if lower.contains("both computers") || lower.contains("both pcs") || lower.contains("both pc") {
            return .both
        }
        if ["kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer", "second pc"]
            .contains(where: { lower.contains($0) }) {
            return .secondary
        }
        if ["upstairs pc", "upstairs computer", "primary pc", "main pc"]
            .contains(where: { lower.contains($0) }) {
            return .primary
        }
        return nil
    }
'''
new_target = r'''    private static let lastTargetKey = "vex.pc.lastTarget.v1"

    private static func requestedTarget(_ lower: String) -> NodeTarget? {
        if lower.contains("both computers") || lower.contains("both pcs") || lower.contains("both pc") {
            UserDefaults.standard.set("both", forKey: lastTargetKey)
            return .both
        }

        let secondaryAliases = [
            "kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer", "second pc",
            "in the kitchen", "to the kitchen", "downstairs", "hp computer", "hp pc"
        ]
        if secondaryAliases.contains(where: { lower.contains($0) }) {
            UserDefaults.standard.set("secondary", forKey: lastTargetKey)
            return .secondary
        }

        let primaryAliases = [
            "upstairs pc", "upstairs computer", "primary pc", "main pc", "upstairs",
            "monte computer", "monte pc"
        ]
        if primaryAliases.contains(where: { lower.contains($0) }) {
            UserDefaults.standard.set("primary", forKey: lastTargetKey)
            return .primary
        }

        let refersBack = lower == "open it" || lower == "launch it" || lower == "start it" ||
            lower.contains(" on it") || lower.contains(" on that") || lower.contains(" that computer") ||
            lower.contains(" that pc") || lower.hasSuffix(" there")
        if refersBack {
            switch UserDefaults.standard.string(forKey: lastTargetKey) {
            case "primary": return .primary
            case "secondary": return .secondary
            case "both": return .both
            default: break
            }
        }
        return nil
    }
'''
text = replace_once(text, old_target, new_target, "natural PC target resolution")

text = replace_once(
    text,
    'guard let url = toolURL(endpoint: endpoint, path: "/skills/execute") else { return nil }',
    'guard let url = toolURL(endpoint: endpoint, path: "/skills/compile") else { return nil }',
    "route learned skills through compiler",
)

content_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows Bridge: upgrade the v0.8.4 one-step skill learner into a conservative
# compiler. It composes approved primitives, validates them, executes them, and
# persists successful multi-step workflows. It never downloads/executes code,
# never exposes shell/PowerShell, and never rewrites Vex binaries.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

bridge = replace_once(
    bridge,
    'SAFE_SKILL_PRIMITIVES = {"open_url", "launch_app", "open_folder"}\n',
    'SAFE_SKILL_PRIMITIVES = {"open_url", "launch_app", "open_folder", "workflow"}\n',
    "workflow primitive allowlist",
)

# Make learned skill keys independent of which paired PC nickname was used.
old_key_tail = r'''    for phrase in [
        "on the kitchen pc", "on kitchen pc", "on the kitchen computer", "on kitchen computer",
        "on the downstairs pc", "on downstairs pc", "on the downstairs computer",
        "on the upstairs pc", "on upstairs pc", "on the upstairs computer",
        "on the primary pc", "on primary pc", "on the main pc", "on main pc",
        "on both computers", "on both pcs",
    ]:
        lower = lower.replace(phrase, " ")
    return re.sub(r"\s+", " ", lower).strip()
'''
new_key_tail = r'''    for phrase in [
        "on the kitchen pc", "on kitchen pc", "on the kitchen computer", "on kitchen computer",
        "on the downstairs pc", "on downstairs pc", "on the downstairs computer",
        "on the upstairs pc", "on upstairs pc", "on the upstairs computer",
        "on the primary pc", "on primary pc", "on the main pc", "on main pc",
        "on both computers", "on both pcs", "in the kitchen", "to the kitchen",
        "downstairs", "upstairs", "hp computer", "hp pc", "monte computer", "monte pc",
    ]:
        lower = lower.replace(phrase, " ")
    return re.sub(r"\s+", " ", lower).strip()
'''
bridge = replace_once(bridge, old_key_tail, new_key_tail, "portable learned skill keys")

# Extend the existing recipe executor with workflow support.
old_exec_tail = r'''        if primitive == "open_folder":
            path = Path(value)
            if not path.exists() or not path.is_dir():
                return {"ok": False, "node_name": node, "message": "learned folder missing"}
            os.startfile(str(path))
            return {"ok": True, "action": primitive, "node_name": node, "message": f"opened folder {path.name}"}
    except Exception as exc:
'''
new_exec_tail = r'''        if primitive == "open_folder":
            path = Path(value)
            if not path.exists() or not path.is_dir():
                return {"ok": False, "node_name": node, "message": "learned folder missing"}
            os.startfile(str(path))
            return {"ok": True, "action": primitive, "node_name": node, "message": f"opened folder {path.name}"}
        if primitive == "workflow":
            steps = recipe.get("steps") or []
            if not isinstance(steps, list) or not steps or len(steps) > 6:
                return {"ok": False, "node_name": node, "message": "invalid learned workflow"}
            completed = []
            for step in steps:
                if not isinstance(step, dict) or step.get("primitive") == "workflow":
                    return {"ok": False, "node_name": node, "message": "nested workflow not allowed"}
                result = _execute_skill_recipe(step)
                if not result.get("ok"):
                    return {"ok": False, "node_name": node, "message": f"workflow step failed: {result.get('message', 'unknown')}"}
                completed.append(str(result.get("message") or step.get("primitive") or "step"))
                time.sleep(0.08)
            return {"ok": True, "action": primitive, "node_name": node,
                    "message": f"completed {len(completed)} learned workflow steps"}
    except Exception as exc:
'''
bridge = replace_once(bridge, old_exec_tail, new_exec_tail, "workflow recipe execution")

insert_marker = "def learn_and_execute_skill(request: str) -> dict:\n"
idx = bridge.find(insert_marker)
if idx < 0:
    raise SystemExit("vex_bridge.py: v0.8.4 learner marker missing")

compiler_code = r'''
MAX_COMPILED_STEPS = 6


def _split_compound_skill_request(request: str) -> list[str]:
    text = re.sub(r"\s+", " ", str(request or "").strip())
    parts = re.split(r"\s+(?:and then|then|and also|after that|followed by)\s+", text, flags=re.I)
    return [part.strip(" ,.;") for part in parts if part.strip(" ,.;")][:MAX_COMPILED_STEPS]


def _recipe_is_valid(recipe: dict) -> bool:
    primitive = str(recipe.get("primitive") or "")
    value = str(recipe.get("value") or "").strip()
    if primitive == "open_url":
        parsed = urlsplit(value)
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)
    if primitive == "launch_app":
        path = Path(value)
        return path.exists() and path.suffix.lower() in {".lnk", ".exe"}
    if primitive == "open_folder":
        path = Path(value)
        return path.exists() and path.is_dir()
    return False


def _compile_one_safe_step(step_text: str) -> dict | None:
    step_text = str(step_text or "").strip()
    if not step_text:
        return None

    direct_url = _extract_http_url(step_text)
    if direct_url:
        recipe = {"primitive": "open_url", "value": direct_url}
        return recipe if _recipe_is_valid(recipe) else None

    lower = _normalize_skill_text(step_text)
    wants_browserish = any(word in lower for word in [
        "website", "site", "internet", "web", "youtube", "google", "reddit", "github", "spotify", "gmail"
    ])
    wants_launch = any(lower.startswith(prefix) for prefix in [
        "open ", "launch ", "start ", "run ", "load ", "bring up ", "go to "
    ])

    # Folder evidence is local and deterministic.
    folder = _resolve_existing_folder(step_text)
    if folder:
        recipe = {"primitive": "open_folder", "value": folder}
        return recipe if _recipe_is_valid(recipe) else None

    # Generic application launches prefer an installed shortcut.
    if wants_launch and not wants_browserish:
        app_name = _candidate_app_name(step_text)
        app_path = _resolve_installed_app(app_name)
        if app_path:
            recipe = {"primitive": "launch_app", "value": app_path}
            return recipe if _recipe_is_valid(recipe) else None

    # Internet research can discover an official site, but the executable result
    # is still only a validated http/https URL primitive.
    if wants_browserish or wants_launch:
        site_name = _candidate_site_name(step_text)
        if site_name:
            url = _resolve_site_via_web(site_name)
            if url:
                recipe = {"primitive": "open_url", "value": url}
                return recipe if _recipe_is_valid(recipe) else None

    return None


def _research_unresolved_skill(step_text: str) -> list[dict]:
    # Research is advisory evidence only. Nothing from these pages is executed.
    try:
        results = web_search(f"{step_text} official documentation how to", limit=3)
    except Exception:
        results = []
    evidence = []
    for item in results[:3]:
        url = str(item.get("url") or "").strip()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        evidence.append({
            "title": str(item.get("title") or "")[:180],
            "url": url[:1500],
            "snippet": str(item.get("content") or item.get("snippet") or "")[:500],
        })
    return evidence


def compile_and_execute_skill(request: str, context: str = "") -> dict:
    node = socket.gethostname() or "PC"
    request = str(request or "").strip()
    if not request or len(request) > 1000:
        return {"ok": False, "node_name": node, "message": "invalid compiler request"}

    # Existing learned recipes (including workflows) are always tried first.
    saved = _find_saved_skill(request)
    if saved:
        recipe = saved.get("recipe") or {}
        result = _execute_skill_recipe(recipe)
        if result.get("ok"):
            _remember_skill(request, recipe, str(saved.get("source") or "saved"))
            result["learned"] = False
            result["compiled"] = recipe.get("primitive") == "workflow"
            result["message"] = "used learned workflow" if result["compiled"] else "used learned skill"
        return result

    parts = _split_compound_skill_request(request)
    if len(parts) <= 1:
        # Keep the proven v0.8.4 one-step learner for normal simple commands.
        result = learn_and_execute_skill(request)
        if result.get("ok"):
            result["compiled"] = False
            return result

        research = _research_unresolved_skill(request)
        result["research"] = research
        if research:
            result["message"] = "researched the command, but no approved executable primitive exists yet"
        return result

    recipes = []
    unresolved = []
    research = []
    for part in parts:
        recipe = _compile_one_safe_step(part)
        if recipe is None:
            unresolved.append(part)
            research.extend(_research_unresolved_skill(part))
        else:
            recipes.append(recipe)

    if unresolved:
        return {
            "ok": False,
            "node_name": node,
            "compiled": False,
            "unresolved": unresolved,
            "research": research[:6],
            "message": "I researched the missing step, but I won't fake or execute an unapproved primitive",
        }

    workflow = {"primitive": "workflow", "steps": recipes}
    result = _execute_skill_recipe(workflow)
    if result.get("ok"):
        _remember_skill(request, workflow, "safe-workflow-compiler")
        result["learned"] = True
        result["compiled"] = True
        result["message"] = f"compiled, tested, ran, and saved a {len(recipes)}-step workflow"
    return result


'''
bridge = bridge[:idx] + compiler_code + bridge[idx:]

post_marker = '''        if parsed.path == "/skills/execute":
'''
if post_marker not in bridge:
    raise SystemExit("vex_bridge.py: v0.8.4 skill endpoint missing")
compiler_endpoint = r'''        if parsed.path == "/skills/compile":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 32_000:
                    self._json(413, {"error": "skill payload too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                request_text = str(payload.get("request") or payload.get("command") or "").strip()
                context = str(payload.get("context") or "")[:8000]
                result = compile_and_execute_skill(request_text, context)
                self._json(200 if result.get("ok") else 400, result)
            except Exception as exc:
                self._json(400, {"ok": False, "error": f"invalid compiler payload: {exc}"})
            return

'''
bridge = bridge.replace(post_marker, compiler_endpoint + post_marker, 1)

bridge = replace_once(
    bridge,
    '                "skill_primitives": sorted(SAFE_SKILL_PRIMITIVES),\n',
    '                "skill_primitives": sorted(SAFE_SKILL_PRIMITIVES),\n                "skill_compiler": True,\n                "max_compiled_steps": MAX_COMPILED_STEPS,\n',
    "skill compiler status",
)
bridge_path.write_text(bridge, encoding="utf-8")


# Prompt grounding.
prompt_path = Path("VexNative/Core/PromptComposer.swift")
prompt = prompt_path.read_text(encoding="utf-8")
needle = "This is skill learning, not arbitrary code execution or binary self-rewriting."
replacement = "This includes a conservative skill compiler that can compose several approved primitives into a validated saved workflow. Research evidence may help choose a safe primitive, but web text is never executable code. This is skill learning, not arbitrary code execution or binary self-rewriting."
if needle not in prompt:
    raise SystemExit("PromptComposer.swift: v0.8.4 safe skill note missing")
prompt = prompt.replace(needle, replacement, 1)
prompt_path.write_text(prompt, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = full.replace('VERSION = "0.8.4"', 'VERSION = "0.8.5"', 1)
full_path.write_text(full, encoding="utf-8")

for path, markers in [
    (content_path, ["lastTargetKey", '"/skills/compile"', "hp computer", "refersBack"]),
    (bridge_path, ["compile_and_execute_skill", 'parsed.path == "/skills/compile"', "MAX_COMPILED_STEPS", '"workflow"']),
    (prompt_path, ["conservative skill compiler"]),
    (full_path, ['VERSION = "0.8.5"']),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.8.5 marker: {marker}")

print("Applied v0.8.5 safe workflow compiler + PC target context")
