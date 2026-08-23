#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexRemoteSupport.py")
text = path.read_text(encoding="utf-8")

if 'VERSION = "0.9.9.1"' in text and "def send_ntfy" in text:
    print("v0.9.9.1 ntfy patch already applied")
    raise SystemExit(0)

if 'VERSION = "0.9.9"' not in text:
    raise SystemExit("v0.9.9 version marker missing")
text = text.replace('VERSION = "0.9.9"', 'VERSION = "0.9.9.1"', 1)

save_marker = '''def save_state(data: dict) -> None:\n    STATE_PATH.write_text(json.dumps(data, indent=2), "utf-8")\n\n'''
if save_marker not in text:
    raise SystemExit("save_state marker missing")

notify_code = r'''def save_state(data: dict) -> None:
    STATE_PATH.write_text(json.dumps(data, indent=2), "utf-8")


NTFY_SERVER = "https://ntfy.sh"


def _notify_seed_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "VexRemoteSupport-notify.json"
    return Path(__file__).resolve().parent / "VexRemoteSupport-notify.json"


def seed_notify_settings() -> None:
    """Import a local sidecar config once. The topic is never sent to GitHub."""
    seed = _notify_seed_path()
    if not seed.exists():
        return
    try:
        incoming = json.loads(seed.read_text("utf-8"))
        if not isinstance(incoming, dict):
            return
        state = load_state()
        changed = False
        raw_topic = str(incoming.get("ntfy_topic") or "").strip()
        if raw_topic and not state.get("ntfy_topic") and re.fullmatch(r"[A-Za-z0-9_-]{8,180}", raw_topic):
            state["ntfy_topic"] = raw_topic
            changed = True
        raw_label = str(incoming.get("node_label") or "").strip()
        if raw_label and not state.get("node_label"):
            state["node_label"] = raw_label[:48]
            changed = True
        if changed:
            save_state(state)
    except Exception:
        pass


def ntfy_settings() -> tuple[str, str]:
    state = load_state()
    topic = str(state.get("ntfy_topic") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,180}", topic):
        topic = ""
    label = str(state.get("node_label") or "Vex PC").strip()[:48] or "Vex PC"
    return topic, label


def save_ntfy_settings(topic: str, label: str) -> bool:
    topic = str(topic or "").strip()
    label = str(label or "").strip()[:48] or "Vex PC"
    if topic and not re.fullmatch(r"[A-Za-z0-9_-]{8,180}", topic):
        return False
    state = load_state()
    state["ntfy_topic"] = topic
    state["node_label"] = label
    save_state(state)
    return True


def send_ntfy(message: str, *, priority: str = "default") -> bool:
    """Send a deliberately low-detail phone notification through ntfy.sh."""
    topic, label = ntfy_settings()
    if not topic:
        return False
    try:
        response = requests.post(
            f"{NTFY_SERVER}/{topic}",
            data=str(message)[:500].encode("utf-8"),
            headers={
                "Title": f"Vex • {label}",
                "Priority": priority,
                "Tags": "computer",
            },
            timeout=12,
        )
        return 200 <= response.status_code < 300
    except Exception:
        return False


def notify_action(action: str, result: dict) -> None:
    names = {
        "status": "status check",
        "doctor": "quick diagnostic",
        "doctor_deep": "deep diagnostic",
        "bridge_status": "Bridge check",
        "art_health": "art-engine check",
        "learning_status": "learning check",
        "learning_queue": "learning queue update",
        "learning_run": "learning job",
        "maintenance_status": "maintenance check",
        "housekeeping_audit": "housekeeping audit",
        "maintenance_run": "safe maintenance",
    }
    pretty = names.get(str(action or "").lower(), str(action or "job").replace("_", " "))
    attention = False
    if isinstance(result, dict):
        if result.get("ok") is False:
            attention = True
        doctor = result.get("doctor")
        if isinstance(doctor, dict) and str(doctor.get("overall") or "").lower() not in {"", "healthy", "ok"}:
            attention = True
    send_ntfy(
        f"{pretty} {'needs attention' if attention else 'finished'}.",
        priority="high" if attention else "default",
    )

'''
text = text.replace(save_marker, notify_code, 1)

command_marker = '''                    result = execute_command(command, allow_maintenance=bool(self.allow_maintenance()))\n                    post_comment("command_result", {"command_id": command_id, "action": str(command.get("action") or "")[:80], "result": result})\n                    self.on_status("Support session is active")\n'''
if command_marker not in text:
    raise SystemExit("command completion marker missing")
command_replacement = '''                    action_name = str(command.get("action") or "")[:80]\n                    result = execute_command(command, allow_maintenance=bool(self.allow_maintenance()))\n                    post_comment("command_result", {"command_id": command_id, "action": action_name, "result": result})\n                    threading.Thread(target=notify_action, args=(action_name, result), daemon=True, name="VexPhoneNotify").start()\n                    self.on_status("Support session is active")\n'''
text = text.replace(command_marker, command_replacement, 1)

