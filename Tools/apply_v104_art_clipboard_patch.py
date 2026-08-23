#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexArtWorker.py")
text = path.read_text(encoding="utf-8")
if 'VERSION = "0.10.3"' not in text:
    raise SystemExit("VexArtWorker v0.10.3 marker missing")
text = text.replace('VERSION = "0.10.3"', 'VERSION = "0.10.4"', 1)

marker = '    prompt_box.insert("1.0", "photorealistic portrait of a stylish alternative woman, natural skin texture, dramatic but believable lighting")\n'
if marker not in text:
    raise SystemExit("prompt box marker missing")

clipboard = r'''    # Explicit Windows-friendly clipboard behavior for the prompt editor.
    # ScrolledText/Tk defaults vary across frozen builds, so bind everything
    # ourselves instead of making the user fight the widget.
    def _prompt_copy(event=None):
        try:
            selected = prompt_box.get("sel.first", "sel.last")
            root.clipboard_clear()
            root.clipboard_append(selected)
        except tk.TclError:
            pass
        return "break"

    def _prompt_cut(event=None):
        try:
            selected = prompt_box.get("sel.first", "sel.last")
            root.clipboard_clear()
            root.clipboard_append(selected)
            prompt_box.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        return "break"

    def _prompt_paste(event=None):
        try:
            value = root.clipboard_get()
        except tk.TclError:
            return "break"
        try:
            prompt_box.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        prompt_box.insert("insert", value)
        prompt_box.focus_set()
        return "break"

    def _prompt_select_all(event=None):
        prompt_box.tag_add("sel", "1.0", "end-1c")
        prompt_box.mark_set("insert", "1.0")
        prompt_box.see("insert")
        return "break"

    def _prompt_clear():
        prompt_box.delete("1.0", "end")
        prompt_box.focus_set()

    for seq, handler in (
        ("<Control-c>", _prompt_copy),
        ("<Control-C>", _prompt_copy),
        ("<Control-x>", _prompt_cut),
        ("<Control-X>", _prompt_cut),
        ("<Control-v>", _prompt_paste),
        ("<Control-V>", _prompt_paste),
        ("<Control-a>", _prompt_select_all),
        ("<Control-A>", _prompt_select_all),
    ):
        prompt_box.bind(seq, handler)

    prompt_menu = tk.Menu(root, tearoff=0)
    prompt_menu.add_command(label="Cut", command=_prompt_cut)
    prompt_menu.add_command(label="Copy", command=_prompt_copy)
    prompt_menu.add_command(label="Paste", command=_prompt_paste)
    prompt_menu.add_separator()
    prompt_menu.add_command(label="Select All", command=_prompt_select_all)
    prompt_menu.add_command(label="Clear", command=_prompt_clear)

    def _show_prompt_menu(event):
        try:
            prompt_menu.tk_popup(event.x_root, event.y_root)
        finally:
            prompt_menu.grab_release()
        return "break"

    prompt_box.bind("<Button-3>", _show_prompt_menu)

    prompt_tools = tk.Frame(top)
    prompt_tools.pack(fill="x", pady=(0, 6))
    tk.Button(prompt_tools, text="Paste", command=_prompt_paste, width=10).pack(side="left", padx=(0, 4))
    tk.Button(prompt_tools, text="Copy", command=_prompt_copy, width=10).pack(side="left", padx=4)
    tk.Button(prompt_tools, text="Select All", command=_prompt_select_all, width=10).pack(side="left", padx=4)
    tk.Button(prompt_tools, text="Clear", command=_prompt_clear, width=10).pack(side="left", padx=4)
'''
text = text.replace(marker, marker + clipboard + "\n", 1)

checks = [
    'VERSION = "0.10.4"',
    'def _prompt_paste',
    'prompt_menu.add_command(label="Paste"',
    'text="Paste"',
    '"<Control-v>"',
]
for check in checks:
    if check not in text:
        raise SystemExit(f"clipboard patch missing marker: {check}")

path.write_text(text, encoding="utf-8")
print("Applied VexArtWorker v0.10.4 clipboard UX patch")
