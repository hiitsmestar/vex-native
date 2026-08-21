#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")


def replace_function(name: str, replacement: str) -> None:
    global text
    start = text.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"function missing: {name}")
    candidates = [
        text.find("\ndef ", start + 5),
        text.find("\nasync def ", start + 5),
        text.find("\nclass ", start + 5),
    ]
    candidates = [value for value in candidates if value >= 0]
    if not candidates:
        raise SystemExit(f"function end missing: {name}")
    end = min(candidates)
    text = text[:start] + replacement.rstrip() + "\n\n" + text[end + 1:]


# ---------------------------------------------------------------------------
# Browser control helpers.
#
# v0.9.0 used os.startfile() for every YouTube navigation, which naturally made
# Chrome/Edge create more tabs while Star retried. v0.9.1 reuses the existing
# YouTube/browser window and navigates its current tab. It also reads the current
# address bar for phrases like "the first playlist on that channel".
# ---------------------------------------------------------------------------
marker = "\n\nNEURAL_TTS_VOICES = {"
if marker not in text:
    raise SystemExit("v0.9.0 neural helper marker missing")

browser_helpers = r'''

_BROWSER_CONTROL_LOCK = threading.Lock()
_MEDIA_ACTION_LOCK = threading.Lock()
_MEDIA_LAST = {"key": "", "at": 0.0, "result": None}


def _is_youtube_url(value: str) -> bool:
    try:
        parsed = urlsplit(str(value or "").strip())
        host = (parsed.hostname or "").lower()
        return parsed.scheme in {"http", "https"} and (host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com"))
    except Exception:
        return False


def _window_title(hwnd) -> str:
    try:
        user32 = ctypes.windll.user32
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip()
    except Exception:
        return ""


def _browser_windows() -> list[tuple[int, str]]:
    if not sys.platform.startswith("win"):
        return []
    user32 = ctypes.windll.user32
    results = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @callback_type
    def callback(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            title = _window_title(hwnd)
            low = title.lower()
            if title and any(token in low for token in ["youtube", "chrome", "edge", "firefox", "brave", "opera"]):
                results.append((int(hwnd), title))
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(callback, 0)
    except Exception:
        return []
    return results


def _find_browser_window(prefer_youtube: bool = False) -> int | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        foreground = int(ctypes.windll.user32.GetForegroundWindow())
        title = _window_title(foreground).lower()
        if foreground and any(token in title for token in ["youtube", "chrome", "edge", "firefox", "brave", "opera"]):
            if not prefer_youtube or "youtube" in title:
                return foreground
    except Exception:
        pass

    windows = _browser_windows()
    if prefer_youtube:
        for hwnd, title in windows:
            if "youtube" in title.lower():
                return hwnd
    return windows[0][0] if windows else None


def _activate_window(hwnd: int) -> bool:
    if not hwnd or not sys.platform.startswith("win"):
        return False
    try:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.12)
        return int(user32.GetForegroundWindow()) == int(hwnd)
    except Exception:
        return False


def _key(vk: int, down: bool = True) -> None:
    flags = 0 if down else 0x0002
    ctypes.windll.user32.keybd_event(vk, 0, flags, 0)


def _press_ctrl_key(vk: int) -> None:
    _key(0x11, True)
    _key(vk, True)
    _key(vk, False)
    _key(0x11, False)


def _clipboard_read_text() -> str | None:
    if not sys.platform.startswith("win"):
        return None
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p
    for _ in range(8):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.03)
    else:
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    except Exception:
        return None
    finally:
        user32.CloseClipboard()


def _clipboard_write_text(value: str) -> bool:
    if not sys.platform.startswith("win"):
        return False
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p
    user32.SetClipboardData.restype = ctypes.c_void_p

    data = (str(value or "") + "\0").encode("utf-16-le")
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        return False
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return False
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)

    for _ in range(8):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.03)
    else:
        return False
    try:
        user32.EmptyClipboard()
        return bool(user32.SetClipboardData(CF_UNICODETEXT, handle))
    except Exception:
        return False
    finally:
        user32.CloseClipboard()


def _current_browser_url() -> str | None:
    if not sys.platform.startswith("win"):
        return None
    with _BROWSER_CONTROL_LOCK:
        hwnd = _find_browser_window(prefer_youtube=True) or _find_browser_window(prefer_youtube=False)
        if not hwnd or not _activate_window(hwnd):
            return None
        previous = _clipboard_read_text()
        try:
            _press_ctrl_key(0x4C)  # Ctrl+L
            time.sleep(0.06)
            _press_ctrl_key(0x43)  # Ctrl+C
            time.sleep(0.10)
            value = (_clipboard_read_text() or "").strip()
            _key(0x1B, True)       # Escape address-bar selection
            _key(0x1B, False)
        finally:
            if previous is not None:
                _clipboard_write_text(previous)
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return None


def _open_or_reuse_browser(raw_url: str) -> str:
    raw_url = str(raw_url or "").strip()
    if not raw_url:
        raise ValueError("missing browser URL")
    if not sys.platform.startswith("win"):
        os.startfile(raw_url)
        return "new"

    prefer_youtube = _is_youtube_url(raw_url)
    with _BROWSER_CONTROL_LOCK:
        hwnd = _find_browser_window(prefer_youtube=prefer_youtube)
        if hwnd and _activate_window(hwnd):
            previous = _clipboard_read_text()
            try:
                if _clipboard_write_text(raw_url):
                    _press_ctrl_key(0x4C)  # Ctrl+L
                    time.sleep(0.05)
                    _press_ctrl_key(0x56)  # Ctrl+V
                    time.sleep(0.05)
                    _key(0x0D, True)       # Enter
                    _key(0x0D, False)
                    time.sleep(0.18)
                    return "reused"
            finally:
                if previous is not None:
                    _clipboard_write_text(previous)

    os.startfile(raw_url)
    return "new"

'''
text = text.replace(marker, browser_helpers + marker, 1)


