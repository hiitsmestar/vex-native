from pathlib import Path
p=Path('Tools/VexRemoteSupport.py')
s=p.read_text(encoding='utf-8')
if 'VERSION = "0.11.7.62"' not in s:
    raise SystemExit('expected v0.11.7.62 source')
s=s.replace('VERSION = "0.11.7.62"','VERSION = "0.11.7.67"',1)
if 'SESSION_SECONDS = 2 * 60 * 60' not in s:
    raise SystemExit('2-hour session constant missing')
s=s.replace('SESSION_SECONDS = 2 * 60 * 60','SESSION_SECONDS = 24 * 60 * 60',1)
p.write_text(s,encoding='utf-8')
compile(s,str(p),'exec')
print('Applied v0.11.7.67 24-hour Remote Support session')
