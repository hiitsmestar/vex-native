#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Tools"
APP = ROOT / "VexNative"
PBX = ROOT / "VexNative.xcodeproj" / "project.pbxproj"
CONTENT = APP / "ContentView.swift"

C_TEMPLATE = TOOLS / "VexContainerChildProbe.c"
SWIFT_TEMPLATE = TOOLS / "VexContainerChildDiagnostics.swift"
C_DEST = APP / "VexContainerChildProbe.c"
SWIFT_DEST = APP / "VexContainerChildDiagnostics.swift"

for source in [C_TEMPLATE, SWIFT_TEMPLATE]:
    if not source.exists():
        raise SystemExit(f"v0.13.6 template missing: {source}")

shutil.copyfile(C_TEMPLATE, C_DEST)
shutil.copyfile(SWIFT_TEMPLATE, SWIFT_DEST)

pbx = PBX.read_text(encoding="utf-8")

if "VexContainerChildProbe.c in Sources" not in pbx:
    build_anchor = 'A000000000000000000004D /* VexBadQueryDiagnostics.swift in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002D /* VexBadQueryDiagnostics.swift */; };'
    build_repl = build_anchor + '\n' + \
        '\t\tA000000000000000000004E /* VexContainerChildProbe.c in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002E /* VexContainerChildProbe.c */; };' + '\n' + \
        '\t\tA000000000000000000004F /* VexContainerChildDiagnostics.swift in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002F /* VexContainerChildDiagnostics.swift */; };'
    if build_anchor not in pbx:
        raise SystemExit("v0.13.6 build-file anchor missing")
    pbx = pbx.replace(build_anchor, build_repl, 1)

    file_anchor = 'A000000000000000000002D /* VexBadQueryDiagnostics.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = VexBadQueryDiagnostics.swift; sourceTree = "<group>"; };'
    file_repl = file_anchor + '\n' + \
        '\t\tA000000000000000000002E /* VexContainerChildProbe.c */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.c.c; path = VexContainerChildProbe.c; sourceTree = "<group>"; };' + '\n' + \
        '\t\tA000000000000000000002F /* VexContainerChildDiagnostics.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = VexContainerChildDiagnostics.swift; sourceTree = "<group>"; };'
    if file_anchor not in pbx:
        raise SystemExit("v0.13.6 file-reference anchor missing")
    pbx = pbx.replace(file_anchor, file_repl, 1)

    group_anchor = '\t\t\t\tA000000000000000000002D /* VexBadQueryDiagnostics.swift */,'
    group_repl = group_anchor + '\n' + \
        '\t\t\t\tA000000000000000000002E /* VexContainerChildProbe.c */,' + '\n' + \
        '\t\t\t\tA000000000000000000002F /* VexContainerChildDiagnostics.swift */,'
    if group_anchor not in pbx:
        raise SystemExit("v0.13.6 group anchor missing")
    pbx = pbx.replace(group_anchor, group_repl, 1)

    sources_anchor = '\t\t\t\tA000000000000000000004D /* VexBadQueryDiagnostics.swift in Sources */,'
    sources_repl = sources_anchor + '\n' + \
        '\t\t\t\tA000000000000000000004E /* VexContainerChildProbe.c in Sources */,' + '\n' + \
        '\t\t\t\tA000000000000000000004F /* VexContainerChildDiagnostics.swift in Sources */,'
    if sources_anchor not in pbx:
        raise SystemExit("v0.13.6 sources anchor missing")
    pbx = pbx.replace(sources_anchor, sources_repl, 1)

PBX.write_text(pbx, encoding="utf-8")

content = CONTENT.read_text(encoding="utf-8")
if "VexContainerChildProbeView()" not in content:
    anchor = "                    VexBadQueryProbeView()"
    if anchor not in content:
        raise SystemExit("v0.13.6 UI anchor missing")
    content = content.replace(anchor, anchor + "\n\n                    VexContainerChildProbeView()", 1)
CONTENT.write_text(content, encoding="utf-8")

combined = (
    PBX.read_text(encoding="utf-8") + "\n" +
    CONTENT.read_text(encoding="utf-8") + "\n" +
    C_DEST.read_text(encoding="utf-8") + "\n" +
    SWIFT_DEST.read_text(encoding="utf-8")
)

for marker in [
    "VexContainerChildProbe.c in Sources",
    "VexContainerChildDiagnostics.swift in Sources",
    "VexContainerChildProbeView()",
    'buildMarker = "v0.13.6-read-only-child-container-probe-v1"',
    "vex_bad_query_list_children",
    "vex_bad_query_free_string",
]:
    if marker not in combined:
        raise SystemExit(f"v0.13.6 marker missing: {marker}")

for forbidden in [
    "O_WRONLY", "O_RDWR", "unlink(", "rename(", "removeItem(",
    "createFile(", "replaceItem(", ".write(to:"
]:
    if forbidden in C_DEST.read_text(encoding="utf-8") or forbidden in SWIFT_DEST.read_text(encoding="utf-8"):
        raise SystemExit(f"v0.13.6 mutation primitive forbidden: {forbidden}")

print("PASS v0.13.6 child-container read-only probe patch")
