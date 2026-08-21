#!/usr/bin/env python3
from pathlib import Path
import re


bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

# Dependencies used by the v0.9.0 resolver. Keep execution declarative: no shell,
# PowerShell, downloaded scripts, or arbitrary program execution is introduced.
if "import asyncio\n" not in bridge:
    bridge = bridge.replace("import argparse\n", "import argparse\nimport asyncio\n", 1)
if "import shutil\n" not in bridge:
    bridge = bridge.replace("import secrets\n", "import secrets\nimport shutil\n", 1)
if "import sqlite3\n" not in bridge:
    bridge = bridge.replace("import ssl\n", "import ssl\nimport sqlite3\n", 1)
if "import tempfile\n" not in bridge:
    bridge = bridge.replace("import threading\n", "import tempfile\nimport threading\n", 1)


# ---------------------------------------------------------------------------
# Natural voice backend: Microsoft Edge neural speech through the free edge-tts
# client. This is optional at runtime; the iPhone falls back to its best local
# AVSpeech voice if neither Bridge can synthesize a reply.
# ---------------------------------------------------------------------------
tool_marker = "PC_TOOL_ACTIONS = [\n"
if tool_marker not in bridge:
    raise SystemExit("vex_bridge.py: PC_TOOL_ACTIONS marker missing")

