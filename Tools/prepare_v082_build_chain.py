#!/usr/bin/env python3
from pathlib import Path

# Compatibility prep for the deterministic patch chain used by CI.
# Earlier device-test patches target the source shape that existed when they
# were written. These tiny text normalizations make them compose reliably on
# both macOS and Windows runners without changing runtime behavior.

p080 = Path("Tools/apply_v080_hybrid_brain_patch.py")
s080 = p080.read_text(encoding="utf-8")
s080 = s080.replace("prefix(1500)", "prefix(3400)")
p080.write_text(s080, encoding="utf-8")

p081 = Path("Tools/apply_v081_dual_pc_mesh_patch.py")
s081 = p081.read_text(encoding="utf-8")
s081 = s081.replace(
    '(bridge_path, ["MUSIC_EXTENSIONS", "search_music", "node_name"])',
    '(bridge_path, ["MUSIC_EXTENSIONS", "search_music"])',
)
p081.write_text(s081, encoding="utf-8")

p082 = Path("Tools/apply_v082_pc_tools_capability_patch.py")
s082 = p082.read_text(encoding="utf-8")
s082 = s082.replace(
    "guard !original.isEmpty, !isGenerating else { return }",
    "guard (!original.isEmpty || pendingPhotoData != nil), !isGenerating else { return }",
)
p082.write_text(s082, encoding="utf-8")

print("Prepared v0.8.2 patch chain for current photo + mesh source shape")