# ---------------------------------------------------------------------------
# Stronger YouTube resolver.
#
# DuckDuckGo snippets were not a dependable way to locate an actual playlist.
# yt-dlp gives the Bridge a free, read-only YouTube extractor: filtered playlist
# search, channel /playlists inspection, and first-video resolution. Nothing is
# downloaded; the final URL is still validated and opened through the allowlist.
# ---------------------------------------------------------------------------
old_clean = "_clean_named_media_query"
new_clean = r'''def _clean_named_media_query(request: str) -> str:
    query = re.sub(r"\s+", " ", str(request or "")).strip()
    query = re.sub(
        r"\s+(?:on|in|to)\s+(?:the\s+)?(?:kitchen|downstairs|upstairs|ashley|monte|hp)(?:\s+(?:pc|computer))?.*$",
        "",
        query,
        flags=re.I,
    ).strip()
    query = re.sub(r"\s+for me$", "", query, flags=re.I).strip()

    named = re.search(r"\b(?:called|named)\s+(.+)$", query, flags=re.I)
    if named:
        query = named.group(1).strip()
    else:
        query = re.sub(
            r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:play|put on|start|open|find|load|queue|bring up|go to)\s+",
            "",
            query,
            flags=re.I,
        ).strip()
        query = re.sub(
            r"^(?:(?:a|the)\s+)?(?:(?:first|next|previous)\s+)?(?:playlist|song|track|album)(?:\s+on\s+youtube)?\s*",
            "",
            query,
            flags=re.I,
        ).strip()

    query = re.sub(r"\b(?:on|from)\s+youtube\b", " ", query, flags=re.I)
    query = re.sub(
        r"\b(?:off\s+of\s+there|off\s+there|from\s+there|on\s+there|on\s+that\s+channel|on\s+this\s+channel|from\s+that\s+channel)\b",
        " ",
        query,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", query).strip(" .,-")
'''
replace_function(old_clean, new_clean)

insert_marker = "async def _windows_media_state_async() -> dict:\n"
if insert_marker not in text:
    raise SystemExit("Windows media state marker missing")

