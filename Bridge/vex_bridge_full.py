#!/usr/bin/env python3
"""Vex Bridge v0.7.1 full-access launcher.

Builds on the v0.7 bridge core while changing startup/indexing behavior:
- disables Windows QuickEdit so clicking the console cannot pause the process
- defaults to all readable fixed drives, no folder-picker required
- prunes OS/cache trees from indexing so full-drive scans stay practical
- serves immediately while indexing runs in the background
- refreshes roots and reindexes periodically so new folders appear automatically
"""

from __future__ import annotations

import argparse
import ctypes
import os
import ssl
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from http.server import ThreadingHTTPServer

import vex_bridge as core

VERSION = "0.7.1"
REINDEX_SECONDS = 300
MAX_INDEXED_FILES = 16000
MAX_STORED_TEXT = 16000
TOKEN_SAMPLE = 12000

SKIP_NAMES = {
    "$recycle.bin", "system volume information", "windows", "windows.old",
    "program files", "program files (x86)", "programdata", "recovery",
    "$winreagent", "perflogs", "msocache", "node_modules", ".git", ".svn",
    ".hg", "__pycache__", ".cache", "cache", "caches", "temp", "tmp"
}


def disable_quick_edit() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_QUICK_EDIT_MODE = 0x0040
            ENABLE_EXTENDED_FLAGS = 0x0080
            new_mode = (mode.value | ENABLE_EXTENDED_FLAGS) & ~ENABLE_QUICK_EDIT_MODE
            kernel32.SetConsoleMode(handle, new_mode)
    except Exception:
        pass


def fixed_drives() -> list[Path]:
    if not sys.platform.startswith("win"):
        return [Path.home()]
    roots: list[Path] = []
    try:
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        DRIVE_FIXED = 3
        for i in range(26):
            if mask & (1 << i):
                root = f"{chr(ord('A') + i)}:\\"
                if ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) == DRIVE_FIXED:
                    roots.append(Path(root))
    except Exception:
        pass
    if not roots:
        roots = [Path(Path.home().anchor or "C:\\")]
    return roots


def automatic_roots() -> list[Path]:
    # Home is first so personal files become searchable before the broad drive scan.
    roots = [Path.home()] + fixed_drives()
    result: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            key = os.path.normcase(str(root.resolve()))
        except Exception:
            key = os.path.normcase(str(root))
        if key not in seen:
            seen.add(key)
            result.append(root)
    return result


