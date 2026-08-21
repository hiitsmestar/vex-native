#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)

# iPhone: improve named-PC resolution and compile unknown commands through the
# safe skill planner before giving up to WebBrain/Qwen.
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

# Persist last explicit PC target and accept location-only aliases.
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
        if ["kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer", "second pc",
            "in the kitchen", "to the kitchen", "downstairs", "hp computer", "hp pc"]
            .contains(where: { lower.contains($0) }) {
            UserDefaults.standard.set("secondary", forKey: lastTargetKey)
            return .secondary
        }
        if ["upstairs pc", "upstairs computer", "primary pc", "main pc",
            "upstairs", "monte computer", "monte pc"]
            .contains(where: { lower.contains($0) }) {
            UserDefaults.standard.set("primary", forKey: lastTargetKey)
            return .primary
        }

        let refersBack = lower.contains(" on it") || lower.contains(" on that") ||
            lower.contains(" that computer") || lower.contains(" that pc") || lower.hasSuffix(" there")
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
text = replace_once(text, old_target, new_target, "v0.8.5 target alias/context")

# Upgrade learned-skill endpoint to compiler endpoint and send recent context.
old_skill_call = r'''    private static func tryLearnedSkill(_ original: String, lower: String, app: AppModel) async -> Bool {
'''
new_skill_call = r'''    private static func tryLearnedSkill(_ original: String, lower: String, app: AppModel) async -> Bool {
'''
# marker stays the same, but we patch body pieces below
if old_skill_call not in text:
    raise SystemExit("ContentView.swift: learned skill function marker missing")

text = text.replace(
    'guard let url = toolURL(endpoint: node.endpoint, path: "/skills/execute") else { continue }',
    'guard let url = toolURL(endpoint: node.endpoint, path: "/skills/compile") else { continue }',
)
text = text.replace(
    'request.httpBody = try? JSONSerialization.data(withJSONObject: ["command": original])',
    'let recentContext = app.profile.messages.suffix(6).map { "\\($0.role.rawValue): \\($0.content)" }.joined(separator: "\\n")\n            request.httpBody = try? JSONSerialization.data(withJSONObject: ["command": original, "context": recentContext])',
)
text = text.replace(
    'let message = decoded.message ?? "I learned how to do that on \\(decoded.node_name ?? node.label), baby. 🧠🖤"',
    'let message = decoded.message ?? "I figured that out on \\(decoded.node_name ?? node.label), saved the workflow, and ran it, baby. 🧠⚡🖤"',
)

# Treat location-only wording as an attempt to use a named PC so it reaches the compiler.
text = text.replace(
    'let mentionsPC = lower.contains(" pc") || lower.contains("computer") || lower.contains("downstairs") || lower.contains("upstairs")',
    'let mentionsPC = lower.contains(" pc") || lower.contains("computer") || lower.contains("downstairs") || lower.contains("upstairs") || lower.contains("kitchen") || lower.contains("hp")',
)

content_path.write_text(text, encoding="utf-8")

# Windows Bridge: add a small workflow compiler over safe primitives. It can
# discover installed apps, folders, and http/https sites, combine several steps,
# dry-validate them, execute, and persist successful workflows. No shell/code.
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

insert_marker = "def learn_and_execute_skill(command: str) -> dict:\n"
idx = bridge.find(insert_marker)
if idx < 0:
    raise SystemExit("vex_bridge.py: v0.8.4 skill function missing")

