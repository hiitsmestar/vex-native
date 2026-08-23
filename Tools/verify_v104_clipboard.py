from pathlib import Path

t = Path('Tools/VexArtWorker.py').read_text(encoding='utf-8')
checks = [
    'VERSION = "0.10.4"',
    'def _prompt_paste',
    'prompt_menu.add_command(label="Paste"',
    '<Control-v>',
    'text="Paste"',
    'text="Copy"',
    'text="Select All"',
    'text="Clear"',
]
for check in checks:
    if check not in t:
        raise SystemExit(f'missing marker: {check}')
print('v0.10.4 clipboard verification OK')
