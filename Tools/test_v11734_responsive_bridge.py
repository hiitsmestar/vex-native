import json, os, time
from pathlib import Path
import requests

config_path = Path(os.environ['APPDATA']) / 'VexBridge' / 'config.json'
deadline = time.time() + 25
last = 'no response'
while time.time() < deadline:
    try:
        cfg = json.loads(config_path.read_text(encoding='utf-8'))
        external_port = int(cfg.get('port', 8765))
        local_port = int(cfg.get('local_control_port') or (external_port + 1))
        response = requests.get(
            f'http://127.0.0.1:{local_port}/status',
            params={'token': cfg['token']},
            timeout=2,
        )
        last = response.text[:1000]
        if response.status_code == 200 and isinstance(response.json(), dict):
            body = response.json()
            if body.get('local_control_protocol') != 'vex-local-v1':
                raise RuntimeError('local control protocol marker missing')
            print(last)
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as exc:
        last = exc.__class__.__name__ + ': ' + str(exc)[:300]
    time.sleep(1)
raise SystemExit('Bridge local-control health did not answer during bootstrap: ' + str(last))
