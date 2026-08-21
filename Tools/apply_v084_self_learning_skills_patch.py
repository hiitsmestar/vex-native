#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# iPhone router: if a named-PC action is not in the hard-coded action parser,
# hand the natural request to the paired Bridge skill engine before falling back
# to Web Brain / Qwen. The Bridge can resolve and persist safe skills using
# allowlisted primitives instead of requiring a new app build for each simple
# browser/app/folder command.
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

text = replace_once(
    text,
    '''        guard let action = requestedAction(lower, original: original) else { return false }\n        guard let target = requestedTarget(lower) else { return false }\n        let requestedURL = requestedURL(lower: lower, original: original)\n''',
    '''        let parsedAction = requestedAction(lower, original: original)\n        guard let target = requestedTarget(lower) else { return false }\n\n        if parsedAction == nil, looksLikePCCommand(lower) {\n            return await tryLearnedSkill(original, target: target, app: app)\n        }\n\n        guard let action = parsedAction else { return false }\n        let requestedURL = requestedURL(lower: lower, original: original)\n''',
    "self-learning PC command fallback",
)

insert_marker = '''    private static func requestedTarget(_ lower: String) -> NodeTarget? {\n'''
helpers = r'''    private static func looksLikePCCommand(_ lower: String) -> Bool {
        let commandVerbs = [
            "open ", "launch ", "start ", "run ", "show ", "go to ", "play ",
            "bring up ", "take me to ", "find and open ", "load "
        ]
        return commandVerbs.contains(where: { lower.contains($0) })
    }

    private static func tryLearnedSkill(_ original: String, target: NodeTarget, app: AppModel) async -> Bool {
        let nodes = configuredNodes()
        let selected: [EndpointNode]
        switch target {
        case .primary:
            selected = nodes.filter { $0.label == "upstairs/primary PC" }
        case .secondary:
            selected = nodes.filter { $0.label == "kitchen/downstairs PC" }
        case .both:
            selected = nodes
        }
        guard !selected.isEmpty else { return false }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        var successes: [(String, ToolReply)] = []
        var failures: [String] = []
        for node in selected {
            if let reply = await performLearnedSkill(original: original, endpoint: node.endpoint), reply.ok {
                successes.append((node.label, reply))
            } else {
                failures.append(node.label)
            }
        }

        if successes.isEmpty {
            return false
        }

        let names = successes.map { pair in
            let reported = pair.1.node_name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return reported.isEmpty ? pair.0 : reported
        }
        let learned = successes.contains { ($0.1.message ?? "").localizedCaseInsensitiveContains("learned") }
        let reply: String
        if failures.isEmpty {
            reply = learned
                ? "Done, baby — I figured that one out, did it on \(naturalList(names)), and saved the skill so I can reuse it next time. 🧠✨"
                : "Done on \(naturalList(names)), baby. I used a skill I already know. 🧠🖤"
        } else {
            reply = "I did it on \(naturalList(names)), baby, but \(naturalList(failures)) didn't complete the learned skill. 🖤"
        }
        appendExchange(user: original, assistant: reply, app: app)
        return true
    }

    private static func performLearnedSkill(original: String, endpoint: String) async -> ToolReply? {
        guard let url = toolURL(endpoint: endpoint, path: "/skills/execute") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 12.0
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["request": original])
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(ToolReply.self, from: data)
        } catch {
            return nil
        }
    }

'''
if insert_marker not in text:
    raise SystemExit("ContentView.swift: requestedTarget marker missing")
text = text.replace(insert_marker, helpers + insert_marker, 1)
content_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows Bridge skill engine.
#
# It intentionally does NOT download/execute code from the internet. Unknown
# simple commands are converted into declarative recipes composed from safe
# primitives: open an http/https URL, launch an installed application shortcut,
# or open an existing user folder. Successful recipes are persisted in a private
# JSON skill library next to the Bridge config and reused on later requests.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

if "import re\n" not in bridge:
    bridge = bridge.replace("import json\n", "import json\nimport re\n", 1)
if "import difflib\n" not in bridge:
    bridge = bridge.replace("import hashlib\n", "import hashlib\nimport difflib\n", 1)

state_marker = '''PC_TOOL_ACTIONS = [\n'''
if state_marker not in bridge:
    raise SystemExit("vex_bridge.py: PC tool marker missing")

