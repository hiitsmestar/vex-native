from pathlib import Path

bridge = Path('Bridge/vex_bridge.py')
remote = Path('Tools/VexRemoteSupport.py')

b = bridge.read_text('utf-8')
r = remote.read_text('utf-8')

if '"version": "0.11.7.18"' not in b:
    raise SystemExit('expected Bridge v0.11.7.18 marker missing')
if 'VERSION = "0.11.7.18"' not in r:
    raise SystemExit('expected Remote Support v0.11.7.18 marker missing')

b = b.replace('"version": "0.11.7.18"', '"version": "0.11.7.19"')
r = r.replace('VERSION = "0.11.7.18"', 'VERSION = "0.11.7.19"')

bridge.write_text(b, 'utf-8')
remote.write_text(r, 'utf-8')
print('Applied v0.11.7.19 bridge supervision/Doctor packaging markers')
