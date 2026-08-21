#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str):
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)


# v0.9.0 Bridge adds two narrow capabilities:
# 1) no-cost neural TTS through edge-tts (reply text only leaves the LAN), and
# 2) named-media opening plus Windows media-session verification.
# No shell/PowerShell/downloaded-code execution is added.
if "import base64\n" not in text:
    text = text.replace("import argparse\n", "import argparse\nimport base64\nimport asyncio\n", 1)

# Add the named-media action to the existing allowlist.
start = text.find("PC_TOOL_ACTIONS = [")
end = text.find("]\n", start)
if start < 0 or end < 0:
    raise SystemExit("PC_TOOL_ACTIONS missing")
block = text[start:end]
if '"play_named_media"' not in block:
    block += '    "play_named_media",\n'
text = text[:start] + block + text[end:]

# Neural voice allowlist. The client cannot make the Bridge request arbitrary
# voice IDs or settings beyond these intentionally exposed choices.
state_marker = "\n\nclass BridgeState:\n"
if state_marker not in text:
    raise SystemExit("BridgeState marker missing")
helpers = r'''

NEURAL_TTS_VOICES = {
    "en-US-AvaMultilingualNeural",
    "en-US-EmmaMultilingualNeural",
    "en-US-JennyNeural",
    "en-US-AriaNeural",
    "en-US-MichelleNeural",
}


def _signed_setting(value: int, suffix: str) -> str:
    return f"{value:+d}{suffix}"


def synthesize_neural_tts(text_value: str, voice: str, rate: int = 0, pitch: int = 0) -> bytes:
    text_value = re.sub(r"\s+", " ", str(text_value or "")).strip()
    if not text_value or len(text_value) > 1800:
        raise ValueError("invalid speech text")
    if voice not in NEURAL_TTS_VOICES:
        raise ValueError("unsupported neural voice")
    rate = max(-30, min(30, int(rate)))
    pitch = max(-35, min(35, int(pitch)))

    import edge_tts
    communicate = edge_tts.Communicate(
        text_value,
        voice,
        rate=_signed_setting(rate, "%"),
        volume="+0%",
        pitch=_signed_setting(pitch, "Hz"),
    )
    chunks = []
    for chunk in communicate.stream_sync():
        if chunk.get("type") == "audio":
            data = chunk.get("data") or b""
            if data:
                chunks.append(data)
    audio = b"".join(chunks)
    if not audio:
        raise RuntimeError("neural speech returned no audio")
    if len(audio) > 4 * 1024 * 1024:
        raise RuntimeError("neural speech audio too large")
    return audio


def _media_terms(value: str) -> set[str]:
    ignored = {
        "the", "a", "an", "playlist", "song", "track", "album", "music", "video",
        "play", "put", "start", "called", "named", "youtube", "please", "can", "you",
        "on", "in", "for", "me", "pc", "computer", "kitchen", "downstairs", "upstairs",
        "ashley", "monte", "hp",
    }
    return {
        token for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) > 1 and token not in ignored
    }


def _clean_named_media_query(request: str) -> str:
    query = re.sub(r"\s+", " ", str(request or "")).strip()
    query = re.sub(r"^(please\s+)?(can you\s+)?(play|put on|start)\s+", "", query, flags=re.I).strip()
    query = re.sub(r"^playlist\s+(called|named)\s+", "", query, flags=re.I).strip()
    query = re.sub(r"\s+(on|in|to)\s+(the\s+)?(kitchen|downstairs|upstairs|ashley|monte|hp)(\s+(pc|computer))?.*$", "", query, flags=re.I).strip()
    query = re.sub(r"\s+for me$", "", query, flags=re.I).strip()
    return query


def _resolve_named_media_v090(request: str) -> dict | None:
    query = _clean_named_media_query(request)
    if not query:
        return None
    low_request = str(request or "").lower()
    wants_playlist = "playlist" in low_request
    search_query = f"{query} YouTube"
    if wants_playlist:
        search_query = f"{query} site:youtube.com playlist"
    try:
        results = web_search(search_query, limit=12)
    except Exception:
        results = []

    wanted = _media_terms(query)
    scored = []
    for item in results:
        raw_url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        parsed = urlsplit(raw_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not (host == "youtu.be" or host.endswith("youtube.com")):
            continue

        hay = f"{title} {raw_url}".lower()
        overlap = len(wanted & _media_terms(hay))
        if wanted and overlap == 0:
            continue

        score = overlap * 5
        if query.lower() in title.lower():
            score += 8
        if wants_playlist:
            if "list=" in raw_url:
                score += 12
            if "/watch" in raw_url or host == "youtu.be":
                score += 7
            elif "/playlist" in raw_url:
                score += 3
        elif "/watch" in raw_url or host == "youtu.be":
            score += 6
        scored.append((score, raw_url, title))

    if not scored:
        return None
    scored.sort(key=lambda row: row[0], reverse=True)
    _, url, title = scored[0]
    return {"url": url, "title": title or query, "query": query}


async def _windows_media_state_async() -> dict:
    try:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if session is None:
            return {}
        playback = session.get_playback_info()
        status_obj = playback.playback_status
        status = getattr(status_obj, "name", None) or str(status_obj)
        properties = await session.try_get_media_properties_async()
        title = str(getattr(properties, "title", "") or "").strip()
        artist = str(getattr(properties, "artist", "") or "").strip()
        source_app = str(getattr(session, "source_app_user_model_id", "") or "").strip()
        return {
            "status": status.lower(),
            "title": title,
            "artist": artist,
            "source_app": source_app,
        }
    except Exception:
        return {}


async def _windows_try_play_async() -> bool:
    try:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if session is None:
            return False
        return bool(await session.try_play_async())
    except Exception:
        return False


def _windows_media_state() -> dict:
    try:
        return asyncio.run(_windows_media_state_async())
    except Exception:
        return {}


def _windows_try_play() -> bool:
    try:
        return bool(asyncio.run(_windows_try_play_async()))
    except Exception:
        return False


def _media_state_changed(before: dict, after: dict) -> bool:
    if not after:
        return False
    if not before:
        return True
    return (
        str(after.get("title") or "").lower() != str(before.get("title") or "").lower()
        or str(after.get("source_app") or "").lower() != str(before.get("source_app") or "").lower()
        or str(after.get("status") or "").lower() != str(before.get("status") or "").lower()
    )


def _play_named_media(request: str) -> dict:
    node = socket.gethostname() or "PC"
    candidate = _resolve_named_media_v090(request)
    if candidate is None:
        return {
            "ok": False,
            "action": "play_named_media",
            "node_name": node,
            "message": "no sufficiently relevant YouTube media match found",
            "playback_verified": False,
        }

    raw_url = str(candidate["url"])
    parsed = urlsplit(raw_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (host == "youtu.be" or host.endswith("youtube.com")):
        return {
            "ok": False,
            "action": "play_named_media",
            "node_name": node,
            "message": "resolved media URL failed validation",
            "playback_verified": False,
        }

    before = _windows_media_state()
    try:
        os.startfile(raw_url)
    except Exception as exc:
        return {
            "ok": False,
            "action": "play_named_media",
            "node_name": node,
            "message": str(exc),
            "playback_verified": False,
        }

    wanted = _media_terms(candidate.get("query") or request)
    verified = False
    observed = {}
    tried_play = False

    # Give the browser time to load, then inspect the real Windows media session.
    # If the page loaded paused, try the safe SMTC play primitive once and verify again.
    for attempt in range(12):
        time.sleep(0.65 if attempt else 1.2)
        observed = _windows_media_state()
        status = str(observed.get("status") or "").lower()
        current_title = str(observed.get("title") or "")
        title_overlap = len(wanted & _media_terms(current_title)) if wanted else 0
        changed = _media_state_changed(before, observed)
        if "playing" in status and (title_overlap > 0 or changed):
            verified = True
            break
        if attempt >= 3 and not tried_play:
            tried_play = True
            _windows_try_play()

    return {
        "ok": True,
        "action": "play_named_media",
        "node_name": node,
        "message": "named media opened and playback verified" if verified else "named media opened; playback not verified",
        "playback_verified": verified,
        "media_title": str(observed.get("title") or candidate.get("title") or candidate.get("query") or "")[:240],
        "source_app": str(observed.get("source_app") or "")[:240],
        "resolved_url": raw_url,
    }

'''
text = text.replace(state_marker, helpers + state_marker, 1)

