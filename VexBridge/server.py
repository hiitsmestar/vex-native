from __future__ import annotations

import base64
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil
from docx import Document
from mcp.server.fastmcp import FastMCP
from openpyxl import Workbook, load_workbook
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexBridge"
CONFIG_PATH = APP_DIR / "config.json"
AUDIT_PATH = APP_DIR / "audit.jsonl"
APP_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "allowedRoots": [str(Path.home())],
    "fileReadLineLimit": 1000,
    "searchResultLimit": 500,
}
if not CONFIG_PATH.exists():
    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")

MCP_HOST = os.environ.get("VEXBRIDGE_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("VEXBRIDGE_PORT", "8795"))
mcp = FastMCP("VexBridge", host=MCP_HOST, port=MCP_PORT, stateless_http=True, json_response=True)

def audit(tool: str, ok: bool, detail: dict[str, Any] | None = None) -> None:
    rec = {"ts": time.time(), "tool": tool, "ok": ok, "detail": detail or {}}
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def load_config() -> dict[str, Any]:
    try:
        return {**DEFAULT_CONFIG, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
    except Exception:
        return dict(DEFAULT_CONFIG)

def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def resolve_allowed(raw: str) -> Path:
    p = Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
    roots = [Path(os.path.expandvars(os.path.expanduser(x))).resolve() for x in load_config().get("allowedRoots", [])]
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

@mcp.tool()
def ping() -> dict[str, Any]:
    return {"pong": True, "host": socket.gethostname(), "time": time.time()}

@mcp.tool()
def get_config() -> dict[str, Any]:
    return load_config()

@mcp.tool()
def set_config_value(key: str, value: Any) -> dict[str, Any]:
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
    audit("set_config_value", True, {"key": key})
    return cfg

@mcp.tool()
def read_file(path: str, isUrl: bool = False, offset: int = 0, length: int = 1000,
              sheet: str | None = None, range: str | None = None, options: dict[str, Any] | None = None) -> Any:
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

@mcp.tool()
def read_multiple_files(paths: list[str]) -> dict[str, Any]:
    out = {}
    for p in paths:
        try:
            out[p] = read_file(p)
        except Exception as e:
            out[p] = {"error": str(e)}
    return out

@mcp.tool()
def write_file(path: str, content: str, mode: str = "rewrite") -> dict[str, Any]:
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

@mcp.tool()
def create_directory(path: str) -> dict[str, Any]:
    p = resolve_allowed(path)
    p.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": str(p)}

@mcp.tool()
def move_file(source: str, destination: str) -> dict[str, Any]:
    s, d = resolve_allowed(source), resolve_allowed(destination)
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))
    audit("move_file", True, {"source": str(s), "destination": str(d)})
    return {"ok": True, "destination": str(d)}

@mcp.tool()
def get_file_info(path: str) -> dict[str, Any]:
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

@mcp.tool()
def list_directory(path: str, depth: int = 2) -> list[str]:
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

@mcp.tool()
def edit_block(file_path: str, old_string: str | None = None, new_string: str | None = None,
               expected_replacements: int = 1, range: str | None = None, content: list[list[Any]] | None = None) -> dict[str, Any]:
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