helpers = r'''
VEX_TTS_VOICES = [
    "en-US-AvaNeural",
    "en-US-JennyNeural",
    "en-US-AriaNeural",
]


def synthesize_vex_voice(text: str) -> tuple[bytes, str]:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text or len(text) > 5000:
        raise ValueError("invalid TTS text")

    async def _run() -> tuple[bytes, str]:
        import edge_tts
        last_error = None
        for voice in VEX_TTS_VOICES:
            try:
                communicate = edge_tts.Communicate(
                    text=text,
                    voice=voice,
                    rate="+4%",
                    volume="+0%",
                    pitch="+0Hz",
                )
                chunks = []
                async for chunk in communicate.stream():
                    if chunk.get("type") == "audio" and chunk.get("data"):
                        chunks.append(chunk["data"])
                if chunks:
                    return b"".join(chunks), voice
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"neural TTS unavailable: {last_error}")

    return asyncio.run(_run())


MEDIA_STOP_WORDS = {
    "a", "an", "the", "please", "play", "playing", "put", "on", "start",
    "called", "named", "playlist", "song", "track", "album", "music", "for",
    "me", "my", "some", "youtube", "video", "videos", "pc", "computer",
    "kitchen", "downstairs", "upstairs", "monte", "ashley", "hp",
}


def _media_tokens(text: str) -> list[str]:
    return [
        token for token in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(token) > 1 and token not in MEDIA_STOP_WORDS
    ]


def _parse_media_request(request: str) -> tuple[str, str]:
    raw = re.sub(r"\s+", " ", str(request or "")).strip()
    low = raw.lower()
    if "playlist" in low:
        kind = "playlist"
    elif "album" in low:
        kind = "album"
    elif "song" in low or "track" in low:
        kind = "song"
    else:
        kind = "media"

    query = re.sub(
        r"^(?:please\s+)?(?:can you\s+|could you\s+|would you\s+)?(?:play|put on|start playing|start)\s+",
        "",
        raw,
        flags=re.I,
    )

    # Remove PC-location language without teaching one literal utterance. The
    # iPhone has already selected the target node before this reaches the Bridge.
    location_phrases = [
        "on the kitchen pc", "on kitchen pc", "on the kitchen computer", "in the kitchen",
        "on the downstairs pc", "on downstairs pc", "on the downstairs computer", "downstairs",
        "on the upstairs pc", "on upstairs pc", "on the upstairs computer", "upstairs",
        "on the primary pc", "on primary pc", "on the main pc", "on main pc",
        "on the hp pc", "on hp pc", "on the hp computer", "on hp computer",
        "on monte pc", "on the monte pc", "on ashley pc", "on the ashley pc",
    ]
    for phrase in location_phrases:
        query = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", query, flags=re.I)
    query = re.sub(r"\s+", " ", query).strip(" ,.;:-")

    called = re.search(r"\b(?:called|named)\s+(.+)$", query, flags=re.I)
    if called:
        query = called.group(1).strip(" ,.;:-")
    else:
        query = re.sub(r"\b(?:playlist|song|track|album)\b", " ", query, flags=re.I)
        query = re.sub(r"\s+", " ", query).strip(" ,.;:-")

    return query, kind


def _youtube_url(raw_url: str) -> bool:
    try:
        parsed = urlsplit(str(raw_url or "").strip())
        host = (parsed.hostname or "").lower()
        return parsed.scheme in {"http", "https"} and (
            host == "youtu.be" or host.endswith("youtube.com")
        )
    except Exception:
        return False


def _playlist_url(raw_url: str) -> bool:
    try:
        parsed = urlsplit(raw_url)
        query = urllib.parse.parse_qs(parsed.query)
        return parsed.path.startswith("/playlist") or bool(query.get("list"))
    except Exception:
        return False


def _score_media_candidate(query: str, kind: str, title: str, raw_url: str) -> float | None:
    if not _youtube_url(raw_url):
        return None
    if kind == "playlist" and not _playlist_url(raw_url):
        return None

    wanted = _media_tokens(query)
    if not wanted:
        return None
    decoded_url = urllib.parse.unquote_plus(raw_url)
    hay = f"{title} {decoded_url}".lower()
    overlap = sum(1 for token in wanted if token in hay)
    required = min(2, len(wanted))
    if overlap < required:
        return None

    normalized_query = " ".join(wanted)
    normalized_title = " ".join(_media_tokens(title))
    score = overlap * 6.0
    if normalized_query and normalized_query in normalized_title:
        score += 8.0
    if kind == "playlist" and _playlist_url(raw_url):
        score += 7.0
    if "/watch" in raw_url or "youtu.be/" in raw_url:
        score += 1.5
    return score


def _walk_bookmark_nodes(node, results: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        if node.get("type") == "url":
            url = str(node.get("url") or "")
            if _youtube_url(url):
                results.append((str(node.get("name") or ""), url))
        for value in node.values():
            _walk_bookmark_nodes(value, results)
    elif isinstance(node, list):
        for value in node:
            _walk_bookmark_nodes(value, results)


def _browser_profiles() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roots = [
        local / "Google/Chrome/User Data",
        local / "Microsoft/Edge/User Data",
    ]
    profiles = []
    for root in roots:
        if not root.exists():
            continue
        default = root / "Default"
        if default.exists():
            profiles.append(default)
        try:
            profiles.extend(sorted(root.glob("Profile *")))
        except Exception:
            pass
    return profiles


def _local_browser_media_candidates(limit: int = 5000) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    seen = set()

    for profile in _browser_profiles():
        bookmarks = profile / "Bookmarks"
        if bookmarks.exists():
            try:
                data = json.loads(bookmarks.read_text(encoding="utf-8"))
                found: list[tuple[str, str]] = []
                _walk_bookmark_nodes(data, found)
                for title, url in found:
                    key = url.lower()
                    if key not in seen:
                        seen.add(key)
                        results.append((title, url))
            except Exception:
                pass

        history = profile / "History"
        if history.exists() and len(results) < limit:
            temp_path = None
            try:
                fd, temp_name = tempfile.mkstemp(prefix="vex-history-", suffix=".sqlite")
                os.close(fd)
                temp_path = Path(temp_name)
                shutil.copy2(history, temp_path)
                conn = sqlite3.connect(str(temp_path))
                try:
                    rows = conn.execute(
                        "SELECT title, url FROM urls ORDER BY last_visit_time DESC LIMIT 4000"
                    ).fetchall()
                finally:
                    conn.close()
                for title, url in rows:
                    url = str(url or "")
                    if not _youtube_url(url):
                        continue
                    key = url.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append((str(title or ""), url))
                    if len(results) >= limit:
                        break
            except Exception:
                pass
            finally:
                if temp_path is not None:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        pass

    return results[:limit]


def _best_exact_media(query: str, kind: str) -> tuple[str, str, str] | None:
    scored = []
    for title, url in _local_browser_media_candidates():
        score = _score_media_candidate(query, kind, title, url)
        if score is not None:
            scored.append((score + 4.0, title or query, url, "exact_local"))

    if scored:
        scored.sort(key=lambda row: row[0], reverse=True)
        _, title, url, source = scored[0]
        return title, url, source

    search_query = f'"{query}" YouTube {kind}'
    if kind == "playlist":
        search_query = f'"{query}" site:youtube.com playlist'
    try:
        web_results = web_search(search_query, limit=12)
    except Exception:
        web_results = []

    for rank, result in enumerate(web_results):
        title = str(result.get("title") or "")
        url = str(result.get("url") or "")
        score = _score_media_candidate(query, kind, title, url)
        if score is not None:
            scored.append((score - rank * 0.25, title or query, url, "exact_web"))

    if not scored:
        return None
    scored.sort(key=lambda row: row[0], reverse=True)
    _, title, url, source = scored[0]
    return title, url, source


def _visible_window_titles() -> list[str]:
    if not sys.platform.startswith("win"):
        return []
    titles: list[str] = []
    try:
        user32 = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        @callback_type
        def enum_window(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value.strip()
                if title:
                    titles.append(title)
            except Exception:
                pass
            return True

        user32.EnumWindows(enum_window, 0)
    except Exception:
        return []
    return titles


def _verify_media_window(query: str, timeout: float = 5.0) -> bool:
    wanted = _media_tokens(query)
    if not wanted:
        return False
    required = min(2, len(wanted))
    deadline = time.time() + timeout
    while time.time() < deadline:
        for title in _visible_window_titles():
            low = title.lower()
            if sum(1 for token in wanted if token in low) >= required:
                return True
        time.sleep(0.35)
    return False


def resolve_and_open_media(request: str) -> dict:
    node = socket.gethostname() or "PC"
    query, kind = _parse_media_request(request)
    if not query or not _media_tokens(query):
        return {
            "ok": False,
            "verified": False,
            "node_name": node,
            "kind": kind,
            "resolution": "unresolved",
            "message": "media title was empty or too vague",
        }

    exact = _best_exact_media(query, kind)
    if exact is not None:
        title, url, resolution = exact
        try:
            os.startfile(url)
        except Exception as exc:
            return {
                "ok": False,
                "verified": False,
                "node_name": node,
                "title": title,
                "url": url,
                "kind": kind,
                "resolution": resolution,
                "message": str(exc),
            }
        verified = _verify_media_window(query)
        return {
            "ok": True,
            "verified": verified,
            "node_name": node,
            "title": title,
            "url": url,
            "kind": kind,
            "resolution": resolution,
            "message": "matched media URL opened" if verified else "matched media URL opened; browser title not verified",
        }

    # A search page is useful progress, but it is not the requested playlist.
    # Return a distinct resolution so the phone can say exactly what happened.
    search_terms = query + (" playlist" if kind == "playlist" else "")
    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(search_terms)
    try:
        os.startfile(search_url)
        return {
            "ok": True,
            "verified": False,
            "node_name": node,
            "title": query,
            "url": search_url,
            "kind": kind,
            "resolution": "search_results",
            "message": "exact match not proven; opened YouTube search results",
        }
    except Exception as exc:
        return {
            "ok": False,
            "verified": False,
            "node_name": node,
            "title": query,
            "kind": kind,
            "resolution": "unresolved",
            "message": str(exc),
        }


'''
bridge = bridge.replace(tool_marker, helpers + tool_marker, 1)


