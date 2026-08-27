from pathlib import Path

p = Path('Bridge/vex_bridge.py')
s = p.read_text(encoding='utf-8')

# Bump any packaged v0.11.7.29 Bridge identity markers after the full chain.
s = s.replace('"version": "0.11.7.29"', '"version": "0.11.7.34"')
s = s.replace('VexBridge/0.11.7.29', 'VexBridge/0.11.7.34')

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

# Replace blocking bootstrap if it survived earlier chain patches.
s = s.replace('    state.index.rebuild()\n    start_background_reindex(state)\n', '    start_initial_reindex(state)\n    start_background_reindex(state)\n', 1)

# A second common generated form used by later bridge patches.
s = s.replace('    initial_index_thread = threading.Thread(target=state.index.rebuild, daemon=True)\n    initial_index_thread.start()\n', '    start_initial_reindex(state)\n', 1)

if 'def start_initial_reindex(state: BridgeState)' not in s:
    raise SystemExit('responsive bootstrap helper anchor not found')
if 'start_initial_reindex(state)' not in s:
    raise SystemExit('responsive bootstrap call not installed')

p.write_text(s, encoding='utf-8')
print('Applied v0.11.7.34 responsive Bridge bootstrap patch')
# workflow trigger: field-test responsive health
