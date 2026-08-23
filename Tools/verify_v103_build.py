#!/usr/bin/env python3
from pathlib import Path

worker = Path('Tools/VexArtWorker.py').read_text(encoding='utf-8')
remote = Path('Tools/VexRemoteSupport.py').read_text(encoding='utf-8')
bridge = Path('Bridge/vex_bridge.py').read_text(encoding='utf-8')
full = Path('Bridge/vex_bridge_full.py').read_text(encoding='utf-8')

required_worker = [
    'VERSION = "0.10.3"',
    'LITE_CHECKPOINT_NAME = "v1-5-pruned-emaonly-fp16.safetensors"',
    'e9476a13728cd75d8279f6ec8bad753a66a1957ca375a1464dc63b37db6e3916',
    'def _download_lite_model(',
    'def _quick_status(',
    'LiteModelRequired',
    'Install Lite Model',
    'model_profile == "sd15-lite"',
    'return (320, 320) if cpu else (512, 512)',
]
for marker in required_worker:
    assert marker in worker, marker
assert 'VERSION = "0.10.3"' in remote
assert '["--quick-status"]' in remote
assert 'MODULAR_ART_EXTERNAL = True' in bridge
assert '"version": "0.10.3"' in bridge
assert 'VERSION = "0.10.3"' in full
print('v0.10.3 verification OK')