@mcp.tool()
def write_pdf(path: str, content: Any, outputPath: str | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
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
    q: queue.Queue = field(default_factory=queue.Queue)
    done: bool = False
    stop: bool = False

SEARCHES: dict[str, SearchJob] = {}

def search_worker(job: SearchJob, root: Path, pattern: str, search_type: str,
                  file_pattern: str | None, ignore_case: bool, literal: bool) -> None:
    flags = re.I if ignore_case else 0
    rx = None if literal else re.compile(pattern, flags)
    needle = pattern.lower() if ignore_case else pattern
    try:
        for base, _, files in os.walk(root):
            if job.stop: break
            for name in files:
                if job.stop: break
                p = Path(base) / name
                if file_pattern and not any(fnmatch.fnmatch(name, x) for x in file_pattern.split("|")): continue
                try:
                    if search_type == "files":
                        hay = name.lower() if ignore_case else name
                        matched = needle in hay if literal else bool(rx.search(name))
                        if matched: job.q.put({"path": str(p)})
                    else:
                        txt = p.read_text(encoding="utf-8", errors="ignore")
                        hay = txt.lower() if ignore_case else txt
                        matched = needle in hay if literal else bool(rx.search(txt))
                        if matched: job.q.put({"path": str(p)})
                except Exception:
                    pass
    finally:
        job.done = True

@mcp.tool()
def start_search(path: str, pattern: str, searchType: str = "files", filePattern: str | None = None,
                 ignoreCase: bool = True, literalSearch: bool = False, earlyTermination: bool | None = None) -> dict[str, Any]:
    root = resolve_allowed(path)
    sid = uuid.uuid4().hex
    job = SearchJob(sid); SEARCHES[sid] = job
    threading.Thread(target=search_worker, args=(job, root, pattern, searchType, filePattern, ignoreCase, literalSearch), daemon=True).start()
    return {"sessionId": sid}

@mcp.tool()
def get_more_search_results(sessionId: str, offset: int = 0, length: int = 100) -> dict[str, Any]:
    job = SEARCHES[sessionId]
    results = []
    while len(results) < length:
        try: results.append(job.q.get_nowait())
        except queue.Empty: break
    return {"results": results, "done": job.done and job.q.empty()}

@mcp.tool()
def stop_search(sessionId: str) -> dict[str, Any]:
    SEARCHES[sessionId].stop = True
    return {"ok": True}

@mcp.tool()
def list_searches() -> list[dict[str, Any]]:
    return [{"sessionId": k, "done": v.done, "queued": v.q.qsize()} for k,v in SEARCHES.items()]

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

@mcp.tool()
def start_process(timeout_ms: int, command: str, verbose_timing: bool = False, shell: str | None = None) -> dict[str, Any]:
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

@mcp.tool()
def read_process_output(pid: int, timeout_ms: int = 1000, offset: int = 0, length: int = 1000,
                        verbose_timing: bool = False) -> dict[str, Any]:
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

@mcp.tool()
def interact_with_process(pid: int, input: str, timeout_ms: int = 8000, wait_for_prompt: bool = True,
                          verbose_timing: bool = False) -> dict[str, Any]:
    s = PROCS[pid]
    if s.popen.stdin is None: raise RuntimeError("stdin unavailable")
    before = len(s.output)
    s.popen.stdin.write(input + "\n"); s.popen.stdin.flush()
    deadline = time.time() + min(timeout_ms,10000)/1000
    while wait_for_prompt and time.time() < deadline and len(s.output) == before and s.popen.poll() is None: time.sleep(0.05)
    return {"pid": pid, "output": s.output[before:], "running": s.popen.poll() is None}

@mcp.tool()
def force_terminate(pid: int) -> dict[str, Any]:
    s = PROCS[pid]
    s.popen.kill()
    return {"ok": True, "pid": pid}

@mcp.tool()
def list_sessions() -> list[dict[str, Any]]:
    return [{"pid": pid, "running": s.popen.poll() is None, "runtime": time.time()-s.started, "lines": len(s.output)} for pid,s in PROCS.items()]

@mcp.tool()
def list_processes() -> list[dict[str, Any]]:
    out = []
    for p in psutil.process_iter(["pid","name","cpu_percent","memory_info","cmdline"]):
        try:
            i=p.info; out.append({"pid":i["pid"],"name":i["name"],"cpu":i["cpu_percent"],
                "memory": getattr(i["memory_info"],"rss",None),"cmdline":i["cmdline"]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return out

@mcp.tool()
def kill_process(pid: int) -> dict[str, Any]:
    psutil.Process(pid).kill()
    audit("kill_process", True, {"pid": pid})
    return {"ok": True, "pid": pid}

@mcp.tool()
def get_usage_stats() -> dict[str, Any]:
    count = 0
    if AUDIT_PATH.exists():
        with AUDIT_PATH.open("r", encoding="utf-8") as f:
            count = sum(1 for _ in f)
    return {"localToolCallsLogged": count, "quotaPercent": 0}

@mcp.tool()
def get_recent_tool_calls(limit: int = 50) -> list[dict[str, Any]]:
    if not AUDIT_PATH.exists(): return []
    lines = AUDIT_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    return [json.loads(x) for x in lines]

@mcp.tool()
def shutdown() -> dict[str, Any]:
    def later():
        time.sleep(0.25)
        os._exit(0)
    threading.Thread(target=later, daemon=True).start()
    return {"ok": True, "message": "VexBridge shutting down"}

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