yt_helpers = r'''
def _is_contextual_media_request(request: str) -> bool:
    low = str(request or "").lower()
    return any(phrase in low for phrase in [
        "that channel", "this channel", "the channel", "off of there", "off there",
        "from there", "on there", "first playlist", "next playlist", "previous playlist",
    ])


def _yt_extract(url: str, playlistend: int = 25, flat: bool = True) -> dict | None:
    try:
        from yt_dlp import YoutubeDL
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,
            "playlistend": max(1, int(playlistend)),
            "socket_timeout": 12,
            "retries": 1,
        }
        if flat:
            options["extract_flat"] = "in_playlist"
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
        return info if isinstance(info, dict) else None
    except Exception as exc:
        print(f"[media] yt-dlp extract failed: {exc}", flush=True)
        return None


def _walk_yt_nodes(value, depth: int = 0):
    if depth > 4 or not isinstance(value, dict):
        return
    yield value
    entries = value.get("entries") or []
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                yield from _walk_yt_nodes(entry, depth + 1)


def _yt_node_url(node: dict) -> str | None:
    for key in ["webpage_url", "original_url", "url"]:
        value = str(node.get(key) or "").strip()
        if value.startswith("https://") or value.startswith("http://"):
            return value
    ident = str(node.get("id") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", ident):
        return f"https://www.youtube.com/watch?v={ident}"
    if ident and any(ident.startswith(prefix) for prefix in ["PL", "UU", "OL", "RD", "FL", "LL"]):
        return f"https://www.youtube.com/playlist?list={urllib.parse.quote(ident)}"
    return None


def _youtube_list_id(url: str) -> str:
    try:
        parsed = urlsplit(url)
        return (urllib.parse.parse_qs(parsed.query).get("list") or [""])[0]
    except Exception:
        return ""


def _playlist_playable_candidate(url: str, title: str = "") -> dict | None:
    if not _is_youtube_url(url):
        return None
    list_id = _youtube_list_id(url)
    looks_playlist = "playlist" in url.lower() or bool(list_id)
    if not looks_playlist:
        return None

    canonical = url
    if list_id:
        canonical = f"https://www.youtube.com/playlist?list={urllib.parse.quote(list_id)}"

    info = _yt_extract(canonical, playlistend=3, flat=True)
    first_video_id = ""
    resolved_title = title
    if info:
        resolved_title = str(info.get("title") or resolved_title or "").strip()
        for node in _walk_yt_nodes(info):
            ident = str(node.get("id") or "").strip()
            node_url = _yt_node_url(node) or ""
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", ident):
                first_video_id = ident
                break
            match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", node_url)
            if match:
                first_video_id = match.group(1)
                break

    playable = canonical
    if first_video_id:
        playable = f"https://www.youtube.com/watch?v={first_video_id}"
        if list_id:
            playable += f"&list={urllib.parse.quote(list_id)}"
    return {
        "url": playable,
        "playlist_url": canonical,
        "title": resolved_title or title or "YouTube playlist",
        "query": resolved_title or title or "",
    }


def _channel_root_from_url(url: str) -> str | None:
    if not _is_youtube_url(url):
        return None
    parsed = urlsplit(url)
    host = parsed.hostname or "www.youtube.com"
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    first = parts[0]
    if first.startswith("@"):
        return f"https://{host}/{first}"
    if first in {"channel", "c", "user"} and len(parts) >= 2:
        return f"https://{host}/{first}/{parts[1]}"
    return None


def _channel_root_via_info(url: str) -> str | None:
    direct = _channel_root_from_url(url)
    if direct:
        return direct
    info = _yt_extract(url, playlistend=1, flat=False)
    if not info:
        return None
    for key in ["channel_url", "uploader_url"]:
        candidate = str(info.get(key) or "").strip()
        direct = _channel_root_from_url(candidate)
        if direct:
            return direct
    return None


def _playlist_candidates_from_channel(current_url: str) -> list[dict]:
    if not _is_youtube_url(current_url):
        return []
    list_id = _youtube_list_id(current_url)
    if list_id:
        candidate = _playlist_playable_candidate(current_url)
        return [candidate] if candidate else []

    root = _channel_root_via_info(current_url)
    if not root:
        return []
    info = _yt_extract(root.rstrip("/") + "/playlists", playlistend=24, flat=True)
    if not info:
        return []

    candidates = []
    seen = set()
    for node in _walk_yt_nodes(info):
        url = _yt_node_url(node) or ""
        title = str(node.get("title") or "").strip()
        if not url:
            continue
        if "playlist" not in url.lower() and not _youtube_list_id(url):
            continue
        candidate = _playlist_playable_candidate(url, title)
        if not candidate:
            continue
        key = candidate.get("playlist_url") or candidate.get("url")
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
        if len(candidates) >= 16:
            break
    return candidates


def _playlist_candidates_from_search(query: str) -> list[dict]:
    query = str(query or "").strip()
    if not query:
        return []
    params = urllib.parse.urlencode({"search_query": query, "sp": "EgIQAw=="})
    search_url = "https://www.youtube.com/results?" + params
    info = _yt_extract(search_url, playlistend=25, flat=True)
    candidates = []
    seen = set()
    if info:
        for node in _walk_yt_nodes(info):
            url = _yt_node_url(node) or ""
            title = str(node.get("title") or "").strip()
            if not url or ("playlist" not in url.lower() and not _youtube_list_id(url)):
                continue
            candidate = _playlist_playable_candidate(url, title)
            if not candidate:
                continue
            key = candidate.get("playlist_url") or candidate.get("url")
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
            if len(candidates) >= 12:
                break

    # Conservative fallback for cases where YouTube changes its search page.
    if not candidates:
        try:
            results = web_search(f"{query} site:youtube.com playlist", limit=12)
        except Exception:
            results = []
        for item in results:
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            candidate = _playlist_playable_candidate(url, title)
            if candidate:
                candidates.append(candidate)
    return candidates


def _video_candidates_from_search(query: str) -> list[dict]:
    query = str(query or "").strip()
    if not query:
        return []
    info = _yt_extract(f"ytsearch12:{query}", playlistend=12, flat=True)
    candidates = []
    if not info:
        return candidates
    for node in _walk_yt_nodes(info):
        url = _yt_node_url(node) or ""
        if not _is_youtube_url(url):
            continue
        title = str(node.get("title") or "").strip()
        if "/watch" in url or "youtu.be/" in url:
            candidates.append({"url": url, "title": title or query, "query": query})
            if len(candidates) >= 10:
                break
    return candidates


def _rank_media_candidates(candidates: list[dict], query: str) -> dict | None:
    if not candidates:
        return None
    wanted = _media_terms(query)
    scored = []
    for index, candidate in enumerate(candidates):
        title = str(candidate.get("title") or "")
        hay = f"{title} {candidate.get('url') or ''}".lower()
        overlap = len(wanted & _media_terms(hay)) if wanted else 0
        score = overlap * 8 - index * 0.05
        if query and query.lower() in title.lower():
            score += 14
        scored.append((score, candidate))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if wanted and scored[0][0] <= 0:
        return None
    return scored[0][1]

'''
text = text.replace(insert_marker, yt_helpers + insert_marker, 1)

