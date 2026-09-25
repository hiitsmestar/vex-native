#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
server = (root / "Tools" / "VexMCPServer.py").read_text(encoding="utf-8")
installer = (root / "Tools" / "Install-VexMCP.ps1").read_text(encoding="utf-8")

required = [
    'VERSION = "0.15.4"',
    'FastMCP(',
    'stateless_http=True',
    'def vex_status(',
    'def continuity_snapshot(',
    'def phone_command(',
    'def phone_command_result(',
    'def refresh_vex_recall(',
    'def render_vex(',
    'server.run(transport=transport)',
]
for marker in required:
    assert marker in server, f"missing server marker: {marker}"

for forbidden in [
    'shell=True',
    'os.system(',
    'subprocess.Popen(',
]:
    assert forbidden not in server, f"unsafe generic execution marker found: {forbidden}"

for marker in [
    'mcp==1.26.0',
    'VexNativeMCP',
    '127.0.0.1',
    'VexMCPServer.py',
]:
    assert marker in installer, f"missing installer marker: {marker}"

compile(server, str(root / "Tools" / "VexMCPServer.py"), "exec")
print("v0.15.4 VexNative MCP source checks passed")
