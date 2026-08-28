#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "Tools" / "VexAgentRuntimeInstall.py"
source = INSTALLER.read_text(encoding="utf-8")
compile(source, str(INSTALLER), "exec")

required = [
    'pkg = package_dir().resolve()',
    'if path == pkg:',
    'if p != pkg',
    'separate from this installer package',
]
for marker in required:
    if marker not in source:
        raise SystemExit(f"installer self-home hotfix marker missing: {marker}")

spec = importlib.util.spec_from_file_location("vex_installer_v11754", INSTALLER)
if spec is None or spec.loader is None:
    raise SystemExit("could not import generated installer")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory() as td:
    fake_home = Path(td) / "User"
    downloads = fake_home / "Downloads"
    package = downloads / "Vex-Agent-Runtime-v0.11.7.54-READY-TO-INSTALL"
    existing = downloads / "Vex-Existing-Install"
    package.mkdir(parents=True)
    existing.mkdir(parents=True)

    # Make the package score higher than the real install, reproducing the field
    # failure that selected the freshly extracted artifact as home.
    (package / "VexBridge.exe").write_bytes(b"pkg")
    (package / "VexBridgeRuntime").mkdir()
    (package / "VexRemoteSupportRuntime").mkdir()
    (package / "VexMemoryWorkerRuntime").mkdir()
    (package / "VexMemoryWorkerRuntime" / "VexMemoryWorker.exe").write_bytes(b"pkg")
    (package / "VexWindowsHost").mkdir()
    (existing / "VexBridge.exe").write_bytes(b"old")

    with mock.patch.object(module, "package_dir", return_value=package), mock.patch.object(module.Path, "home", return_value=fake_home):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VEX_HOME", None)
            chosen = module.find_home()
        if chosen.resolve() != existing.resolve():
            raise SystemExit(f"installer selected wrong home: {chosen}")

        with mock.patch.dict(os.environ, {"VEX_HOME": str(package)}, clear=False):
            try:
                module.find_home()
            except RuntimeError as exc:
                if "installer package" not in str(exc):
                    raise SystemExit(f"wrong VEX_HOME rejection: {exc}")
            else:
                raise SystemExit("installer accepted VEX_HOME pointing at its own package")

print("PASS v0.11.7.54 installer excludes its own extracted package")