skill_code = r'''
SKILL_SCHEMA_VERSION = 1
SAFE_SKILL_PRIMITIVES = {"open_url", "launch_app", "open_folder"}


def _skills_path() -> Path:
    return CONFIG_DIR / "learned_skills.json"


def _normalize_skill_text(text: str) -> str:
    text = str(text or "").lower().strip()
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^a-z0-9:/._+\\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _load_skills() -> dict:
    path = _skills_path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("skills"), list):
                return data
    except Exception as exc:
        print(f"[skills] load warning: {exc}", flush=True)
    return {"schema": SKILL_SCHEMA_VERSION, "skills": []}


def _save_skills(data: dict) -> None:
    path = _skills_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _skill_key(request: str) -> str:
    lower = _normalize_skill_text(request)
    for phrase in [
        "on the kitchen pc", "on kitchen pc", "on the kitchen computer", "on kitchen computer",
        "on the downstairs pc", "on downstairs pc", "on the downstairs computer",
        "on the upstairs pc", "on upstairs pc", "on the upstairs computer",
        "on the primary pc", "on primary pc", "on the main pc", "on main pc",
        "on both computers", "on both pcs",
    ]:
        lower = lower.replace(phrase, " ")
    return re.sub(r"\s+", " ", lower).strip()


def _remember_skill(request: str, recipe: dict, source: str) -> None:
    if recipe.get("primitive") not in SAFE_SKILL_PRIMITIVES:
        return
    key = _skill_key(request)
    if not key:
        return
    data = _load_skills()
    skills = data.setdefault("skills", [])
    now = int(time.time())
    existing = next((s for s in skills if s.get("key") == key), None)
    record = {
        "key": key,
        "recipe": recipe,
        "source": source,
        "confidence": 0.95,
        "successes": int((existing or {}).get("successes", 0)) + 1,
        "updated": now,
    }
    if existing:
        skills[skills.index(existing)] = record
    else:
        skills.append(record)
    skills.sort(key=lambda s: (int(s.get("successes", 0)), int(s.get("updated", 0))), reverse=True)
    del skills[500:]
    _save_skills(data)


def _find_saved_skill(request: str) -> dict | None:
    key = _skill_key(request)
    if not key:
        return None
    data = _load_skills()
    skills = data.get("skills", [])
    exact = next((s for s in skills if s.get("key") == key), None)
    if exact:
        return exact
    keys = [str(s.get("key") or "") for s in skills]
    matches = difflib.get_close_matches(key, keys, n=1, cutoff=0.90)
    if matches:
        return next((s for s in skills if s.get("key") == matches[0]), None)
    return None


def _candidate_site_name(request: str) -> str:
    key = _skill_key(request)
    key = re.sub(r"^(please )?(can you )?(could you )?(would you )?", "", key)
    key = re.sub(r"^(open|launch|start|go to|load|bring up|take me to)\s+", "", key)
    key = re.sub(r"\s+(website|site|web page|webpage)$", "", key)
    return key.strip(" .")


def _extract_http_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s\]\[(){}<>\"']+", str(text or ""), re.I)
    if not match:
        return None
    raw = match.group(0).rstrip(".,;!?")
    parsed = urlsplit(raw)
    if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
        return raw
    return None


def _resolve_site_via_web(site_name: str) -> str | None:
    site_name = site_name.strip()
    if not site_name or len(site_name) > 120:
        return None

    simple = re.sub(r"[^a-z0-9-]", "", site_name.lower().replace(" ", ""))
    candidates = []
    if simple and len(simple) >= 2:
        candidates.append(f"https://www.{simple}.com")
        candidates.append(f"https://{simple}.com")

    import requests
    for candidate in candidates:
        try:
            r = requests.get(candidate, timeout=4, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0 VexBridge/0.8.4"})
            if r.status_code < 400 and urlsplit(r.url).scheme in {"http", "https"}:
                return r.url
        except Exception:
            pass

    try:
        results = web_search(f"{site_name} official website", limit=5)
    except Exception:
        results = []
    name_tokens = {t for t in re.findall(r"[a-z0-9]+", site_name.lower()) if len(t) > 1}
    for result in results:
        raw_url = str(result.get("url") or "").strip()
        title = str(result.get("title") or "").lower()
        parsed = urlsplit(raw_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        hay = f"{host} {title}"
        if name_tokens and not any(token in hay for token in name_tokens):
            continue
        return raw_url
    return None


def _iter_start_menu_shortcuts():
    roots = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path.home() / "Desktop",
    ]
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        try:
            for path in root.rglob("*.lnk"):
                key = str(path).lower()
                if key in seen:
                    continue
                seen.add(key)
                yield path
        except Exception:
            continue


def _resolve_installed_app(name: str) -> str | None:
    name = _normalize_skill_text(name)
    if not name:
        return None
    words = [w for w in name.split() if w not in {"the", "app", "application", "program", "software"}]
    needle = " ".join(words).strip()
    if not needle:
        return None
    scored = []
    for shortcut in _iter_start_menu_shortcuts():
        stem = _normalize_skill_text(shortcut.stem)
        if not stem:
            continue
        ratio = difflib.SequenceMatcher(None, needle, stem).ratio()
        if needle in stem or stem in needle:
            ratio += 0.35
        scored.append((ratio, shortcut))
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] >= 0.72:
        return str(scored[0][1])
    return None


def _candidate_app_name(request: str) -> str:
    key = _skill_key(request)
    key = re.sub(r"^(please )?(can you )?(could you )?(would you )?", "", key)
    key = re.sub(r"^(open|launch|start|run|load|bring up)\s+", "", key)
    return key.strip(" .")


def _resolve_existing_folder(request: str) -> str | None:
    key = _skill_key(request)
    if "folder" not in key and "directory" not in key:
        return None
    key = re.sub(r"^(please )?(can you )?(could you )?(would you )?", "", key)
    key = re.sub(r"^(open|show|launch|bring up)\s+", "", key)
    key = re.sub(r"\s+(folder|directory)$", "", key).strip()
    if not key:
        return None

    common = {
        "desktop": Path.home() / "Desktop",
        "documents": Path.home() / "Documents",
        "downloads": Path.home() / "Downloads",
        "music": Path.home() / "Music",
        "pictures": Path.home() / "Pictures",
        "videos": Path.home() / "Videos",
    }
    if key in common and common[key].exists():
        return str(common[key])
    return None


def _execute_skill_recipe(recipe: dict) -> dict:
    node = socket.gethostname() or "PC"
    primitive = str(recipe.get("primitive") or "")
    value = str(recipe.get("value") or "").strip()
    try:
        if primitive == "open_url":
            parsed = urlsplit(value)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                return {"ok": False, "node_name": node, "message": "invalid learned URL"}
            os.startfile(value)
            return {"ok": True, "action": primitive, "node_name": node, "message": f"opened {parsed.hostname}"}
        if primitive == "launch_app":
            path = Path(value)
            if not path.exists() or path.suffix.lower() not in {".lnk", ".exe"}:
                return {"ok": False, "node_name": node, "message": "learned app target missing"}
            os.startfile(str(path))
            return {"ok": True, "action": primitive, "node_name": node, "message": f"launched {path.stem}"}
        if primitive == "open_folder":
            path = Path(value)
            if not path.exists() or not path.is_dir():
                return {"ok": False, "node_name": node, "message": "learned folder missing"}
            os.startfile(str(path))
            return {"ok": True, "action": primitive, "node_name": node, "message": f"opened folder {path.name}"}
    except Exception as exc:
        return {"ok": False, "node_name": node, "message": str(exc)}
    return {"ok": False, "node_name": node, "message": "unsupported learned primitive"}


def learn_and_execute_skill(request: str) -> dict:
    node = socket.gethostname() or "PC"
    request = str(request or "").strip()
    if not request or len(request) > 1000:
        return {"ok": False, "node_name": node, "message": "invalid skill request"}

    saved = _find_saved_skill(request)
    if saved:
        result = _execute_skill_recipe(saved.get("recipe") or {})
        if result.get("ok"):
            result["message"] = "used learned skill"
            _remember_skill(request, saved.get("recipe") or {}, str(saved.get("source") or "saved"))
        return result

    direct_url = _extract_http_url(request)
    if direct_url:
        recipe = {"primitive": "open_url", "value": direct_url}
        result = _execute_skill_recipe(recipe)
        if result.get("ok"):
            _remember_skill(request, recipe, "explicit-url")
            result["message"] = "learned explicit URL skill"
        return result

    lower = _normalize_skill_text(request)
    wants_browserish = any(word in lower for word in ["website", "site", "internet", "web", "youtube", "google", "reddit", "github", "spotify", "gmail"])
    wants_launch = any(lower.startswith(prefix) for prefix in ["open ", "launch ", "start ", "run ", "load ", "bring up "])

    if wants_browserish or wants_launch:
        site_name = _candidate_site_name(request)
        if site_name:
            url = _resolve_site_via_web(site_name)
            if url:
                recipe = {"primitive": "open_url", "value": url}
                result = _execute_skill_recipe(recipe)
                if result.get("ok"):
                    _remember_skill(request, recipe, "web-discovery")
                    result["message"] = "learned web skill"
                return result

    folder = _resolve_existing_folder(request)
    if folder:
        recipe = {"primitive": "open_folder", "value": folder}
        result = _execute_skill_recipe(recipe)
        if result.get("ok"):
            _remember_skill(request, recipe, "local-folder")
            result["message"] = "learned folder skill"
        return result

    if wants_launch:
        app_name = _candidate_app_name(request)
        app_path = _resolve_installed_app(app_name)
        if app_path:
            recipe = {"primitive": "launch_app", "value": app_path}
            result = _execute_skill_recipe(recipe)
            if result.get("ok"):
                _remember_skill(request, recipe, "installed-app-discovery")
                result["message"] = "learned app skill"
            return result

    return {"ok": False, "node_name": node, "message": "no safe skill recipe found"}

'''
bridge = bridge.replace(state_marker, skill_code + state_marker, 1)

