from pathlib import Path

p = Path('Tools/VexArtWorker.py')
t = p.read_text(encoding='utf-8')
checks = [
    'VERSION = "0.10.5"',
    'REALISM_CHECKPOINT_NAME = "realismByStableYogi_sd15V9.safetensors"',
    'f592c30e3fde778007bf103d37e5405f3212b73af7be3ed553d7511599555d56',
    'def _download_realism_model',
    'return REALISM_CHECKPOINT_NAME, "sd15-realism"',
    'sampler_name = "dpmpp_2m"',
    'scheduler = "karras"',
    'Install Realism Model',
    '--install-realism-model',
]
for item in checks:
    assert item in t, item
print('v0.10.5 realism checks OK')
