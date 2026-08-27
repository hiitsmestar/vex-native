import json, os, time
from pathlib import Path
import requests

requests.packages.urllib3.disable_warnings()
config_path = Path(os.environ['APPDATA']) / 'VexBridge' / 'config.json'
deadline = time.time() + 20
last = 'no response'
while time.time() < deadline:
    try:
        cfg = json.loads(config_path.read_text(encoding='utf-8'))
        port = int(cfg.get('port', 8765))
        response = requests.get(
            f'https://127.0.0.1:{port}/status',
            params={'token': cfg['token']},
            verify=False,
            timeout=2,
        )
        last = response.text[:1000]
        if response.status_code == 200 and isinstance(response.json(), dict):
            print(last)
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as exc:
        last = exc.__class__.__name__
    time.sleep(1)
raise SystemExit('Bridge health did not answer during bootstrap: ' + str(last))