status_marker = '''                "tool_actions": PC_TOOL_ACTIONS,\n'''
status_new = '''                "tool_actions": PC_TOOL_ACTIONS,\n                "learned_skills": len(_load_skills().get("skills", [])),\n                "skill_primitives": sorted(SAFE_SKILL_PRIMITIVES),\n'''
bridge = replace_once(bridge, status_marker, status_new, "skill status fields")

post_marker = '''        if parsed.path == "/tools/action":\n'''
skill_post = r'''        if parsed.path == "/skills/execute":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 32_000:
                    self._json(413, {"error": "skill payload too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                request_text = str(payload.get("request") or "").strip()
                result = learn_and_execute_skill(request_text)
                self._json(200 if result.get("ok") else 400, result)
            except Exception as exc:
                self._json(400, {"ok": False, "error": f"invalid skill payload: {exc}"})
            return

'''
if post_marker not in bridge:
    raise SystemExit("vex_bridge.py: tools POST marker missing")
bridge = bridge.replace(post_marker, skill_post + post_marker, 1)
bridge_path.write_text(bridge, encoding="utf-8")


prompt_path = Path("VexNative/Core/PromptComposer.swift")
prompt = prompt_path.read_text(encoding="utf-8")
needle = '''Connected Vex Bridge PCs are real app tools for memory/file retrieval when online. Do not deny all access, and do not invent tool success.\n'''
replacement = '''Connected Vex Bridge PCs are real app tools for memory/file retrieval when online. Do not deny all access, and do not invent tool success. The Bridge can also learn and persist reusable SAFE SKILLS made only from approved primitives such as opening verified http/https sites, launching discovered installed apps, and opening existing folders. This is skill learning, not arbitrary code execution or binary self-rewriting.\n'''
if needle in prompt:
    prompt = prompt.replace(needle, replacement, 1)