except_marker = '''        except Exception as exc:\n            self.on_status(f"Support error: {exc.__class__.__name__}")\n        finally:\n'''
if except_marker not in text:
    raise SystemExit("worker exception marker missing")
text = text.replace(
    except_marker,
    '''        except Exception as exc:\n            self.on_status(f"Support error: {exc.__class__.__name__}")\n            threading.Thread(target=send_ntfy, args=("Remote Support needs attention.",), kwargs={"priority": "high"}, daemon=True, name="VexPhoneNotifyError").start()\n        finally:\n''',
    1,
)

main_marker = '''def main() -> int:\n    import tkinter as tk\n'''
if main_marker not in text:
    raise SystemExit("main marker missing")
text = text.replace(main_marker, '''def main() -> int:\n    seed_notify_settings()\n    import tkinter as tk\n''', 1)

text = text.replace('root.geometry("760x640")', 'root.geometry("760x730")', 1)
text = text.replace('root.minsize(680, 560)', 'root.minsize(680, 650)', 1)

ui_marker = '''    allow_maintenance_var = tk.BooleanVar(value=False)\n    tk.Checkbutton(\n        root,\n        text="Allow remote SAFE maintenance during this session (safe junk only; protected/review files stay untouched)",\n        variable=allow_maintenance_var,\n        wraplength=700,\n        justify="left",\n    ).pack(anchor="w", padx=22, pady=(0, 10))\n\n    worker = SupportWorker(lambda: allow_maintenance_var.get())\n'''
if ui_marker not in text:
    raise SystemExit("maintenance UI marker missing")
ui_replacement = r'''    allow_maintenance_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        root,
        text="Allow remote SAFE maintenance during this session (safe junk only; protected/review files stay untouched)",
        variable=allow_maintenance_var,
        wraplength=700,
        justify="left",
    ).pack(anchor="w", padx=22, pady=(0, 8))

    saved_topic, saved_label = ntfy_settings()
    notify_box = tk.LabelFrame(root, text="iPhone completion notifications (ntfy)")
    notify_box.pack(fill="x", padx=18, pady=(0, 8))
    tk.Label(notify_box, text="Node label:").grid(row=0, column=0, sticky="w", padx=(8, 4), pady=6)
    node_label_var = tk.StringVar(value=saved_label)
    tk.Entry(notify_box, textvariable=node_label_var, width=18).grid(row=0, column=1, sticky="w", padx=4, pady=6)
    tk.Label(notify_box, text="Topic:").grid(row=0, column=2, sticky="w", padx=(10, 4), pady=6)
    ntfy_topic_var = tk.StringVar(value=saved_topic)
    tk.Entry(notify_box, textvariable=ntfy_topic_var, width=32, show="•").grid(row=0, column=3, sticky="ew", padx=4, pady=6)
    notify_box.columnconfigure(3, weight=1)

    def save_phone_notifications(show_message: bool = True) -> bool:
        ok = save_ntfy_settings(ntfy_topic_var.get(), node_label_var.get())
        if show_message:
            if ok:
                messagebox.showinfo("Vex Remote Support", "Phone notification settings saved locally on this PC.")
            else:
                messagebox.showwarning("Vex Remote Support", "That ntfy topic contains unsupported characters.")
        return ok

    def test_phone_notification() -> None:
        if not save_phone_notifications(show_message=False):
            messagebox.showwarning("Vex Remote Support", "Enter a valid ntfy topic first.")
            return
        if send_ntfy("Test notification — Vex can ping this phone when a job finishes."):
            messagebox.showinfo("Vex Remote Support", "Test ping sent. Check the ntfy app on your iPhone.")
        else:
            messagebox.showwarning("Vex Remote Support", "The test ping did not send. Check internet access and the topic.")

    tk.Button(notify_box, text="Save", command=save_phone_notifications, width=9).grid(row=1, column=2, padx=4, pady=(0, 7), sticky="e")
    tk.Button(notify_box, text="Test phone ping", command=test_phone_notification, width=15).grid(row=1, column=3, padx=4, pady=(0, 7), sticky="w")

    worker = SupportWorker(lambda: allow_maintenance_var.get())
'''
text = text.replace(ui_marker, ui_replacement, 1)

checks = [
    'VERSION = "0.9.9.1"',
    'NTFY_SERVER = "https://ntfy.sh"',
    'def send_ntfy',
    'def notify_action',
    'VexRemoteSupport-notify.json',
    'Test phone ping',
    'threading.Thread(target=notify_action',
]
for marker in checks:
    if marker not in text:
        raise SystemExit(f"missing ntfy marker after patch: {marker}")

path.write_text(text, encoding="utf-8")
print("Applied Vex Remote Support v0.9.9.1 ntfy completion notifications")