# Binary response helper for MP3 speech. Authorization still happens before any
# POST route, so /tts uses the same private token + pinned TLS channel as tools.
authorized_marker = "    def _authorized(self, params: dict[str, list[str]]) -> bool:\n"
if authorized_marker not in bridge:
    raise SystemExit("vex_bridge.py: Handler authorization marker missing")

binary_method = r'''    def _bytes(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

'''
bridge = bridge.replace(authorized_marker, binary_method + authorized_marker, 1)


# Add authenticated TTS + named-media routes before the existing compiler/tool
# routes. Media is deliberately a dedicated evidence-returning action instead of
# pretending a generic learned-skill HTTP 200 proves playback.
post_marker = '        if parsed.path == "/skills/compile":\n'
if post_marker not in bridge:
    raise SystemExit("vex_bridge.py: skill compiler POST marker missing")

new_routes = r'''        if parsed.path == "/tts":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 40_000:
                    self._json(413, {"error": "TTS payload too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                text = str(payload.get("text") or "").strip()
                audio, voice = synthesize_vex_voice(text)
                print(f"[tts] node={socket.gethostname() or 'PC'} voice={voice} bytes={len(audio)}", flush=True)
                self._bytes(200, audio, "audio/mpeg")
            except Exception as exc:
                print(f"[tts] unavailable: {exc}", flush=True)
                self._json(503, {"ok": False, "error": "neural TTS unavailable"})
            return

        if parsed.path == "/media/play":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 32_000:
                    self._json(413, {"error": "media payload too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                request_text = str(payload.get("request") or "").strip()
                result = resolve_and_open_media(request_text)
                self._json(200 if result.get("ok") else 400, result)
            except Exception as exc:
                self._json(400, {"ok": False, "verified": False, "error": f"invalid media payload: {exc}"})
            return

'''
bridge = bridge.replace(post_marker, new_routes + post_marker, 1)

