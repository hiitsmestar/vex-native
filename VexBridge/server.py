from __future__ import annotations

import base64
import hmac
import inspect
import fnmatch
import io
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
import zipfile
from collections import deque
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Literal

import psutil
from docx import Document
from mcp.server.fastmcp import FastMCP
from openpyxl import Workbook, load_workbook
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import uvicorn

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexBridgeDC"
CONFIG_PATH = APP_DIR / "config.json"
AUDIT_PATH = APP_DIR / "audit.jsonl"
APP_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "allowedRoots": [str(Path.home())],
    "allowedDirectories": [str(Path.home())],
    "fileReadLineLimit": 1000,
    "fileWriteLineLimit": 30,
    "searchResultLimit": 500,
    "blockedCommands": [],
    "defaultShell": "",
    "telemetryEnabled": False,
}
if not CONFIG_PATH.exists():
    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")

MCP_HOST = os.environ.get("VEXBRIDGE_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("VEXBRIDGE_PORT", "8795"))
mcp = FastMCP("VexBridge", host=MCP_HOST, port=MCP_PORT, stateless_http=True, json_response=True)
RECENT_TOOL_CALLS = deque(maxlen=1000)
_NO_TRACK = {"get_recent_tool_calls", "get_usage_stats", "get_prompts", "give_feedback_to_desktop_commander"}

def tracked_tool():
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            started = time.time()
            ok = True
            result = None
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as exc:
                ok = False
                result = {"error": f"{type(exc).__name__}: {exc}"}
                raise
            finally:
                if fn.__name__ not in _NO_TRACK:
                    try:
                        arguments = dict(inspect.signature(fn).bind_partial(*args, **kwargs).arguments)
                    except Exception:
                        arguments = dict(kwargs)
                    try:
                        encoded = json.dumps(result, ensure_ascii=False, default=str)
                        output = result if len(encoded) <= 20000 else encoded[:20000] + "...[truncated]"
                    except Exception:
                        output = repr(result)[:20000]
                    RECENT_TOOL_CALLS.append({
                        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                        "tool": fn.__name__, "arguments": arguments, "output": output, "ok": ok,
                        "duration_ms": round((time.time() - started) * 1000, 2),
                    })
        return mcp.tool()(wrapped)
    return decorate

def audit(tool: str, ok: bool, detail: dict[str, Any] | None = None) -> None:
    rec = {"ts": time.time(), "tool": tool, "ok": ok, "detail": detail or {}}
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def load_config() -> dict[str, Any]:
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        cfg = {**DEFAULT_CONFIG, **raw}
        if "allowedDirectories" in raw and "allowedRoots" not in raw:
            cfg["allowedRoots"] = raw["allowedDirectories"]
        elif "allowedRoots" in raw and "allowedDirectories" not in raw:
            cfg["allowedDirectories"] = raw["allowedRoots"]
        return cfg
    except Exception:
        return dict(DEFAULT_CONFIG)

def save_config(cfg: dict[str, Any]) -> None:
    if "allowedDirectories" in cfg:
        cfg["allowedRoots"] = cfg["allowedDirectories"]
    elif "allowedRoots" in cfg:
        cfg["allowedDirectories"] = cfg["allowedRoots"]
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def resolve_allowed(raw: str) -> Path:
    p = Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
    cfg = load_config()
    raw_roots = cfg.get("allowedDirectories", cfg.get("allowedRoots", []))
    if raw_roots == []:
        return p
    roots = [Path(os.path.expandvars(os.path.expanduser(x))).resolve() for x in raw_roots]
    if not any(p == r or r in p.parents for r in roots):
        raise PermissionError(f"path outside allowed roots: {p}")
    return p

def slice_lines(lines: list[str], offset: int = 0, length: int | None = None) -> list[str]:
    if offset < 0:
        return lines[offset:]
    lim = length if length is not None else int(load_config()["fileReadLineLimit"])
    return lines[offset:offset + lim]

def excel_values(path: Path, sheet: str | None = None, cell_range: str | None = None) -> Any:
    wb = load_workbook(path, data_only=False)
    ws = wb[wb.sheetnames[int(sheet)]] if sheet and sheet.isdigit() else wb[sheet] if sheet else wb.active
    rows = ws[cell_range] if cell_range else ws.iter_rows()
    if cell_range and not isinstance(rows, tuple):
        rows = ((rows,),)
    return [[cell.value for cell in row] for row in rows]

def docx_outline(path: Path) -> str:
    d = Document(path)
    out: list[str] = []
    for i, p in enumerate(d.paragraphs):
        if p.text:
            out.append(f"[{i}] paragraph style={p.style.name!r}: {p.text}")
    for ti, t in enumerate(d.tables):
        out.append(f"[table {ti}]")
        for row in t.rows:
            out.append(" | ".join(c.text for c in row.cells))
    return "\n".join(out)

@tracked_tool()
def ping(deviceId: str | None = None) -> dict[str, Any]:
    return {"pong": True, "host": socket.gethostname(), "time": time.time()}

@tracked_tool()
def list_devices() -> list[dict[str, Any]]:
    host = socket.gethostname()
    return [{
        "id": host.lower(),
        "device_name": host,
        "status": "online",
        "auth_token": "local",
        "capabilities": {
            "app_version": "VexBridge-0.1",
            "transport": "streamable-http",
        },
    }]

@tracked_tool()
def who_am_i() -> dict[str, Any]:
    return {
        "user": os.environ.get("USERNAME") or os.environ.get("USER") or "unknown",
        "role": "local_authorized",
        "device_count": 1,
        "remote_tool_usage_percent": 0,
    }

@tracked_tool()
def get_prompts(action: Literal["get_prompt"], promptId: str, deviceId: str | None = None) -> dict[str, Any]:
    prompts = {
        "onb2_01": "Organize the Downloads folder into sensible categories and report what changed.",
        "onb2_02": "Inspect a codebase or repository and explain its structure, entry points, and important workflows.",
        "onb2_03": "Create an organized knowledge base from the selected files and folders.",
        "onb2_04": "Analyze a local data file and summarize important patterns and findings.",
        "onb2_05": "Check system health, running processes, storage, and resource pressure.",
    }
    if action != "get_prompt" or promptId not in prompts:
        raise ValueError("unsupported prompt request")
    return {"action": action, "promptId": promptId, "prompt": prompts[promptId]}

@tracked_tool()
def give_feedback_to_desktop_commander(deviceId: str | None = None) -> dict[str, Any]:
    return {"ok": True, "replacement": "VexBridge", "message": "No vendor feedback form is used by VexBridge."}

@tracked_tool()
def get_config(deviceId: str | None = None) -> dict[str, Any]:
    return load_config()

@tracked_tool()
def set_config_value(key: str, value: str | int | float | bool | list[str] | None, deviceId: str | None = None) -> dict[str, Any]:
    cfg = load_config()
    cfg[key] = value
    if key == "allowedDirectories": cfg["allowedRoots"] = value
    if key == "allowedRoots": cfg["allowedDirectories"] = value
    save_config(cfg)
    audit("set_config_value", True, {"key": key})
    return cfg

@tracked_tool()
def read_file(path: str, isUrl: bool = False, offset: int = 0, length: int = 1000,
              sheet: str | None = None, range: str | None = None, options: dict[str, Any] | None = None, deviceId: str | None = None) -> Any:
    if isUrl:
        with urllib.request.urlopen(path, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    p = resolve_allowed(path)
    ext = p.suffix.lower()
    if ext in {".xlsx", ".xlsm"}:
        return excel_values(p, sheet, range)
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return {"mime": Image.MIME.get(Image.open(p).format, "application/octet-stream"),
                "base64": base64.b64encode(p.read_bytes()).decode()}
    if ext == ".pdf":
        pages = PdfReader(str(p)).pages
        selected = pages[offset:offset + length]
        return "\n\n".join(f"# Page {offset+i+1}\n{pg.extract_text() or ''}" for i, pg in enumerate(selected))
    if ext == ".docx" and offset == 0:
        return docx_outline(p)
    text = p.read_text(encoding="utf-8", errors="replace")
    return "\n".join(slice_lines(text.splitlines(), offset, length))

@tracked_tool()
def read_multiple_files(paths: list[str], deviceId: str | None = None) -> dict[str, Any]:
    out = {}
    for p in paths:
        try:
            out[p] = read_file(p)
        except Exception as e:
            out[p] = {"error": str(e)}
    return out

@tracked_tool()
def write_file(path: str, content: str, mode: str = "rewrite", deviceId: str | None = None) -> dict[str, Any]:
    p = resolve_allowed(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ext = p.suffix.lower()
    if ext in {".xlsx", ".xlsm"}:
        data = json.loads(content)
        wb = Workbook()
        wb.remove(wb.active)
        mapping = data if isinstance(data, dict) else {"Sheet1": data}
        for name, rows in mapping.items():
            ws = wb.create_sheet(name)
            for row in rows:
                ws.append(row)
        wb.save(p)
    elif ext == ".docx" and mode == "rewrite":
        d = Document()
        for line in content.splitlines():
            if line.startswith("### "): d.add_heading(line[4:], 3)
            elif line.startswith("## "): d.add_heading(line[3:], 2)
            elif line.startswith("# "): d.add_heading(line[2:], 1)
            else: d.add_paragraph(line)
        d.save(p)
    else:
        with p.open("a" if mode == "append" else "w", encoding="utf-8") as f:
            f.write(content)
    audit("write_file", True, {"path": str(p), "mode": mode})
    return {"ok": True, "path": str(p), "bytes": p.stat().st_size}

@tracked_tool()
def create_directory(path: str, deviceId: str | None = None) -> dict[str, Any]:
    p = resolve_allowed(path)
    p.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": str(p)}

@tracked_tool()
def move_file(source: str, destination: str, deviceId: str | None = None) -> dict[str, Any]:
    s, d = resolve_allowed(source), resolve_allowed(destination)
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))
    audit("move_file", True, {"source": str(s), "destination": str(d)})
    return {"ok": True, "destination": str(d)}

@tracked_tool()
def get_file_info(path: str, deviceId: str | None = None) -> dict[str, Any]:
    p = resolve_allowed(path)
    st = p.stat()
    info = {
        "path": str(p), "type": "directory" if p.is_dir() else "file",
        "size": st.st_size, "created": st.st_ctime, "modified": st.st_mtime,
        "mode": oct(st.st_mode)
    }
    if p.is_file() and p.suffix.lower() not in {".pdf",".docx",".xlsx",".xlsm",".png",".jpg",".jpeg",".gif",".webp"}:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        info.update({"lineCount": len(lines), "lastLine": max(-1, len(lines)-1), "appendPosition": len(lines)})
    if p.suffix.lower() in {".xlsx",".xlsm"}:
        wb = load_workbook(p, read_only=True)
        info["sheets"] = [{"name": ws.title, "rowCount": ws.max_row, "colCount": ws.max_column} for ws in wb.worksheets]
    return info

@tracked_tool()
def list_directory(path: str, depth: int = 2, deviceId: str | None = None) -> list[str]:
    root = resolve_allowed(path)
    out: list[str] = []
    def walk(cur: Path, level: int) -> None:
        if level > depth: return
        try:
            items = sorted(cur.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            out.append(f"[DENIED] {cur.relative_to(root) if cur != root else '.'}")
            return
        for item in items[:100 if cur != root else None]:
            rel = item.relative_to(root)
            out.append(f"[DIR] {rel}" if item.is_dir() else f"[FILE] {rel}")
            if item.is_dir(): walk(item, level + 1)
        if cur != root and len(items) > 100:
            out.append(f"[WARNING] {cur.name}: {len(items)-100} items hidden")
    walk(root, 1)
    return out

@tracked_tool()
def edit_block(file_path: str, old_string: str | None = None, new_string: str | None = None,
               expected_replacements: int = 1, range: str | None = None, content: list[list[Any]] | None = None, deviceId: str | None = None) -> dict[str, Any]:
    p = resolve_allowed(file_path)
    if p.suffix.lower() in {".xlsx",".xlsm"}:
        if not range or content is None: raise ValueError("range and content required")
        wb = load_workbook(p)
        if "!" in range:
            sheet_name, rg = range.split("!", 1)
            ws = wb[sheet_name]
        else:
            ws, rg = wb.active, range
        rows = ws[rg]
        for r_i, row in enumerate(rows):
            for c_i, cell in enumerate(row):
                if r_i < len(content) and c_i < len(content[r_i]):
                    cell.value = content[r_i][c_i]
        wb.save(p)
        return {"ok": True, "updated": range}
    if old_string is None or new_string is None: raise ValueError("old_string/new_string required")
    if p.suffix.lower() == ".docx":
        with zipfile.ZipFile(p, "r") as z:
            files = {n: z.read(n) for n in z.namelist()}
        names = [n for n in files if n == "word/document.xml" or n.startswith("word/header") or n.startswith("word/footer")]
        total = sum(files[n].decode("utf-8", errors="replace").count(old_string) for n in names)
        if total != expected_replacements: raise ValueError(f"expected {expected_replacements} replacements, found {total}")
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            for n, data in files.items():
                if n in names:
                    txt = data.decode("utf-8", errors="replace").replace(old_string, new_string)
                    data = txt.encode("utf-8")
                z.writestr(n, data)
    else:
        txt = p.read_text(encoding="utf-8", errors="replace")
        found = txt.count(old_string)
        if found != expected_replacements: raise ValueError(f"expected {expected_replacements} replacements, found {found}")
        p.write_text(txt.replace(old_string, new_string), encoding="utf-8")
    audit("edit_block", True, {"path": str(p)})
    return {"ok": True, "replacements": expected_replacements}

def markdown_pdf(markdown: str, output: Path) -> None:
    story = []
    for block in markdown.split("\n\n"):
        if "page-break-before: always" in block:
            from reportlab.platypus import PageBreak
            story.append(PageBreak()); continue
        txt = re.sub(r"^#{1,6}\s*", "", block.strip())
        if txt:
            story.extend([Paragraph(txt.replace("\n","<br/>")), Spacer(1, 8)])
    SimpleDocTemplate(str(output), pagesize=letter).build(story)

@tracked_tool()
def write_pdf(path: str, content: Any, outputPath: str | None = None, options: dict[str, Any] | None = None, deviceId: str | None = None) -> dict[str, Any]:
    src = resolve_allowed(path)
    if isinstance(content, str):
        target = resolve_allowed(outputPath or path)
        target.parent.mkdir(parents=True, exist_ok=True)
        markdown_pdf(content, target)
        return {"ok": True, "path": str(target)}
    target = resolve_allowed(outputPath) if outputPath else None
    if target is None: raise ValueError("outputPath required for PDF modification")
    reader = PdfReader(str(src))
    pages = list(reader.pages)
    for op in content:
        if op["type"] == "delete":
            for idx in sorted(op["pageIndexes"], reverse=True):
                del pages[idx]
        elif op["type"] == "insert":
            idx = op["pageIndex"]
            if op.get("sourcePdfPath"):
                insert_pages = list(PdfReader(str(resolve_allowed(op["sourcePdfPath"]))).pages)
            else:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                    tmp = Path(tf.name)
                markdown_pdf(op.get("markdown",""), tmp)
                insert_pages = list(PdfReader(str(tmp)).pages)
                tmp.unlink(missing_ok=True)
            pages[idx:idx] = insert_pages
    writer = PdfWriter()
    for pg in pages: writer.add_page(pg)
    with target.open("wb") as f: writer.write(f)
    return {"ok": True, "path": str(target)}

@dataclass
class SearchJob:
    id: str
    results: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    stop: bool = False
    started: float = field(default_factory=time.time)

SEARCHES: dict[str, SearchJob] = {}

def _hidden(path: Path) -> bool:
    if path.name.startswith("."): return True
    try: return bool(getattr(path.stat(), "st_file_attributes", 0) & 2)
    except Exception: return False

def search_worker(job: SearchJob, root: Path, pattern: str, search_type: str, file_pattern: str | None,
                  ignore_case: bool, literal: bool, include_hidden: bool, max_results: int,
                  timeout_ms: int | None, context_lines: int, early_termination: bool | None) -> None:
    flags = re.I if ignore_case else 0
    rx = None if literal else re.compile(pattern, flags)
    needle = pattern.lower() if ignore_case else pattern
    deadline = time.time() + timeout_ms / 1000 if timeout_ms else None
    early = (search_type == "files") if early_termination is None else early_termination
    try:
        for base, dirs, files in os.walk(root):
            if job.stop or (deadline and time.time() >= deadline): break
            if not include_hidden: dirs[:] = [d for d in dirs if not _hidden(Path(base) / d)]
            for name in files:
                if job.stop or (deadline and time.time() >= deadline): break
                p = Path(base) / name
                if not include_hidden and _hidden(p): continue
                if file_pattern and not any(fnmatch.fnmatch(name, x) for x in file_pattern.split("|")): continue
                try:
                    if search_type == "files":
                        hay = name.lower() if ignore_case else name
                        matched = needle in hay if literal else bool(rx.search(name))
                        if matched:
                            job.results.append({"path": str(p)})
                            if early and hay == needle: job.stop = True
                    else:
                        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                        for idx, line in enumerate(lines):
                            hay = line.lower() if ignore_case else line
                            matched = needle in hay if literal else bool(rx.search(line))
                            if matched:
                                lo=max(0,idx-context_lines); hi=min(len(lines),idx+context_lines+1)
                                job.results.append({"path":str(p),"lineNumber":idx+1,"line":line,"context":lines[lo:hi]})
                                if len(job.results) >= max_results: job.stop = True; break
                    if len(job.results) >= max_results: job.stop = True
                except Exception: pass
                if job.stop: break
            if job.stop: break
    finally:
        job.done = True

@tracked_tool()
def start_search(pattern: str, path: str, maxResults: int | None = None, includeHidden: bool = False,
                 timeout_ms: int | None = None, contextLines: int = 5, filePattern: str | None = None,
                 ignoreCase: bool = True, searchType: Literal["files", "content"] = "files",
                 earlyTermination: bool | None = None, deviceId: str | None = None,
                 literalSearch: bool = False) -> dict[str, Any]:
    root = resolve_allowed(path)
    limit = int(maxResults or load_config().get("searchResultLimit", 500))
    sid = uuid.uuid4().hex
    job = SearchJob(sid); SEARCHES[sid] = job
    threading.Thread(target=search_worker, args=(job,root,pattern,searchType,filePattern,ignoreCase,literalSearch,includeHidden,limit,timeout_ms,contextLines,earlyTermination), daemon=True).start()
    return {"sessionId": sid}

@tracked_tool()
def get_more_search_results(sessionId: str, offset: int = 0, length: int = 100, deviceId: str | None = None) -> dict[str, Any]:
    job = SEARCHES[sessionId]
    return {"results": job.results[offset:offset+length], "done": job.done, "total": len(job.results)}

@tracked_tool()
def stop_search(sessionId: str, deviceId: str | None = None) -> dict[str, Any]:
    SEARCHES[sessionId].stop = True
    return {"ok": True}

@tracked_tool()
def list_searches(deviceId: str | None = None) -> list[dict[str, Any]]:
    return [{"sessionId":k,"done":v.done,"results":len(v.results),"runtime":time.time()-v.started} for k,v in SEARCHES.items()]

@dataclass
class ProcSession:
    popen: subprocess.Popen
    started: float
    output: list[str] = field(default_factory=list)
    cursor: int = 0

PROCS: dict[int, ProcSession] = {}

def pump_output(sess: ProcSession) -> None:
    assert sess.popen.stdout is not None
    for line in iter(sess.popen.stdout.readline, ""):
        sess.output.append(line.rstrip("\r\n"))

@tracked_tool()
def start_process(timeout_ms: int, command: str, verbose_timing: bool = False, shell: str | None = None, deviceId: str | None = None) -> dict[str, Any]:
    exe = shell or None
    p = subprocess.Popen(command, shell=True if exe is None else False, executable=exe,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, bufsize=1)
    sess = ProcSession(p, time.time()); PROCS[p.pid] = sess
    threading.Thread(target=pump_output, args=(sess,), daemon=True).start()
    deadline = time.time() + max(0, timeout_ms)/1000
    while time.time() < deadline and p.poll() is None and not sess.output:
        time.sleep(0.05)
    return {"pid": p.pid, "running": p.poll() is None, "output": sess.output[-100:]}

@tracked_tool()
def read_process_output(pid: int, timeout_ms: int = 1000, offset: int = 0, length: int = 1000,
                        verbose_timing: bool = False, deviceId: str | None = None) -> dict[str, Any]:
    s = PROCS[pid]
    if offset == 0:
        deadline = time.time() + min(timeout_ms,10000)/1000
        while time.time() < deadline and len(s.output) <= s.cursor and s.popen.poll() is None: time.sleep(0.05)
        data = s.output[s.cursor:s.cursor+length]; s.cursor += len(data)
    elif offset < 0:
        data = s.output[offset:][:length]
    else:
        data = s.output[offset:offset+length]
    return {"pid": pid, "output": data, "running": s.popen.poll() is None, "returncode": s.popen.poll()}

@tracked_tool()
def interact_with_process(pid: int, input: str, timeout_ms: int = 8000, wait_for_prompt: bool = True,
                          verbose_timing: bool = False, deviceId: str | None = None) -> dict[str, Any]:
    s = PROCS[pid]
    if s.popen.stdin is None: raise RuntimeError("stdin unavailable")
    before = len(s.output)
    s.popen.stdin.write(input + "\n"); s.popen.stdin.flush()
    deadline = time.time() + min(timeout_ms,10000)/1000
    while wait_for_prompt and time.time() < deadline and len(s.output) == before and s.popen.poll() is None: time.sleep(0.05)
    return {"pid": pid, "output": s.output[before:], "running": s.popen.poll() is None}

@tracked_tool()
def force_terminate(pid: int, deviceId: str | None = None) -> dict[str, Any]:
    s = PROCS[pid]
    s.popen.kill()
    return {"ok": True, "pid": pid}

@tracked_tool()
def list_sessions(deviceId: str | None = None) -> list[dict[str, Any]]:
    return [{"pid": pid, "running": s.popen.poll() is None, "runtime": time.time()-s.started, "lines": len(s.output)} for pid,s in PROCS.items()]

@tracked_tool()
def list_processes(deviceId: str | None = None) -> list[dict[str, Any]]:
    out = []
    for p in psutil.process_iter(["pid","name","cpu_percent","memory_info","cmdline"]):
        try:
            i=p.info; out.append({"pid":i["pid"],"name":i["name"],"cpu":i["cpu_percent"],
                "memory": getattr(i["memory_info"],"rss",None),"cmdline":i["cmdline"]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return out

@tracked_tool()
def kill_process(pid: int, deviceId: str | None = None) -> dict[str, Any]:
    psutil.Process(pid).kill()
    audit("kill_process", True, {"pid": pid})
    return {"ok": True, "pid": pid}

@tracked_tool()
def get_usage_stats(deviceId: str | None = None) -> dict[str, Any]:
    count = 0
    if AUDIT_PATH.exists():
        with AUDIT_PATH.open("r", encoding="utf-8") as f:
            count = sum(1 for _ in f)
    return {"localToolCallsLogged": count, "quotaPercent": 0}

@tracked_tool()
def get_recent_tool_calls(maxResults: int = 50, toolName: str | None = None, since: str | None = None, deviceId: str | None = None) -> list[dict[str, Any]]:
    rows = list(RECENT_TOOL_CALLS)
    if toolName: rows = [r for r in rows if r.get("tool") == toolName]
    if since: rows = [r for r in rows if str(r.get("time", "")) >= since]
    return rows[-max(1, min(int(maxResults), 1000)): ]

@tracked_tool()
def shutdown(deviceId: str | None = None) -> dict[str, Any]:
    def later():
        time.sleep(0.25)
        os._exit(0)
    threading.Thread(target=later, daemon=True).start()
    return {"ok": True, "message": "VexBridge shutting down"}


BUS_DIR = APP_DIR / "bus"
BUS_PRIVATE_KEY = BUS_DIR / "identity_x25519.key"
BUS_PUBLIC_KEY = BUS_DIR / "identity_x25519.pub"
BUS_SHARED_KEY = BUS_DIR / "shared_aes.key"
BUS_PROCESSED = BUS_DIR / "processed.json"
BUS_COMMAND_URL = "https://raw.githubusercontent.com/hiitsmestar/vex-native/vexbridge-bus/VexBridgeBus/command.json"
BUS_BOOTSTRAP_BASE = "https://raw.githubusercontent.com/hiitsmestar/vex-native/vexbridge-bus/VexBridgeBus/bootstrap"
BUS_RESULT_TOPIC = "vexbridge-results-20260926-a17c6f42"
BUS_TOOL_ALLOW = {
    "ping","list_devices","who_am_i","get_prompts","give_feedback_to_desktop_commander",
    "get_config","set_config_value","read_file","read_multiple_files","write_file","write_pdf",
    "create_directory","list_directory","move_file","start_search","get_more_search_results",
    "stop_search","list_searches","get_file_info","edit_block","start_process","read_process_output",
    "interact_with_process","force_terminate","list_sessions","list_processes","kill_process",
    "get_usage_stats","get_recent_tool_calls","shutdown",
}

def _bus_b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")

def _bus_b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode("ascii"))

def _bus_identity() -> X25519PrivateKey:
    BUS_DIR.mkdir(parents=True, exist_ok=True)
    if BUS_PRIVATE_KEY.exists():
        return X25519PrivateKey.from_private_bytes(BUS_PRIVATE_KEY.read_bytes())
    private = X25519PrivateKey.generate()
    raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    BUS_PRIVATE_KEY.write_bytes(raw)
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    BUS_PUBLIC_KEY.write_text(_bus_b64e(public), encoding="ascii")
    return private

def _bus_export_public(alias: str, private: X25519PrivateKey) -> None:
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    (BUS_DIR / "public.json").write_text(
        json.dumps({"version":1,"alias":alias,"public_key":_bus_b64e(public)}, indent=2),
        encoding="utf-8",
    )

def _bus_fetch_json(url: str) -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(
            url + ("&" if "?" in url else "?") + "t=" + str(int(time.time())),
            headers={"User-Agent":"VexBridgeBus/1"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def _bus_try_bootstrap(alias: str, private: X25519PrivateKey) -> bytes | None:
    if BUS_SHARED_KEY.exists():
        key = BUS_SHARED_KEY.read_bytes()
        return key if len(key) == 32 else None
    env = _bus_fetch_json(f"{BUS_BOOTSTRAP_BASE}/{alias}.json")
    if not env or env.get("alias") != alias:
        return None
    try:
        peer = X25519PublicKey.from_public_bytes(_bus_b64d(str(env["ephemeral_public"])))
        shared = private.exchange(peer)
        wrap_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"vexbridge-bootstrap-v1",
        ).derive(shared)
        clear = AESGCM(wrap_key).decrypt(
            _bus_b64d(str(env["nonce"])),
            _bus_b64d(str(env["ciphertext"])),
            alias.encode("utf-8"),
        )
        if len(clear) != 32:
            raise ValueError("bad bus key length")
        BUS_SHARED_KEY.write_bytes(clear)
        export_path = os.environ.get("VEXBRIDGE_DROPBOX_KEY_EXPORT", "").strip()
        if export_path:
            p = Path(os.path.expandvars(os.path.expanduser(export_path)))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({
                "version":1,
                "algorithm":"AES-256-GCM",
                "bus_key":_bus_b64e(clear),
            }), encoding="utf-8")
        return clear
    except Exception as exc:
        audit("bus_bootstrap", False, {"alias":alias,"error":str(exc)})
        return None

def _bus_processed_ids() -> set[str]:
    try:
        raw = json.loads(BUS_PROCESSED.read_text(encoding="utf-8"))
        return set(str(x) for x in raw[-500:])
    except Exception:
        return set()

def _bus_mark_processed(command_id: str, seen: set[str]) -> None:
    seen.add(command_id)
    ordered = list(seen)[-500:]
    BUS_PROCESSED.write_text(json.dumps(ordered), encoding="utf-8")

def _bus_publish_result(key: bytes, command_id: str, alias: str, payload: dict[str, Any]) -> None:
    clear = json.dumps(payload, ensure_ascii=False, default=str, separators=(",",":")).encode("utf-8")
    nonce = os.urandom(12)
    aad = (command_id + "|" + alias).encode("utf-8")
    encrypted = AESGCM(key).encrypt(nonce, clear, aad)
    encoded = _bus_b64e(encrypted)
    chunk_size = 2200
    chunks = [encoded[i:i+chunk_size] for i in range(0, len(encoded), chunk_size)] or [""]
    for idx, chunk in enumerate(chunks):
        message = json.dumps({
            "v":1,"id":command_id,"node":alias,
            "i":idx,"n":len(chunks),"nonce":_bus_b64e(nonce),"chunk":chunk,
        }, separators=(",",":")).encode("utf-8")
        req = urllib.request.Request(
            f"https://ntfy.sh/{BUS_RESULT_TOPIC}",
            data=message,
            method="POST",
            headers={"Content-Type":"text/plain; charset=utf-8","User-Agent":"VexBridgeBus/1"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()

def _bus_execute(tool: str, arguments: dict[str, Any]) -> Any:
    if tool not in BUS_TOOL_ALLOW:
        raise ValueError(f"tool not allowed: {tool}")
    fn = globals().get(tool)
    if not callable(fn):
        raise ValueError(f"tool unavailable: {tool}")
    return fn(**arguments)

def _bus_loop() -> None:
    alias = os.environ.get("VEXBRIDGE_NODE_ALIAS", socket.gethostname()).strip().lower()
    private = _bus_identity()
    _bus_export_public(alias, private)
    seen = _bus_processed_ids()
    key: bytes | None = None
    while True:
        try:
            if key is None:
                key = _bus_try_bootstrap(alias, private)
                if key is None:
                    time.sleep(5)
                    continue
            env = _bus_fetch_json(BUS_COMMAND_URL)
            if not env:
                time.sleep(4)
                continue
            command_id = str(env.get("id",""))
            target = str(env.get("target","")).lower()
            if not command_id or command_id in seen or target not in {alias,"all"}:
                time.sleep(4)
                continue
            try:
                nonce = _bus_b64d(str(env["nonce"]))
                encrypted = _bus_b64d(str(env["ciphertext"]))
                aad = (command_id + "|" + target).encode("utf-8")
                clear = AESGCM(key).decrypt(nonce, encrypted, aad)
                command = json.loads(clear.decode("utf-8"))
                tool = str(command["tool"])
                arguments = dict(command.get("arguments") or {})
                result = _bus_execute(tool, arguments)
                payload = {"ok":True,"tool":tool,"result":result,"time":time.time()}
            except Exception as exc:
                payload = {"ok":False,"error":f"{type(exc).__name__}: {exc}","time":time.time()}
            _bus_publish_result(key, command_id, alias, payload)
            _bus_mark_processed(command_id, seen)
        except Exception as exc:
            audit("bus_loop", False, {"alias":alias,"error":str(exc)})
        time.sleep(4)

def _start_bus_worker() -> None:
    if os.environ.get("VEXBRIDGE_BUS_ENABLED", "").strip().lower() not in {"1","true","yes","on"}:
        return
    threading.Thread(target=_bus_loop, name="VexBridgeBus", daemon=True).start()

class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        token = os.environ.get("VEXBRIDGE_TOKEN", "")
        if token:
            supplied = request.headers.get("authorization", "")
            expected = "Bearer " + token
            if not hmac.compare_digest(supplied, expected):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

if __name__ == "__main__":
    _start_bus_worker()
    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuthMiddleware)
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT, log_level="info")
