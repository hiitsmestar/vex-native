$ErrorActionPreference = 'Stop'

Write-Host 'Applying Bridge patch chain...'
python Tools/apply_v074_bridge_pairing_patch.py
python Tools/apply_v075_search_routing_patch.py
python Tools/apply_v076_direct_research_answers_patch.py
python Tools/apply_v077_grounded_research_patch.py
python Tools/apply_v078_photo_context_patch.py
python Tools/apply_v079_camera_visual_replies_patch.py
python Tools/apply_v079_compile_hotfix.py
python Tools/apply_v0710_visual_intent_fix.py
python Tools/apply_v0711_zoomable_chat_images.py
python Tools/prepare_v082_build_chain.py
python Tools/apply_v080_hybrid_brain_patch.py
python Tools/apply_v081_dual_pc_mesh_patch.py
python Tools/apply_v082_pc_tools_capability_patch.py
python Tools/apply_v083_browser_url_tools_patch.py
python Tools/apply_v084_self_learning_skills_patch.py
python Tools/apply_v084_skill_resolution_order_hotfix.py
python Tools/apply_v085_skill_compiler_patch.py
python Tools/apply_v086_bridge_media_patch.py
python Tools/apply_v090_bridge_neural_media_patch.py
python Tools/apply_v091_youtube_context_bridge_patch.py
python Tools/apply_v092_bridge_control_patch.py
python Tools/apply_v093_cognition_bridge_patch.py
python Tools/apply_v094_art_bridge_patch.py
python Tools/apply_v095_resource_housekeeper_art_patch.py
python Tools/apply_v096_active_maintenance_bridge_patch.py
python Tools/apply_v0961_bridge_stability_patch.py
python Tools/apply_v0962_self_healing_patch.py
python Tools/apply_v097_learning_engine_art_repair_patch.py
python Tools/apply_v0971_art_dll_hotfix.py
python Tools/apply_v0972_slow_cpu_coordination_hotfix.py
python Tools/apply_v0973_render_grounding_learning_hotfix.py
python Tools/apply_v098_modular_toolbox_time_patch.py

Write-Host 'Preparing Remote Support and standalone Art Worker...'
python Tools/fix_v099_remote_support_syntax.py
python Tools/apply_v0991_ntfy_patch.py
python Tools/apply_v0992_ntfy_header_fix.py
python Tools/apply_v100_art_remote_patch.py
python Tools/apply_v100_art_worker_hotfix.py
python Tools/apply_v102_art_safe_lowmem_patch.py

python -m py_compile Bridge/vex_bridge.py Bridge/vex_bridge_full.py Tools/VexArtWorker.py Tools/VexRemoteSupport.py Tools/VexDoctor.py Tools/VexArtMemoryFix.py Tools/apply_v102_art_safe_lowmem_patch.py
python -c "from pathlib import Path; w=Path('Tools/VexArtWorker.py').read_text(encoding='utf-8'); b=Path('Bridge/vex_bridge.py').read_text(encoding='utf-8'); m=Path('Tools/VexArtMemoryFix.py').read_text(encoding='utf-8'); assert 'VERSION = \"0.10.2\"' in w; assert 'cpu-lowmem' in w; assert 'BELOW_NORMAL_PRIORITY_CLASS' in w; assert 'ArtOwnershipConflict' in w; assert 'MODULAR_ART_EXTERNAL = True' in b; assert 'Bridge restart disabled' in b; assert 'PAGEFILE_MIN_MB = 32768' in m; assert 'PAGEFILE_MAX_MB = 65536' in m; print('v0.10.2 source checks OK')"

Write-Host 'Building VexBridge...'
pyinstaller --noconfirm --clean --onefile --console --name VexBridge --paths Bridge --collect-all cryptography --collect-all edge_tts --collect-all yt_dlp --hidden-import tkinter --hidden-import sqlite3 --hidden-import vex_bridge --hidden-import winrt.windows.media.control Bridge/vex_bridge_full.py
if (!(Test-Path dist/VexBridge.exe)) { throw 'VexBridge.exe missing' }