# Broaden the old safe-skill media recognizer too, so an older iPhone client can
# at least understand a noun-first request rather than searching random PC files.
bridge = bridge.replace(
    'if not (low.startswith("play ") or " playlist" in low or " song" in low or " track" in low or " album" in low):',
    'if not (low.startswith("play ") or low.startswith("playlist ") or low.startswith("song ") or low.startswith("track ") or low.startswith("album ") or " playlist" in low or " song" in low or " track" in low or " album" in low):',
)

# Advertise the capabilities without exposing any pairing material.
status_marker = '                "tool_actions": PC_TOOL_ACTIONS,\n'
if status_marker in bridge and '"neural_tts":' not in bridge:
    bridge = bridge.replace(
        status_marker,
        status_marker + '                "neural_tts": "edge",\n                "verified_media_resolver": True,\n',
        1,
    )

# Normalize the Bridge's public version strings after the sequential patches.
bridge = re.sub(r'server_version = "VexBridge/[0-9.]+"', 'server_version = "VexBridge/0.9.0"', bridge, count=1)
bridge = re.sub(r'"version": "[0-9.]+"', '"version": "0.9.0"', bridge, count=1)
bridge = re.sub(r'Mozilla/5\.0 VexBridge/[0-9.]+', 'Mozilla/5.0 VexBridge/0.9.0', bridge)
bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = re.sub(r'VERSION = "[0-9.]+"', 'VERSION = "0.9.0"', full, count=1)
full_path.write_text(full, encoding="utf-8")

for target, markers in [
    (bridge_path, [
        "synthesize_vex_voice",
        'parsed.path == "/tts"',
        "resolve_and_open_media",
        'parsed.path == "/media/play"',
        "_local_browser_media_candidates",
        "_verify_media_window",
        '"search_results"',
        '"neural_tts": "edge"',
        'server_version = "VexBridge/0.9.0"',
    ]),
    (full_path, ['VERSION = "0.9.0"']),
]:
    data = target.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{target}: missing v0.9.0 marker: {marker}")

print("Applied v0.9.0 Edge neural TTS + grounded/verified named-media Bridge patch")