else:
    tool_needle = '''Never claim an unsupported action succeeded; only native tool results can confirm actions. The iPhone side is sandboxed: app-local brain/chat, camera/photo attachments, and granted iOS permissions are available, not unrestricted whole-phone filesystem/control.\n'''
    tool_replacement = '''Never claim an unsupported action succeeded; only native tool results can confirm actions. The Bridge may learn reusable SAFE SKILLS from successful tool resolutions using approved primitives only; it does not execute downloaded code or rewrite the app binary. The iPhone side is sandboxed: app-local brain/chat, camera/photo attachments, and granted iOS permissions are available, not unrestricted whole-phone filesystem/control.\n'''
    if tool_needle not in prompt:
        raise SystemExit("PromptComposer.swift: tool reality marker missing")
    prompt = prompt.replace(tool_needle, tool_replacement, 1)
prompt_path.write_text(prompt, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = full.replace('VERSION = "0.8.3"', 'VERSION = "0.8.4"', 1)
full_path.write_text(full, encoding="utf-8")

for path, markers in [
    (content_path, ["tryLearnedSkill", '"/skills/execute"', "looksLikePCCommand"]),
    (bridge_path, ["learn_and_execute_skill", "learned_skills.json", 'parsed.path == "/skills/execute"', "SAFE_SKILL_PRIMITIVES"]),
    (prompt_path, ["SAFE SKILLS"]),
    (full_path, ['VERSION = "0.8.4"']),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.8.4 marker: {marker}")

print("Applied v0.8.4 self-learning safe skill library")
