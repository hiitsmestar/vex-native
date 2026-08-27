from pathlib import Path

p = Path('Bridge/vex_bridge.py')
s = p.read_text(encoding='utf-8')

# Bump packaged Bridge identity after the full proven chain.
s = s.replace('"version": "0.11.7.29"', '"version": "0.11.7.34"')
s = s.replace('VexBridge/0.11.7.29', 'VexBridge/0.11.7.34')

# PyInstaller --windowed can leave sys.stdout as None. BaseHTTPRequestHandler
# calls log_message during send_response(), so the old sys.stdout.write logger
# can kill every request handler before headers are sent. Make logging harmless
# in the packaged GUI runtime.
old_log = '''    def log_message(self, fmt: str, *args) -> None:\n        sys.stdout.write("[%s] %s\\n" % (self.log_date_time_string(), fmt % args))\n'''
new_log = '''    def log_message(self, fmt: str, *args) -> None:\n        try:\n            out = getattr(sys, "stdout", None)\n            if out is not None:\n                out.write("[%s] %s\\n" % (self.log_date_time_string(), fmt % args))\n        except Exception:\n            pass\n'''
if old_log in s:
    s = s.replace(old_log, new_log, 1)
elif 'out = getattr(sys, "stdout", None)' not in s:
    raise SystemExit('windowed-safe HTTP logger anchor not found')

# Add nonblocking initial-index state when this class shape is present.
old = '''class BridgeState:\n    def __init__(self, config: dict):\n        self.config = config\n        self.index = LocalIndex(config.get("folders", []))\n        self.started = time.time()\n'''
new = '''class BridgeState:\n    def __init__(self, config: dict):\n        self.config = config\n        self.index = LocalIndex(config.get("folders", []))\n        self.started = time.time()\n        self.indexing = False\n        self.index_error = None\n'''
if old in s:
    s = s.replace(old, new, 1)

# Make /status useful while the first index is still running.
needle = '"uptime_seconds": int(time.time() - STATE.started),'
if needle in s and '"indexing": bool(getattr(STATE, "indexing", False))' not in s:
    s = s.replace(needle, needle + '\n                "indexing": bool(getattr(STATE, "indexing", False)),\n                "index_error": getattr(STATE, "index_error", None),', 1)

helper = '''\n\ndef start_initial_reindex(state: BridgeState) -> None:\n    def work() -> None:\n        state.indexing = True\n        state.index_error = None\n        try:\n            state.index.rebuild()\n        except Exception as exc:\n            state.index_error = exc.__class__.__name__\n        finally:\n            state.indexing = False\n    threading.Thread(target=work, daemon=True, name="VexBridgeInitialIndex").start()\n'''
anchor = '\ndef start_background_reindex(state: BridgeState) -> None:\n'
if 'def start_initial_reindex(state: BridgeState)' not in s and anchor in s:
    s = s.replace(anchor, helper + anchor, 1)

# Replace the generated chain's foreground initial index regardless of whether
# later patches inserted lines between rebuild() and the background scheduler.
call_anchor = '    state.index.rebuild()\n'
if call_anchor in s:
    s = s.replace(call_anchor, '    start_initial_reindex(state)\n', 1)

# Alternate generated form seen in some chain revisions.
s = s.replace('    initial_index_thread = threading.Thread(target=state.index.rebuild, daemon=True)\n    initial_index_thread.start()\n', '    start_initial_reindex(state)\n', 1)

if 'def start_initial_reindex(state: BridgeState)' not in s:
    raise SystemExit('responsive bootstrap helper anchor not found')
if '    start_initial_reindex(state)\n' not in s:
    raise SystemExit('responsive bootstrap call not installed')
if 'out = getattr(sys, "stdout", None)' not in s:
    raise SystemExit('windowed-safe HTTP logger not installed')
if '"version": "0.11.7.34"' not in s:
    raise SystemExit('v0.11.7.34 version marker not installed')

p.write_text(s, encoding='utf-8')
print('Applied v0.11.7.34 responsive Bridge bootstrap + windowed HTTP logger patch')
