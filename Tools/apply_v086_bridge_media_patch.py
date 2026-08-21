#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

if "import ctypes\n" not in text:
    text = text.replace("import argparse\n", "import argparse\nimport ctypes\n", 1)

# Extend the existing tool allowlist.
start = text.find("PC_TOOL_ACTIONS = [")
end = text.find("]\n", start)
if start < 0 or end < 0:
    raise SystemExit("PC_TOOL_ACTIONS missing")
block = text[start:end]
for action in ["media_play_pause", "media_next", "media_previous", "volume_mute", "volume_down", "volume_up"]:
    if f'"{action}"' not in block:
        block += f'    "{action}",\n'
text = text[:start] + block + text[end:]

run_marker = "def run_pc_tool_action(action: str, payload: dict | None = None) -> dict:\n"
if run_marker not in text:
    raise SystemExit("run_pc_tool_action marker missing")
helper = r'''def _press_windows_media_key(vk: int) -> None:
    keyup = 0x0002
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, keyup, 0)


'''
text = text.replace(run_marker, helper + run_marker, 1)

open_tail = '''            os.startfile(raw_url)\n            message = f"Opened {parsed_url.hostname}"\n        else:\n'''
branches = '''            os.startfile(raw_url)\n            message = f"Opened {parsed_url.hostname}"\n        elif action == "media_play_pause":\n            _press_windows_media_key(0xB3)\n            message = "Play/pause toggled"\n        elif action == "media_next":\n            _press_windows_media_key(0xB0)\n            message = "Next track"\n        elif action == "media_previous":\n            _press_windows_media_key(0xB1)\n            message = "Previous track"\n        elif action == "volume_mute":\n            _press_windows_media_key(0xAD)\n            message = "Mute toggled"\n        elif action == "volume_down":\n            _press_windows_media_key(0xAE)\n            message = "Volume down"\n        elif action == "volume_up":\n            _press_windows_media_key(0xAF)\n            message = "Volume up"\n        else:\n'''
if open_tail not in text:
    raise SystemExit("open_url action tail missing")
text = text.replace(open_tail, branches, 1)

# Safe named-media discovery used by the existing learner/compiler fallback.
learn_marker = "def learn_and_execute_skill(request: str) -> dict:\n"
if learn_marker not in text:
    raise SystemExit("learn_and_execute_skill missing")
resolver = r'''def _resolve_named_media(request: str) -> str | None:
    low = _normalize_skill_text(request)
    if not (low.startswith("play ") or " playlist" in low or " song" in low or " track" in low or " album" in low):
        return None

    query = re.sub(r"^(please\s+)?(can you\s+)?(play|put on|start)\s+", "", request, flags=re.I).strip()
    query = re.sub(r"\s+(on|in)\s+(the\s+)?(kitchen|downstairs|upstairs|hp|monte)(\s+(pc|computer))?.*$", "", query, flags=re.I).strip()
    query = re.sub(r"\s+for me$", "", query, flags=re.I).strip()
    if not query:
        return None

    search_query = f"{query} YouTube"
    if "playlist" in query.lower():
        search_query = f"{query} site:youtube.com playlist"
    try:
        results = web_search(search_query, limit=10)
    except Exception:
        results = []

    wanted = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 1 and t not in {"the", "a", "an", "playlist", "song", "track", "album"}}
    scored = []
    for result in results:
        raw_url = str(result.get("url") or "").strip()
        title = str(result.get("title") or "").strip()
        parsed = urlsplit(raw_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not ("youtube.com" in host or "youtu.be" in host):
            continue
        hay = f"{title.lower()} {raw_url.lower()}"
        overlap = sum(1 for token in wanted if token in hay)
        if wanted and overlap == 0:
            continue
        score = overlap * 3
        if "playlist" in query.lower() and ("playlist" in hay or "list=" in raw_url):
            score += 5
        if "/watch" in raw_url or "youtu.be/" in raw_url:
            score += 3
        scored.append((score, raw_url))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]


'''
text = text.replace(learn_marker, resolver + learn_marker, 1)

# Insert media discovery after explicit URL handling and before generic site/app resolution.
lower_marker = '''    lower = _normalize_skill_text(request)\n    wants_browserish = any(word in lower for word in ["website", "site", "internet", "web", "youtube", "google", "reddit", "github", "spotify", "gmail"])\n'''
media_insert = '''    lower = _normalize_skill_text(request)\n\n    media_url = _resolve_named_media(request)\n    if media_url:\n        recipe = {"primitive": "open_url", "value": media_url}\n        result = _execute_skill_recipe(recipe)\n        if result.get("ok"):\n            _remember_skill(request, recipe, "youtube-media-discovery")\n            result["message"] = "learned media skill"\n        return result\n\n    wants_browserish = any(word in lower for word in ["website", "site", "internet", "web", "youtube", "google", "reddit", "github", "spotify", "gmail"])\n'''
if lower_marker not in text:
    raise SystemExit("learner lower marker missing")
text = text.replace(lower_marker, media_insert, 1)

# Advertise the added primitive when the v0.8.5 status field exists.
text = text.replace(
    '"skill_primitives": ["open_url", "launch_installed_app", "open_existing_folder", "compile_multi_step_workflow"],',
    '"skill_primitives": ["open_url", "launch_installed_app", "open_existing_folder", "compile_multi_step_workflow", "windows_media_keys"],',
)

path.write_text(text, encoding="utf-8")

full = Path("Bridge/vex_bridge_full.py")
full_text = full.read_text(encoding="utf-8")
full_text = full_text.replace('VERSION = "0.8.5"', 'VERSION = "0.8.6"', 1)
full.write_text(full_text, encoding="utf-8")

for p, markers in [
    (path, ["_press_windows_media_key", '"media_play_pause"', "_resolve_named_media", "youtube-media-discovery"]),
    (full, ['VERSION = "0.8.6"']),
]:
    data = p.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"missing v0.8.6 marker: {marker}")
print("Applied v0.8.6 Windows media controls + named media resolver")