new_resolver = r'''def _resolve_named_media_v090(request: str) -> dict | None:
    request = str(request or "").strip()
    query = _clean_named_media_query(request)
    low = request.lower()
    wants_playlist = "playlist" in low or _is_contextual_media_request(request)
    current_url = _current_browser_url()

    # Context wins for phrases such as "first playlist on that channel" and also
    # lets a named playlist be found inside the channel already open on the PC.
    if wants_playlist and current_url and _is_youtube_url(current_url):
        channel_candidates = _playlist_candidates_from_channel(current_url)
        if channel_candidates:
            if query:
                ranked = _rank_media_candidates(channel_candidates, query)
                if ranked:
                    ranked["query"] = query
                    return ranked
            elif _is_contextual_media_request(request):
                first = channel_candidates[0]
                first["query"] = first.get("title") or "first playlist"
                return first

    if wants_playlist and query:
        ranked = _rank_media_candidates(_playlist_candidates_from_search(query), query)
        if ranked:
            ranked["query"] = query
            return ranked

    if not wants_playlist and query:
        ranked = _rank_media_candidates(_video_candidates_from_search(query), query)
        if ranked:
            ranked["query"] = query
            return ranked

    if _is_contextual_media_request(request):
        return {
            "error": "I couldn't read a resolvable YouTube channel or playlist from the browser that's open on that PC"
        }
    return {"error": "no sufficiently relevant YouTube media match found"}
'''
replace_function("_resolve_named_media_v090", new_resolver)

