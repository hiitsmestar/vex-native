#!/usr/bin/env python3
from pathlib import Path

src = Path("Tools/VexWindowsHost-v11735.py").read_text(encoding="utf-8")

src = src.replace('VERSION = "0.11.7.35"', 'VERSION = "0.11.7.36"', 1)

old = '''        self.log = tk.Text(self, bg="#1f1125", fg="#f7edf9", insertbackground="white", relief="flat", wrap="word", font=("Segoe UI", 12))\n        self.log.pack(fill="both", expand=True, padx=18, pady=(0, 12))\n        self.log.insert("end", "Vex Windows host ready. PC Brain routing enabled; shared phone/PC relay and lightweight LAN nodes are attached to the same Bridge.\\n\\n")\n        self.log.configure(state="disabled")\n'''
new = '''        self.log = tk.Text(self, bg="#1f1125", fg="#f7edf9", insertbackground="white", relief="flat", wrap="word", font=("Segoe UI", 12))\n        self.log.pack(fill="both", expand=True, padx=18, pady=(0, 12))\n        self.log.insert("end", "Vex Windows host ready. PC Brain routing enabled; shared phone/PC relay and lightweight LAN nodes are attached to the same Bridge.\\n\\n")\n        self.log.configure(state="disabled")\n        self.log.bind("<Control-c>", self.copy_selection)\n        self.log.bind("<Control-C>", self.copy_selection)\n        self.log.bind("<Button-3>", self.show_log_menu)\n        self.log_menu = tk.Menu(self, tearoff=0)\n        self.log_menu.add_command(label="Copy", command=self.copy_selection)\n        self.last_vex_reply = ""\n'''
if old not in src:
    raise SystemExit("log widget anchor missing")
src = src.replace(old, new, 1)

old = '''        ttk.Button(row, text="Send", command=self.send).pack(side="left", padx=(8, 0))\n        ttk.Button(row, text="Ping phone", command=lambda: self.local_event("ping", "Windows ping")).pack(side="left", padx=(8, 0))\n'''
new = '''        ttk.Button(row, text="Send", command=self.send).pack(side="left", padx=(8, 0))\n        ttk.Button(row, text="Copy reply", command=self.copy_last_reply).pack(side="left", padx=(8, 0))\n        ttk.Button(row, text="Ping phone", command=lambda: self.local_event("ping", "Windows ping")).pack(side="left", padx=(8, 0))\n'''
if old not in src:
    raise SystemExit("button row anchor missing")
src = src.replace(old, new, 1)

old = '''    def append(self, who: str, text: str):\n        self.log.configure(state="normal")\n        self.log.insert("end", f"{who}: {text}\\n\\n")\n        self.log.see("end")\n        self.log.configure(state="disabled")\n\n'''
new = '''    def append(self, who: str, text: str):\n        self.log.configure(state="normal")\n        self.log.insert("end", f"{who}: {text}\\n\\n")\n        self.log.see("end")\n        self.log.configure(state="disabled")\n        if who == "Vex":\n            self.last_vex_reply = text\n\n    def copy_selection(self, event=None):\n        try:\n            text = self.log.get("sel.first", "sel.last")\n        except tk.TclError:\n            return "break"\n        self.clipboard_clear()\n        self.clipboard_append(text)\n        self.update_idletasks()\n        return "break"\n\n    def copy_last_reply(self):\n        text = str(getattr(self, "last_vex_reply", "") or "").strip()\n        if not text:\n            return\n        self.clipboard_clear()\n        self.clipboard_append(text)\n        self.update_idletasks()\n\n    def show_log_menu(self, event):\n        try:\n            self.log_menu.tk_popup(event.x_root, event.y_root)\n        finally:\n            self.log_menu.grab_release()\n\n'''
if old not in src:
    raise SystemExit("append anchor missing")
src = src.replace(old, new, 1)

for marker in [
    'VERSION = "0.11.7.36"',
    'text="Copy reply"',
    'def copy_selection(',
    'def copy_last_reply(',
    'def show_log_menu(',
    'self.log.bind("<Control-c>"',
]:
    if marker not in src:
        raise SystemExit(f"missing marker: {marker}")

Path("Tools/VexWindowsHost-v11736.py").write_text(src, encoding="utf-8")
compile(src, "Tools/VexWindowsHost-v11736.py", "exec")
print("Built v0.11.7.36 Host source with selectable transcript, Ctrl+C, right-click Copy, and Copy reply")
