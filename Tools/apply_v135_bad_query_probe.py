#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Tools"
APP = ROOT / "VexNative"
PBX = ROOT / "VexNative.xcodeproj" / "project.pbxproj"
CONTENT = APP / "ContentView.swift"

C_TEMPLATE = TOOLS / "VexBadQueryProbe.c"
SWIFT_TEMPLATE = TOOLS / "VexBadQueryDiagnostics.swift"
C_DEST = APP / "VexBadQueryProbe.c"
SWIFT_DEST = APP / "VexBadQueryDiagnostics.swift"

for source in [C_TEMPLATE, SWIFT_TEMPLATE]:
    if not source.exists():
        raise SystemExit(f"v0.13.5 template missing: {source}")

shutil.copyfile(C_TEMPLATE, C_DEST)
shutil.copyfile(SWIFT_TEMPLATE, SWIFT_DEST)

pbx = PBX.read_text(encoding="utf-8")

if "VexBadQueryProbe.c in Sources" not in pbx:
    anchor = 'A000000000000000000004B /* VexVoiceIntents.swift in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002B /* VexVoiceIntents.swift */; };'
    replacement = anchor + '\n' + \
        '\t\tA000000000000000000004C /* VexBadQueryProbe.c in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002C /* VexBadQueryProbe.c */; };' + '\n' + \
        '\t\tA000000000000000000004D /* VexBadQueryDiagnostics.swift in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002D /* VexBadQueryDiagnostics.swift */; };'
    if anchor not in pbx:
        raise SystemExit("v0.13.5 build-file anchor missing")
    pbx = pbx.replace(anchor, replacement, 1)

    anchor = 'A000000000000000000002B /* VexVoiceIntents.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = VexVoiceIntents.swift; sourceTree = "<group>"; };'
    replacement = anchor + '\n' + \
        '\t\tA000000000000000000002C /* VexBadQueryProbe.c */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.c.c; path = VexBadQueryProbe.c; sourceTree = "<group>"; };' + '\n' + \
        '\t\tA000000000000000000002D /* VexBadQueryDiagnostics.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = VexBadQueryDiagnostics.swift; sourceTree = "<group>"; };'
    if anchor not in pbx:
        raise SystemExit("v0.13.5 file-reference anchor missing")
    pbx = pbx.replace(anchor, replacement, 1)

    anchor = '\t\t\t\tA000000000000000000002B /* VexVoiceIntents.swift */,'
    replacement = anchor + '\n' + \
        '\t\t\t\tA000000000000000000002C /* VexBadQueryProbe.c */,' + '\n' + \
        '\t\t\t\tA000000000000000000002D /* VexBadQueryDiagnostics.swift */,'
    if anchor not in pbx:
        raise SystemExit("v0.13.5 VexNative group anchor missing")
    pbx = pbx.replace(anchor, replacement, 1)

    anchor = '\t\t\t\tA000000000000000000004B /* VexVoiceIntents.swift in Sources */,'
    replacement = anchor + '\n' + \
        '\t\t\t\tA000000000000000000004C /* VexBadQueryProbe.c in Sources */,' + '\n' + \
        '\t\t\t\tA000000000000000000004D /* VexBadQueryDiagnostics.swift in Sources */,'
    if anchor not in pbx:
        raise SystemExit("v0.13.5 sources-phase anchor missing")
    pbx = pbx.replace(anchor, replacement, 1)

PBX.write_text(pbx, encoding="utf-8")

content = CONTENT.read_text(encoding="utf-8")
if "VexBadQueryProbeView()" not in content:
    anchor = '                    if !system.error.isEmpty {'
    if anchor not in content:
        raise SystemExit("v0.13.5 System-view anchor missing")
    content = content.replace(
        anchor,
        '                    VexBadQueryProbeView()\\n\\n' + anchor,
        1,
    )
CONTENT.write_text(content, encoding="utf-8")

pbx_final = PBX.read_text(encoding="utf-8")
content_final = CONTENT.read_text(encoding="utf-8")
swift_final = SWIFT_DEST.read_text(encoding="utf-8")
c_final = C_DEST.read_text(encoding="utf-8")

for marker in [
    "VexBadQueryProbe.c in Sources",
    "VexBadQueryDiagnostics.swift in Sources",
]:
    if marker not in pbx_final:
        raise SystemExit(f"v0.13.5 Xcode marker missing: {marker}")

for marker in [
    'buildMarker = "v0.13.5-read-only-bad-query-probe-v1"',
    "VexBadQueryProbeView()",
    "vex_bad_query_grant_read",
    "vex_bad_query_release",
]:
    haystack = swift_final + "\n" + content_final + "\n" + c_final
    if marker not in haystack:
        raise SystemExit(f"v0.13.5 marker missing: {marker}")

for forbidden in [
    "O_WRONLY",
    "O_RDWR",
    "unlink(",
    "rename(",
    "removeItem(",
    "createFile(",
    "replaceItem(",
    ".write(to:",
]:
    if forbidden in c_final or forbidden in swift_final:
        raise SystemExit(f"v0.13.5 mutation primitive forbidden: {forbidden}")

print("PASS v0.13.5 read-only bad_query probe patch")
