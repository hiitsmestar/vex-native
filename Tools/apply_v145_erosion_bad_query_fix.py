#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Tools"
APP = ROOT / "VexNative"
PBX = ROOT / "VexNative.xcodeproj" / "project.pbxproj"
CONTENT = APP / "ContentView.swift"
APPFILE = APP / "VexNativeApp.swift"

C_TEMPLATE = TOOLS / "VexErosionBadQuery.c"
SWIFT_TEMPLATE = TOOLS / "VexErosionBadQueryDiagnostics.swift"
C_DEST = APP / "VexErosionBadQuery.c"
SWIFT_DEST = APP / "VexErosionBadQueryDiagnostics.swift"

for source in [C_TEMPLATE, SWIFT_TEMPLATE]:
    if not source.exists():
        raise SystemExit(f"v0.14.5 template missing: {source}")

shutil.copyfile(C_TEMPLATE, C_DEST)
shutil.copyfile(SWIFT_TEMPLATE, SWIFT_DEST)

pbx = PBX.read_text(encoding="utf-8")
if "VexErosionBadQuery.c in Sources" not in pbx:
    build_anchor = 'A000000000000000000004B /* VexVoiceIntents.swift in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002B /* VexVoiceIntents.swift */; };'
    if build_anchor not in pbx:
        raise SystemExit("v0.14.5 build-file anchor missing")
    pbx = pbx.replace(
        build_anchor,
        build_anchor + '\n'
        '\t\tA000000000000000000004E /* VexErosionBadQuery.c in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002E /* VexErosionBadQuery.c */; };\n'
        '\t\tA000000000000000000004F /* VexErosionBadQueryDiagnostics.swift in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002F /* VexErosionBadQueryDiagnostics.swift */; };',
        1,
    )

    file_anchor = 'A000000000000000000002B /* VexVoiceIntents.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = VexVoiceIntents.swift; sourceTree = "<group>"; };'
    if file_anchor not in pbx:
        raise SystemExit("v0.14.5 file-reference anchor missing")
    pbx = pbx.replace(
        file_anchor,
        file_anchor + '\n'
        '\t\tA000000000000000000002E /* VexErosionBadQuery.c */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.c.c; path = VexErosionBadQuery.c; sourceTree = "<group>"; };\n'
        '\t\tA000000000000000000002F /* VexErosionBadQueryDiagnostics.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = VexErosionBadQueryDiagnostics.swift; sourceTree = "<group>"; };',
        1,
    )

    group_anchor = '\t\t\t\tA000000000000000000002B /* VexVoiceIntents.swift */,'
    if group_anchor not in pbx:
        raise SystemExit("v0.14.5 group anchor missing")
    pbx = pbx.replace(
        group_anchor,
        group_anchor + '\n'
        '\t\t\t\tA000000000000000000002E /* VexErosionBadQuery.c */,\n'
        '\t\t\t\tA000000000000000000002F /* VexErosionBadQueryDiagnostics.swift */,',
        1,
    )

    sources_anchor = '\t\t\t\tA000000000000000000004B /* VexVoiceIntents.swift in Sources */,'
    if sources_anchor not in pbx:
        raise SystemExit("v0.14.5 sources anchor missing")
    pbx = pbx.replace(
        sources_anchor,
        sources_anchor + '\n'
        '\t\t\t\tA000000000000000000004E /* VexErosionBadQuery.c in Sources */,\n'
        '\t\t\t\tA000000000000000000004F /* VexErosionBadQueryDiagnostics.swift in Sources */,',
        1,
    )

PBX.write_text(pbx, encoding="utf-8")

content = CONTENT.read_text(encoding="utf-8")
if "VexErosionBadQueryProbeView()" not in content:
    anchor = '                    if !system.error.isEmpty {'
    if anchor not in content:
        raise SystemExit("v0.14.5 System-view anchor missing")
    content = content.replace(anchor, '                    VexErosionBadQueryProbeView()\n\n' + anchor, 1)
CONTENT.write_text(content, encoding="utf-8")

app = APPFILE.read_text(encoding="utf-8")
if "VEX_EROSION_BAD_QUERY_AUTORUN" not in app:
    anchor = '                .preferredColorScheme(.dark)'
    if anchor not in app:
        raise SystemExit("v0.14.5 autorun anchor missing")
    app = app.replace(
        anchor,
        anchor + '\n'
        '                .task {\n'
        '                    print("VEX_EROSION_BAD_QUERY_AUTORUN|start")\n'
        '                    await MainActor.run {\n'
        '                        VexErosionBadQueryDiagnostics().run()\n'
        '                    }\n'
        '                }',
        1,
    )
APPFILE.write_text(app, encoding="utf-8")

for marker in [
    "VexErosionBadQuery.c in Sources",
    "VexErosionBadQueryDiagnostics.swift in Sources",
]:
    if marker not in PBX.read_text(encoding="utf-8"):
        raise SystemExit(f"missing Xcode marker: {marker}")

haystack = C_DEST.read_text(encoding="utf-8") + "\n" + SWIFT_DEST.read_text(encoding="utf-8")
for marker in [
    "vex_bad_query_list",
    "vex_bad_query_grant_read",
    'buildMarker = "v0.14.5-erosion-bad-query-readonly-v1"',
    "VEX_EROSION_BAD_QUERY",
]:
    if marker not in haystack:
        raise SystemExit(f"missing v0.14.5 marker: {marker}")

for forbidden in ["O_WRONLY", "O_RDWR", "unlink(", "rename(", "removeItem(", "createFile("]:
    if forbidden in haystack:
        raise SystemExit(f"mutation primitive forbidden in read-only port: {forbidden}")

print("PASS v0.14.5 Erosion-compatible bad_query patch")