compiler_code = r'''

MAX_COMPILED_STEPS = 6


def _split_compound_command(command: str) -> list[str]:
    text = re.sub(r"\s+", " ", command.strip())
    # Keep this intentionally conservative. We split only on obvious sequential
    # connectors and cap the number of steps.
    parts = re.split(r"\s+(?:and then|then|and also|after that)\s+", text, flags=re.I)
    return [p.strip(" ,.;") for p in parts if p.strip(" ,.;")][:MAX_COMPILED_STEPS]


def _infer_primitive(step_text: str) -> dict | None:
    low = step_text.lower()

    # Existing folders are local evidence, not guesses.
    folder_names = {
        "desktop": "Desktop",
        "documents": "Documents",
        "downloads": "Downloads",
        "music": "Music",
        "pictures": "Pictures",
        "videos": "Videos",
    }
    for token, folder in folder_names.items():
        if token in low and any(v in low for v in ("open", "show", "go to", "launch")):
            target = _existing_user_folder(folder)
            if target.exists():
                return {"kind": "folder", "value": str(target), "label": folder}

    # Installed app discovery from local shortcuts first.
    if any(v in low for v in ("open", "launch", "start", "run")):
        app = _discover_installed_app(step_text)
        if app:
            return {"kind": "app", "value": app["path"], "label": app["name"]}

    # Explicit URLs are accepted only for http/https.
    explicit = re.search(r"https?://[^\s]+", step_text, flags=re.I)
    if explicit:
        url = explicit.group(0).rstrip(",.;!?)\"]}")
        parsed = urlsplit(url)
        if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
            return {"kind": "url", "value": url, "label": parsed.hostname}

    # Site discovery is research, but execution stays a safe URL primitive.
    if any(v in low for v in ("open", "go to", "visit", "browse", "website", "site")):
        discovered = _discover_site_url(step_text)
        if discovered:
            return {"kind": "url", "value": discovered["url"], "label": discovered.get("title") or discovered["url"]}

    return None


def _validate_compiled_step(step: dict) -> bool:
    kind = step.get("kind")
    value = str(step.get("value") or "")
    if kind == "app":
        p = Path(value)
        return p.exists() and p.suffix.lower() in {".lnk", ".exe", ".url", ".appref-ms"}
    if kind == "folder":
        p = Path(value)
        return p.exists() and p.is_dir()
    if kind == "url":
        parsed = urlsplit(value)
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)
    return False


def _execute_compiled_step(step: dict) -> None:
    kind = step["kind"]
    value = step["value"]
    if kind in {"app", "folder", "url"}:
        os.startfile(value)
        return
    raise ValueError("unsupported compiled primitive")


def compile_skill_workflow(command: str, context: str = "") -> dict:
    node = socket.gethostname() or "PC"
    command = re.sub(r"\s+", " ", (command or "").strip())[:1000]
    if not command:
        return {"ok": False, "node_name": node, "message": "empty command"}

    # First reuse an already learned skill if it is a close command match.
    saved = load_learned_skills()
    key = normalize_skill_key(command)
    cached = saved.get(key)
    if cached and cached.get("steps"):
        steps = cached["steps"]
        if all(_validate_compiled_step(s) for s in steps):
            try:
                for step in steps:
                    _execute_compiled_step(step)
                    time.sleep(0.08)
                cached["uses"] = int(cached.get("uses", 0)) + 1
                cached["last_used"] = int(time.time())
                saved[key] = cached
                save_learned_skills(saved)
                return {"ok": True, "learned": False, "compiled": True, "node_name": node,
                        "steps": steps, "message": f"Done on {node} — I reused a learned {len(steps)}-step workflow. 🧠⚡"}
            except Exception as exc:
                return {"ok": False, "node_name": node, "message": f"saved workflow failed validation/execution: {exc}"}

    parts = _split_compound_command(command)
    steps = []
    for part in parts:
        primitive = _infer_primitive(part)
        if primitive is None:
            # If a single-step compiler cannot resolve the whole command, fall
            # back to the v0.8.4 learner once. That can still resolve an app/site/folder.
            if len(parts) == 1:
                legacy = learn_and_execute_skill(command)
                if legacy.get("ok"):
                    return legacy
            return {"ok": False, "node_name": node,
                    "message": f"I couldn't safely compile this step yet: {part}"}
        if not _validate_compiled_step(primitive):
            return {"ok": False, "node_name": node, "message": f"A proposed step did not validate: {part}"}
        steps.append(primitive)

    if not steps:
        return {"ok": False, "node_name": node, "message": "No safe workflow steps were found"}

    try:
        for step in steps:
            _execute_compiled_step(step)
            time.sleep(0.08)
    except Exception as exc:
        return {"ok": False, "node_name": node, "message": f"compiled workflow execution failed: {exc}"}

    saved[key] = {
        "command": command,
        "steps": steps,
        "uses": 1,
        "created": int(time.time()),
        "last_used": int(time.time()),
        "source": "safe_compiler",
    }
    save_learned_skills(saved)
    labels = ", then ".join(str(s.get("label") or s.get("kind")) for s in steps)
    return {"ok": True, "learned": True, "compiled": True, "node_name": node, "steps": steps,
            "message": f"I figured out a safe {len(steps)}-step workflow on {node}, ran it, and saved it: {labels}. 🧠⚡"}

'''
bridge = bridge[:idx] + compiler_code + bridge[idx:]

# Add compiler endpoint alongside v0.8.4 execute endpoint.
post_marker = '''        if parsed.path == "/skills/execute":
'''
if post_marker not in bridge:
    raise SystemExit("vex_bridge.py: /skills/execute endpoint missing")
compiler_endpoint = '''        if parsed.path == "/skills/compile":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 32_000:
                    self._json(413, {"error": "skill payload too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                command = str(payload.get("command") or "").strip()
                context = str(payload.get("context") or "")[:8000]
                result = compile_skill_workflow(command, context)
                self._json(200 if result.get("ok") else 400, result)
            except Exception as exc:
                self._json(400, {"ok": False, "error": f"invalid compiler payload: {exc}"})
            return

'''
bridge = bridge.replace(post_marker, compiler_endpoint + post_marker, 1)

# Advertise compiler in status and approved primitives.
bridge = bridge.replace(
    '"skill_primitives": ["open_url", "launch_installed_app", "open_existing_folder"],',
    '"skill_primitives": ["open_url", "launch_installed_app", "open_existing_folder", "compile_multi_step_workflow"],',
)
bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = full.replace('VERSION = "0.8.4"', 'VERSION = "0.8.5"', 1)
full_path.write_text(full, encoding="utf-8")

# Prompt note: model should not pretend it executed compiled skills; native router confirms them.
prompt_path = Path("VexNative/Core/PromptComposer.swift")
prompt = prompt_path.read_text(encoding="utf-8")
prompt = prompt.replace(
    "A Bridge may learn reusable safe skills from verified websites, installed app shortcuts, and existing folders. Do not claim arbitrary code execution or unsupported self-modification.",
    "A Bridge may learn reusable safe skills from verified websites, installed app shortcuts, and existing folders, and can compile several approved primitives into a persisted workflow. Native tool results confirm execution. Do not claim arbitrary code execution, downloaded-code execution, or app-binary self-modification.",
)
prompt_path.write_text(prompt, encoding="utf-8")

for path, markers in [
    (content_path, ["lastTargetKey", "/skills/compile", "kitchen", "refersBack"]),
    (bridge_path, ["compile_skill_workflow", 'parsed.path == "/skills/compile"', "MAX_COMPILED_STEPS"]),
    (full_path, ['VERSION = "0.8.5"']),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.8.5 marker {marker}")

print("Applied v0.8.5 safe skill compiler + PC target context")
