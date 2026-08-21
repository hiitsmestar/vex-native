#!/usr/bin/env python3
"""Vex Bridge v0.7

A local companion for VexNative. It exposes a SearXNG-compatible /search endpoint
so the iPhone app can search selected PC folders and, when available, the public
web. A per-install bearer token protects every query and the server uses a
self-signed TLS certificate generated on first run.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import secrets
import socket
import ssl
import sys
import threading
import time
import urllib.parse
import zipfile
from dataclasses import dataclass, asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable

APP_NAME = "VexBridge"
PORT = 8765
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 8000
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".json", ".csv", ".log", ".ini", ".cfg",
    ".yaml", ".yml", ".xml", ".html", ".htm", ".py", ".swift", ".js",
    ".ts", ".css", ".c", ".cpp", ".h", ".hpp", ".java", ".kt", ".sh",
    ".bat", ".ps1", ".rtf"
}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}


def app_dir() -> Path:
    if sys.platform.startswith("win"):
        root = Path(os.environ.get("APPDATA", Path.home()))
    else:
        root = Path.home() / ".config"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


CONFIG_PATH = app_dir() / "config.json"
CERT_PATH = app_dir() / "bridge-cert.pem"
KEY_PATH = app_dir() / "bridge-key.pem"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text("utf-8"))
        except Exception:
            pass
    config = {
        "token": secrets.token_urlsafe(32),
        "folders": [],
        "web_search": True,
        "port": PORT,
    }
    save_config(config)
    return config


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2), "utf-8")


def choose_folders(existing: list[str]) -> list[str]:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception:
        return existing

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folders = list(existing)
    while True:
        selected = filedialog.askdirectory(title="Choose a folder Vex may search")
        if selected:
            normalized = str(Path(selected).resolve())
            if normalized not in folders:
                folders.append(normalized)
        if not selected or not messagebox.askyesno("Vex Bridge", "Add another searchable folder?"):
            break
    root.destroy()
    return folders


def ensure_certificate() -> None:
    if CERT_PATH.exists() and KEY_PATH.exists():
        return
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from datetime import datetime, timedelta, timezone
    except Exception as exc:
        raise RuntimeError("TLS certificate support is missing. Reinstall the packaged Vex Bridge.") from exc

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Vex Bridge Local")
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    KEY_PATH.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        sock.close()


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9_+-]{1,}", text.lower()) if len(w) > 1]


def strip_rtf(text: str) -> str:
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return re.sub(r"\s+", " ", text).strip()


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("word/document.xml").decode("utf-8", "ignore")
    raw = re.sub(r"</w:p>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(re.sub(r"[ \t]+", " ", raw)).strip()


def read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages[:80]:
            parts.append(page.extract_text() or "")
            if sum(map(len, parts)) > 180_000:
                break
        return "\n".join(parts)
    except Exception:
        return ""


def read_text_file(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return ""
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return read_pdf(path)
        if suffix == ".docx":
            return read_docx(path)
        data = path.read_bytes()
        text = data.decode("utf-8", "ignore")
        if suffix == ".rtf":
            text = strip_rtf(text)
        return text
    except Exception:
        return ""


@dataclass
class IndexedDocument:
    path: str
    name: str
    text: str
    tokens: set[str]
    mtime: float


class LocalIndex:
    def __init__(self, folders: list[str]):
        self.folders = [Path(p) for p in folders]
        self.documents: list[IndexedDocument] = []
        self.lock = threading.Lock()
        self.last_indexed = 0.0

    def rebuild(self) -> None:
        documents: list[IndexedDocument] = []
        count = 0
        for root in self.folders:
            if not root.exists():
                continue
            try:
                iterator = root.rglob("*")
                for path in iterator:
                    if count >= MAX_FILES:
                        break
                    try:
                        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                            continue
                        text = read_text_file(path)
                        if not text.strip():
                            continue
                        compact = re.sub(r"\s+", " ", text).strip()
                        documents.append(IndexedDocument(
                            path=str(path),
                            name=path.name,
                            text=compact[:220_000],
                            tokens=set(words(path.name + " " + compact[:80_000])),
                            mtime=path.stat().st_mtime,
                        ))
                        count += 1
                    except Exception:
                        continue
            except Exception:
                continue
        with self.lock:
            self.documents = documents
            self.last_indexed = time.time()

    def search(self, query: str, limit: int = 5) -> list[dict]:
        qwords = words(query)
        if not qwords:
            return []
        qset = set(qwords)
        scored: list[tuple[float, IndexedDocument]] = []
        with self.lock:
            docs = list(self.documents)
        for doc in docs:
            overlap = len(qset & doc.tokens)
            if overlap == 0:
                continue
            name_lower = doc.name.lower()
            name_hits = sum(1 for w in qset if w in name_lower)
            phrase_bonus = 2.5 if query.lower() in doc.text.lower() else 0.0
            score = overlap / max(2, len(qset)) + name_hits * 0.35 + phrase_bonus
            scored.append((score, doc))
        scored.sort(key=lambda item: item[0], reverse=True)

        results = []
        for score, doc in scored[:limit]:
            snippet = best_snippet(doc.text, qwords)
            digest = hashlib.sha256(doc.path.encode("utf-8", "ignore")).hexdigest()[:16]
            results.append({
                "title": f"[PC] {doc.name}",
                "url": f"https://vexbridge.invalid/local/{digest}",
                "content": snippet,
                "engine": "Vex Bridge PC files",
                "score": round(float(score), 4),
            })
        return results


def best_snippet(text: str, qwords: list[str], width: int = 900) -> str:
    lower = text.lower()
    positions = [lower.find(w) for w in qwords if lower.find(w) >= 0]
    start = max(0, (min(positions) if positions else 0) - 180)
    snippet = text[start:start + width]
    return snippet.strip()


def unwrap_ddg(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urllib.parse.urlparse(href)
        query = urllib.parse.parse_qs(parsed.query)
        if "uddg" in query:
            return urllib.parse.unquote(query["uddg"][0])
    except Exception:
        pass
    return href


def web_search(query: str, limit: int = 6) -> list[dict]:
    try:
        import requests
        from bs4 import BeautifulSoup

        response = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 VexBridge/0.7"},
            timeout=12,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for block in soup.select(".result"):
            link = block.select_one("a.result__a")
            if link is None:
                continue
            href = unwrap_ddg(link.get("href") or "")
            if not href.startswith("https://"):
                continue
            snippet_node = block.select_one(".result__snippet")
            snippet = " ".join(snippet_node.stripped_strings) if snippet_node else ""
            title = " ".join(link.stripped_strings)
            if not title:
                continue
            results.append({
                "title": title,
                "url": href,
                "content": snippet,
                "engine": "Vex Bridge web",
                "score": max(0.2, 1.0 - len(results) * 0.08),
            })
            if len(results) >= limit:
                break
        return results
    except Exception:
        return []


class BridgeState:
    def __init__(self, config: dict):
        self.config = config
        self.index = LocalIndex(config.get("folders", []))
        self.started = time.time()


STATE: BridgeState | None = None


class Handler(BaseHTTPRequestHandler):
    server_version = "VexBridge/0.7"

    def log_message(self, fmt: str, *args) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, params: dict[str, list[str]]) -> bool:
        assert STATE is not None
        supplied = (params.get("token") or [""])[0]
        return secrets.compare_digest(supplied, STATE.config.get("token", ""))

    def do_GET(self) -> None:
        assert STATE is not None
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if not self._authorized(params):
            self._json(401, {"error": "invalid bridge token"})
            return

        if parsed.path in ("/", "/status"):
            self._json(200, {
                "name": "Vex Bridge",
                "version": "0.7",
                "indexed_files": len(STATE.index.documents),
                "folders": STATE.config.get("folders", []),
                "web_search": bool(STATE.config.get("web_search", True)),
                "uptime_seconds": int(time.time() - STATE.started),
            })
            return

        if parsed.path == "/reindex":
            STATE.index.rebuild()
            self._json(200, {"ok": True, "indexed_files": len(STATE.index.documents)})
            return

        if parsed.path != "/search":
            self._json(404, {"error": "not found"})
            return

        query = (params.get("q") or [""])[0].strip()
        if not query:
            self._json(200, {"results": []})
            return

        local = STATE.index.search(query, limit=5)
        web = web_search(query, limit=6) if STATE.config.get("web_search", True) else []
        # Local knowledge comes first, but web still fills the broader research role.
        results = local + web
        self._json(200, {"query": query, "results": results[:10]})


def start_background_reindex(state: BridgeState) -> None:
    def loop() -> None:
        while True:
            time.sleep(600)
            try:
                state.index.rebuild()
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Vex Bridge — local PC knowledge + web gateway")
    parser.add_argument("--setup", action="store_true", help="choose/rechoose searchable folders")
    parser.add_argument("--no-web", action="store_true", help="disable public web search; PC files only")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    config = load_config()
    if args.no_web:
        config["web_search"] = False
    if args.port:
        config["port"] = int(args.port)

    if args.setup or not config.get("folders"):
        config["folders"] = choose_folders(config.get("folders", []))
        save_config(config)

    ensure_certificate()
    state = BridgeState(config)
    global STATE
    STATE = state

    print("\nVex Bridge v0.7 — indexing selected folders…")
    state.index.rebuild()
    start_background_reindex(state)

    port = int(config.get("port", PORT))
    address = lan_ip()
    token = config["token"]
    endpoint = f"https://{address}:{port}?token={urllib.parse.quote(token)}"

    print(f"Indexed files: {len(state.index.documents)}")
    print("Folders:")
    for folder in config.get("folders", []):
        print(f"  - {folder}")
    if not config.get("folders"):
        print("  (none — run VexBridge.exe --setup to add folders)")
    print("\nPaste this whole line into Vex → Brain → SearXNG endpoint:")
    print(endpoint)
    print("\nKeep this window open while Vex is using the bridge.")
    print("The pairing token is private; anyone with it on your LAN can query the bridge.\n")

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nVex Bridge stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