# Named media is a first-class allowlisted PC action, so it no longer depends on
# the generic skill learner or falls through to file search.
once(
    '''    try:
        if action == "show_desktop":
''',
    '''    try:
        if action == "play_named_media":
            return _play_named_media(str((payload or {}).get("query") or ""))
        if action == "show_desktop":
''',
    "named media action execution",
)

# Advertise neural speech support to the phone without exposing any secret config.
once(
    '                "tool_actions": PC_TOOL_ACTIONS,\n',
    '                "tool_actions": PC_TOOL_ACTIONS,\n                "neural_tts": True,\n                "neural_tts_voices": sorted(NEURAL_TTS_VOICES),\n                "media_playback_verification": True,\n',
    "Bridge status voice/media capabilities",
)

# Add the authenticated TTS endpoint before the existing skill/compiler handlers.
post_marker = '        if parsed.path == "/skills/compile":\n'
if post_marker not in text:
    raise SystemExit("skills compile POST marker missing")
tts_endpoint = r'''        if parsed.path == "/tts/speak":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 32_000:
                    self._json(413, {"ok": False, "error": "speech payload too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                speech_text = str(payload.get("text") or "").strip()
                voice = str(payload.get("voice") or "en-US-AvaMultilingualNeural").strip()
                rate = int(payload.get("rate") or 0)
                pitch = int(payload.get("pitch") or 0)
                audio = synthesize_neural_tts(speech_text, voice, rate, pitch)
                self._json(200, {
                    "ok": True,
                    "mime": "audio/mpeg",
                    "voice": voice,
                    "audio_base64": base64.b64encode(audio).decode("ascii"),
                })
            except Exception as exc:
                self._json(502, {"ok": False, "error": f"neural speech unavailable: {exc}"})
            return

'''
text = text.replace(post_marker, tts_endpoint + post_marker, 1)

path.write_text(text, encoding="utf-8")

# Version the packaged launcher while preserving the user's existing AppData config,
# token, cert, brain DB and learned skills.
full = Path("Bridge/vex_bridge_full.py")
full_text = full.read_text(encoding="utf-8")
if 'VERSION = "0.8.6"' not in full_text:
    raise SystemExit("Bridge full v0.8.6 version marker missing")
full_text = full_text.replace('VERSION = "0.8.6"', 'VERSION = "0.9.0"', 1)
full.write_text(full_text, encoding="utf-8")

for p, markers in [
    (path, [
        '"play_named_media"',
        "NEURAL_TTS_VOICES",
        'parsed.path == "/tts/speak"',
        "audio_base64",
        "_windows_media_state",
        "playback_verified",
        "_resolve_named_media_v090",
    ]),
    (full, ['VERSION = "0.9.0"']),
]:
    data = p.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"missing v0.9.0 Bridge marker: {marker}")
print("Applied v0.9.0 Bridge neural TTS + verified named media patch")