def norm(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except Exception:
        return os.path.normcase(str(path))


def skip_directory(path: Path, name: str) -> bool:
    lower_name = name.lower()
    if lower_name in SKIP_NAMES:
        return True
    lower_path = norm(path).lower()
    # AppData\Roaming remains searchable; giant Local caches do not.
    if "\\appdata\\local" in lower_path:
        return True
    return False


def full_rebuild(self) -> None:
    if getattr(self, "_vex_indexing", False):
        return
    self._vex_indexing = True
    try:
        documents = []
        count = 0
        seen_files: set[str] = set()
        completed_roots: set[str] = set()
        last_report = 0

        for root in list(self.folders):
            if count >= MAX_INDEXED_FILES:
                break
            root = Path(root)
            if not root.exists():
                continue
            print(f"[index] scanning {root}", flush=True)

            try:
                walker = os.walk(root, topdown=True, followlinks=False)
                for dirpath, dirnames, filenames in walker:
                    if count >= MAX_INDEXED_FILES:
                        break
                    current = Path(dirpath)

                    kept = []
                    for dirname in dirnames:
                        child = current / dirname
                        child_key = norm(child)
                        if child_key in completed_roots:
                            continue
                        if skip_directory(child, dirname):
                            continue
                        kept.append(dirname)

                    priority = {
                        "desktop": 0, "documents": 1, "downloads": 2, "onedrive": 3,
                        "pictures": 4, "music": 5, "videos": 6, "source": 7,
                        "src": 8, "projects": 9, "appdata": 90
                    }
                    kept.sort(key=lambda value: (priority.get(value.lower(), 50), value.lower()))
                    dirnames[:] = kept

                    for filename in filenames:
                        if count >= MAX_INDEXED_FILES:
                            break
                        path = current / filename
                        if path.suffix.lower() not in core.SUPPORTED_EXTENSIONS:
                            continue
                        key = norm(path)
                        if key in seen_files:
                            continue
                        seen_files.add(key)

                        try:
                            if not path.is_file() or path.stat().st_size > core.MAX_FILE_BYTES:
                                continue
                            text = core.read_text_file(path)
                            if not text.strip():
                                continue
                            compact = core.re.sub(r"\s+", " ", text).strip()
                            documents.append(core.IndexedDocument(
                                path=str(path),
                                name=path.name,
                                text=compact[:MAX_STORED_TEXT],
                                tokens=set(core.words(path.name + " " + compact[:TOKEN_SAMPLE])),
                                mtime=path.stat().st_mtime,
                            ))
                            count += 1
                        except Exception:
                            continue

                        if count - last_report >= 250:
                            last_report = count
                            with self.lock:
                                self.documents = list(documents)
                            print(f"[index] {count:,} searchable files so far…", flush=True)
            except Exception:
                pass
            completed_roots.add(norm(root))

        with self.lock:
            self.documents = documents
            self.last_indexed = time.time()
        print(f"[index] ready — {len(documents):,} searchable files", flush=True)
    finally:
        self._vex_indexing = False


def launch_rebuild(state) -> None:
    if getattr(state.index, "_vex_indexing", False):
        return
    state.index.folders = automatic_roots()
    threading.Thread(target=state.index.rebuild, daemon=True, name="VexBridgeIndex").start()


def refresh_loop(state) -> None:
    while True:
        time.sleep(REINDEX_SECONDS)
        launch_rebuild(state)


def main() -> None:
    disable_quick_edit()
    core.LocalIndex.rebuild = full_rebuild
    core.Handler.server_version = f"VexBridge/{VERSION}"

    parser = argparse.ArgumentParser(description="Vex Bridge — full PC knowledge + web gateway")
    parser.add_argument("--no-web", action="store_true", help="disable public web search; PC files only")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    config = core.load_config()
    config["access_mode"] = "full"
    config["folders"] = [str(root) for root in automatic_roots()]
    if args.no_web:
        config["web_search"] = False
    if args.port:
        config["port"] = int(args.port)
    core.save_config(config)

    core.ensure_certificate()
    state = core.BridgeState(config)
    core.STATE = state

    port = int(config.get("port", core.PORT))
    address = core.lan_ip()
    token = config["token"]
    endpoint = f"https://{address}:{port}?token={urllib.parse.quote(token)}"

    print(f"\nVex Bridge v{VERSION} — READY", flush=True)
    print("Full-access mode: every readable fixed drive is included automatically.", flush=True)
    print("New folders are discovered on the recurring background scan.", flush=True)
    print("Windows/Program Files/system caches are ignored by the content index so it stays responsive.", flush=True)
    print("The bridge server is usable immediately while indexing continues.\n", flush=True)
    print("Paste this whole line into Vex → Brain → SearXNG endpoint:", flush=True)
    print(endpoint, flush=True)
    print("\nKeep this window open while Vex is using the bridge.", flush=True)
    print("Index progress will appear below. Clicking the window will no longer freeze it.\n", flush=True)

    server = ThreadingHTTPServer(("0.0.0.0", port), core.Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(core.CERT_PATH), keyfile=str(core.KEY_PATH))
    server.socket = context.wrap_socket(server.socket, server_side=True)

    launch_rebuild(state)
    threading.Thread(target=refresh_loop, args=(state,), daemon=True, name="VexBridgeRefresh").start()

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nVex Bridge stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