Write-Host 'Building VexArtWorker...'
pyinstaller --noconfirm --clean --onefile --windowed --name VexArtWorker --collect-all requests --collect-all PIL Tools/VexArtWorker.py
if (!(Test-Path dist/VexArtWorker.exe)) { throw 'VexArtWorker.exe missing' }

Write-Host 'Building VexRemoteSupport...'
pyinstaller --noconfirm --clean --onefile --windowed --name VexRemoteSupport --collect-all requests Tools/VexRemoteSupport.py
if (!(Test-Path dist/VexRemoteSupport.exe)) { throw 'VexRemoteSupport.exe missing' }

Write-Host 'Building VexDoctor...'
pyinstaller --noconfirm --clean --onefile --console --name VexDoctor --collect-all requests Tools/VexDoctor.py
if (!(Test-Path dist/VexDoctor.exe)) { throw 'VexDoctor.exe missing' }

Write-Host 'Building VexArtMemoryFix...'
pyinstaller --noconfirm --clean --onefile --windowed --name VexArtMemoryFix Tools/VexArtMemoryFix.py
if (!(Test-Path dist/VexArtMemoryFix.exe)) { throw 'VexArtMemoryFix.exe missing' }

Copy-Item Tools/VexBridgeWatchdog.ps1 dist/VexBridgeWatchdog.ps1
Copy-Item Tools/START-VEX-SELF-HEAL.cmd dist/START-VEX-SELF-HEAL.cmd
Copy-Item Tools/STOP-VEX-SELF-HEAL.cmd dist/STOP-VEX-SELF-HEAL.cmd

@'
Vex Art Safe Low-Memory v0.10.2
=================================

FIELD FIXES
- VexArtWorker is the sole owner of ComfyUI.
- Bridge/self-heal may observe art health but may not start/restart/repair ComfyUI.
- Bridge no longer evicts Ollama just because art is installed.
- CPU mode no longer forces the fp16 SDXL checkpoint to fp32.
- 8 GB CPU nodes use low-memory ComfyUI launch profiles first.
- Renderer runs BELOW_NORMAL priority with bounded math threads so Remote Support/UI stay responsive.
- CPU render test is 384x384 / 3 steps; normal CPU renders use conservative sizes / 5 steps.
- Art Worker rejects a ComfyUI process started by a different owner.

MEMORY HELPER
VexArtMemoryFix.exe explicitly configures INTERNAL C:\pagefile.sys to 32 GB minimum / 64 GB maximum.
It requires local UAC approval and a Windows restart. The external Seagate drive is not modified.

FIRST UPSTAIRS TEST
1. Keep only Remote Support active.
2. Run VexArtMemoryFix.exe and set the 32-64 GB internal pagefile.
3. Restart Windows.
4. Start only Remote Support and its 2-hour session.
5. Run VexArtWorker.exe -> Render Test. Do not start Bridge yet.
6. After that isolated render passes, test again with the new Bridge/self-heal running.
'@ | Set-Content -Encoding UTF8 dist/README-Vex-Art-Safe-v0.10.2.txt

Compress-Archive -Path dist/VexBridge.exe,dist/VexArtWorker.exe,dist/VexRemoteSupport.exe,dist/VexDoctor.exe,dist/VexArtMemoryFix.exe,dist/VexBridgeWatchdog.ps1,dist/START-VEX-SELF-HEAL.cmd,dist/STOP-VEX-SELF-HEAL.cmd,dist/README-Vex-Art-Safe-v0.10.2.txt -DestinationPath Vex-Art-Safe-v0.10.2.zip -Force
if (!(Test-Path Vex-Art-Safe-v0.10.2.zip)) { throw 'Vex-Art-Safe-v0.10.2.zip missing' }
Write-Host 'Vex v0.10.2 package complete.'