new_play = r'''def _play_named_media(request: str) -> dict:
    node = socket.gethostname() or "PC"
    key = _normalize_skill_text(request)

    with _MEDIA_ACTION_LOCK:
        now = time.time()
        cached = _MEDIA_LAST.get("result")
        if key and key == _MEDIA_LAST.get("key") and now - float(_MEDIA_LAST.get("at") or 0) < 15 and isinstance(cached, dict):
            duplicate = dict(cached)
            duplicate["deduplicated"] = True
            return duplicate

        candidate = _resolve_named_media_v090(request)
        if not candidate or candidate.get("error"):
            result = {
                "ok": False,
                "action": "play_named_media",
                "node_name": node,
                "message": str((candidate or {}).get("error") or "no YouTube media match found"),
                "playback_verified": False,
            }
            _MEDIA_LAST.update({"key": key, "at": now, "result": result})
            return result

        raw_url = str(candidate.get("url") or "").strip()
        if not _is_youtube_url(raw_url):
            result = {
                "ok": False,
                "action": "play_named_media",
                "node_name": node,
                "message": "resolved media URL failed YouTube validation",
                "playback_verified": False,
            }
            _MEDIA_LAST.update({"key": key, "at": now, "result": result})
            return result

        before = _windows_media_state()
        try:
            browser_mode = _open_or_reuse_browser(raw_url)
        except Exception as exc:
            result = {
                "ok": False,
                "action": "play_named_media",
                "node_name": node,
                "message": str(exc),
                "playback_verified": False,
            }
            _MEDIA_LAST.update({"key": key, "at": now, "result": result})
            return result

        wanted = _media_terms(candidate.get("query") or candidate.get("title") or request)
        verified = False
        observed = {}
        tried_play = False

        for attempt in range(16):
            time.sleep(0.60 if attempt else 1.1)
            observed = _windows_media_state()
            status = str(observed.get("status") or "").lower()
            current_title = str(observed.get("title") or "")
            title_overlap = len(wanted & _media_terms(current_title)) if wanted else 0
            changed = _media_state_changed(before, observed)
            if "playing" in status and (title_overlap > 0 or changed):
                verified = True
                break
            if attempt >= 4 and not tried_play:
                tried_play = True
                _windows_try_play()

        result = {
            "ok": True,
            "action": "play_named_media",
            "node_name": node,
            "message": "named media opened and playback verified" if verified else "named media opened; playback not verified",
            "playback_verified": verified,
            "media_title": str(observed.get("title") or candidate.get("title") or candidate.get("query") or "")[:240],
            "source_app": str(observed.get("source_app") or "")[:240],
            "resolved_url": raw_url,
            "browser_mode": browser_mode,
        }
        _MEDIA_LAST.update({"key": key, "at": now, "result": result})
        return result
'''
replace_function("_play_named_media", new_play)


# Generic "open YouTube" should also reuse the existing YouTube tab instead of
# manufacturing another one each time. Other URLs keep the old behavior.
old_open = '''            os.startfile(raw_url)\n            message = f"Opened {parsed_url.hostname}"\n'''
new_open = '''            if _is_youtube_url(raw_url):\n                _open_or_reuse_browser(raw_url)\n            else:\n                os.startfile(raw_url)\n            message = f"Opened {parsed_url.hostname}"\n'''
if old_open not in text:
    raise SystemExit("open_url launch marker missing")
text = text.replace(old_open, new_open, 1)

# Advertise the context controller in status for diagnostics.
status_marker = '                "media_playback_verification": True,\n'
if status_marker not in text:
    raise SystemExit("v0.9.0 media status marker missing")
text = text.replace(
    status_marker,
    status_marker + '                "youtube_context_control": True,\n                "youtube_same_tab_navigation": True,\n',
    1,
)

path.write_text(text, encoding="utf-8")

full = Path("Bridge/vex_bridge_full.py")
full_text = full.read_text(encoding="utf-8")
if 'VERSION = "0.9.0"' not in full_text:
    raise SystemExit("Bridge full v0.9.0 version marker missing")
full_text = full_text.replace('VERSION = "0.9.0"', 'VERSION = "0.9.1"', 1)
full.write_text(full_text, encoding="utf-8")

for p, markers in [
    (path, [
        "_current_browser_url",
        "_open_or_reuse_browser",
        "yt_dlp",
        "EgIQAw==",
        "_playlist_candidates_from_channel",
        "youtube_same_tab_navigation",
        "deduplicated",
    ]),
    (full, ['VERSION = "0.9.1"']),
]:
    data = p.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"missing v0.9.1 Bridge marker: {marker}")
print("Applied v0.9.1 YouTube channel context + same-tab navigation + yt-dlp resolver")
