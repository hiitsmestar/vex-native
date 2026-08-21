#!/usr/bin/env python3
from pathlib import Path


def once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    return text.replace(old, new, 1)


path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

list_start = text.find("PC_TOOL_ACTIONS = [")
list_end = text.find("]\n", list_start)
if list_start < 0 or list_end < 0:
    raise SystemExit("vex_bridge.py: PC_TOOL_ACTIONS missing")
list_block = text[list_start:list_end]
new_actions = [
    "lock_screen",
    "open_windows_settings",
    "open_task_manager",
    "open_start_menu",
    "open_task_view",
    "open_run_dialog",
    "open_windows_search",
    "minimize_all_windows",
    "restore_all_windows",
    "close_active_window",
]
for action in new_actions:
    if f'"{action}"' not in list_block:
        list_block += f'    "{action}",\n'
text = text[:list_start] + list_block + text[list_end:]

run_marker = "def run_pc_tool_action(action: str, payload: dict | None = None) -> dict:\n"
if run_marker not in text:
    raise SystemExit("vex_bridge.py: action executor marker missing")
combo_helper = r'''def _press_windows_combo(keys: list[int]) -> None:
    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)


'''
if "def _press_windows_combo(" not in text:
    text = text.replace(run_marker, combo_helper + run_marker, 1)

executor_head = '''    try:
        if action == "play_named_media":
'''
executor_new = '''    try:
        if action == "lock_screen":
            if not ctypes.windll.user32.LockWorkStation():
                raise RuntimeError("Windows refused LockWorkStation")
            message = "workstation locked"
        elif action == "open_windows_settings":
            os.startfile("ms-settings:")
            message = "Windows Settings opened"
        elif action == "open_task_manager":
            taskmgr = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "System32" / "Taskmgr.exe"
            os.startfile(str(taskmgr))
            message = "Task Manager opened"
        elif action == "open_start_menu":
            _press_windows_combo([0x5B])
            message = "Start menu opened"
        elif action == "open_task_view":
            _press_windows_combo([0x5B, 0x09])
            message = "Task View opened"
        elif action == "open_run_dialog":
            _press_windows_combo([0x5B, 0x52])
            message = "Run dialog opened"
        elif action == "open_windows_search":
            _press_windows_combo([0x5B, 0x53])
            message = "Windows Search opened"
        elif action == "minimize_all_windows":
            _press_windows_combo([0x5B, 0x4D])
            message = "windows minimized"
        elif action == "restore_all_windows":
            _press_windows_combo([0x5B, 0x10, 0x4D])
            message = "windows restored"
        elif action == "close_active_window":
            _press_windows_combo([0x12, 0x73])
            message = "active window close requested"
        elif action == "play_named_media":
'''
text = once(text, executor_head, executor_new, "expanded Windows action executor")
path.write_text(text, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = once(full, 'VERSION = "0.9.1"', 'VERSION = "0.9.2"', "Bridge version")
full_path.write_text(full, encoding="utf-8")

for target, markers in [
    (path, ['"lock_screen"', '"open_windows_settings"', "_press_windows_combo", "LockWorkStation", "Taskmgr.exe"]),
    (full_path, ['VERSION = "0.9.2"']),
]:
    data = target.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{target}: missing v0.9.2 marker: {marker}")

print("Applied v0.9.2 expanded authenticated Windows controls")
