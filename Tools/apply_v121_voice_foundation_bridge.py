#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
PROOF = Path("Tools/ci_v120_postbuild_wants_proof.py")

bridge = BRIDGE.read_text(encoding="utf-8")
proof = PROOF.read_text(encoding="utf-8")

MARKER = 'V121_VOICE_FOUNDATION = "v0.12.1-swap-ready-voice-v1"'

if 'parsed.path == "/tts/speak"' not in bridge or "NEURAL_TTS_VOICES" not in bridge:
    raise SystemExit("v0.12.1 voice foundation requires the proven v0.9 neural TTS Bridge layer")
if 'V120_PC_HEALTH_AUTONOMY' not in bridge:
    raise SystemExit("v0.12.1 voice foundation requires the generated v0.12 Bridge")

if "import importlib.util\n" not in bridge:
    import_anchor = "import hashlib\n"
    if import_anchor not in bridge:
        raise SystemExit("Bridge import anchor missing")
    bridge = bridge.replace(import_anchor, import_anchor + "import importlib.util\n", 1)

if MARKER not in bridge:
    state_anchor = "class BridgeState:\n"
    if state_anchor not in bridge:
        raise SystemExit("BridgeState anchor missing")
    layer = r'''
# ---------------------------------------------------------------------------
# v0.12.1 swap-ready voice transport
# ---------------------------------------------------------------------------
V121_VOICE_FOUNDATION = "v0.12.1-swap-ready-voice-v1"
V121_VOICE_CONTRACT_VERSION = 1
V121_VOICE_DEFAULT_PROVIDER = "auto"
V121_VOICE_EDGE_PROVIDER = "edge-neural"
V121_VOICE_FUTURE_LOCAL_PROVIDER = "local-neural"


def _v121_voice_module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _v121_voice_status() -> dict:
    edge_ready = _v121_voice_module_available("edge_tts")
    return {
        "ok": True,
        "version": V121_VOICE_FOUNDATION,
        "contract_version": V121_VOICE_CONTRACT_VERSION,
        "transport": "bridge-json-base64-audio-v1",
        "default_provider": V121_VOICE_DEFAULT_PROVIDER,
        "supports_provider_selection": True,
        "supports_streaming": False,
        "text_limit": 1800,
        "audio_mime": "audio/mpeg",
        "providers": [
            {
                "id": V121_VOICE_EDGE_PROVIDER,
                "available": edge_ready,
                "local": False,
                "network_required": True,
                "description": "Current lightweight neural voice provider; text is synthesized by the Edge TTS service.",
            },
            {
                "id": V121_VOICE_FUTURE_LOCAL_PROVIDER,
                "available": False,
                "local": True,
                "network_required": False,
                "description": "Reserved provider contract for the dedicated AI PC custom Vex voice model.",
            },
        ],
    }


def _v121_resolve_voice_provider(requested: str) -> str:
    provider = str(requested or V121_VOICE_DEFAULT_PROVIDER).strip().lower()
    if provider == V121_VOICE_DEFAULT_PROVIDER:
        # The current low-end PC intentionally does not carry a heavyweight local
        # voice model. The same contract can switch this resolution to local-neural
        # once the dedicated AI machine has a verified local provider installed.
        return V121_VOICE_EDGE_PROVIDER
    if provider == V121_VOICE_EDGE_PROVIDER:
        return provider
    raise ValueError(f"unsupported voice provider: {provider}")


'''
    bridge = bridge.replace(state_anchor, layer + state_anchor, 1)

# Authenticated capability discovery. Prefer the v0.12 hardware route as the
# insertion anchor because this patch runs after the cumulative v0.12 assembler.
voice_get = '''        if parsed.path == "/voice/status":\n            self._json(200, _v121_voice_status())\n            return\n\n'''
if 'parsed.path == "/voice/status"' not in bridge:
    get_anchor = '        if parsed.path == "/hardware/status":\n'
    if get_anchor not in bridge:
        get_anchor = '        if parsed.path in ("/", "/status"):\n'
    if get_anchor not in bridge:
        raise SystemExit("Bridge GET voice status insertion anchor missing")
    bridge = bridge.replace(get_anchor, voice_get + get_anchor, 1)

# Extend the already-proven /tts/speak endpoint instead of replacing it. This
# keeps every existing phone client working while new clients can explicitly ask
# for provider=auto and later gain a fully local custom voice without a new API.
provider_anchor = '''                speech_text = str(payload.get("text") or "").strip()\n                voice = str(payload.get("voice") or "en-US-AvaMultilingualNeural").strip()\n'''
provider_new = '''                speech_text = str(payload.get("text") or "").strip()\n                requested_provider = str(payload.get("provider") or V121_VOICE_DEFAULT_PROVIDER).strip().lower()\n                resolved_provider = _v121_resolve_voice_provider(requested_provider)\n                voice = str(payload.get("voice") or "en-US-AvaMultilingualNeural").strip()\n'''
if "requested_provider = str(payload.get(\"provider\")" not in bridge:
    if provider_anchor not in bridge:
        raise SystemExit("TTS provider request anchor missing")
    bridge = bridge.replace(provider_anchor, provider_new, 1)

response_anchor = '''                    "mime": "audio/mpeg",\n                    "voice": voice,\n                    "audio_base64": base64.b64encode(audio).decode("ascii"),\n'''
response_new = '''                    "mime": "audio/mpeg",\n                    "provider": resolved_provider,\n                    "voice": voice,\n                    "audio_base64": base64.b64encode(audio).decode("ascii"),\n'''
if '"provider": resolved_provider' not in bridge:
    if response_anchor not in bridge:
        raise SystemExit("TTS provider response anchor missing")
    bridge = bridge.replace(response_anchor, response_new, 1)

BRIDGE.write_text(bridge, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")

# Teach the existing final-artifact proof to apply this layer last, freeze the
# dynamic edge_tts dependency, and prove the capability endpoint from the actual
# rewritten ZIP. The second freeze-only pass preserves this already-mutated source.
if 'run(sys.executable, "Tools/apply_v121_voice_foundation_bridge.py")' not in proof:
    patch_anchor = '        run(sys.executable, "Tools/apply_v120_pc_health_autonomy.py")\n'
    if patch_anchor not in proof:
        raise SystemExit("post-build patch-order anchor missing")
    proof = proof.replace(
        patch_anchor,
        patch_anchor + '        run(sys.executable, "Tools/apply_v121_voice_foundation_bridge.py")\n',
        1,
    )

if 'V121_VOICE_FOUNDATION' not in proof:
    marker_anchor = '        \'parsed.path == "/maintenance/run"\',\n'
    if marker_anchor not in proof:
        raise SystemExit("post-build Bridge marker anchor missing")
    proof = proof.replace(
        marker_anchor,
        marker_anchor
        + '        \'V121_VOICE_FOUNDATION = "v0.12.1-swap-ready-voice-v1"\',\n'
        + '        \'parsed.path == "/voice/status"\',\n'
        + '        \'requested_provider = str(payload.get("provider")\',\n',
        1,
    )

edge_collect = '        "--collect-all", "bs4", "--collect-all", "pypdf", "--collect-all", "cryptography",\n'
if '"--collect-all", "edge_tts"' not in proof:
    if edge_collect not in proof:
        raise SystemExit("post-build PyInstaller dependency anchor missing")
    proof = proof.replace(
        edge_collect,
        '        "--collect-all", "bs4", "--collect-all", "pypdf", "--collect-all", "cryptography",\n'
        '        "--collect-all", "edge_tts",\n',
        1,
    )

voice_proof_anchor = '''                audit = no_proxy_json(f"http://127.0.0.1:{port}/housekeeping/audit?{query}", timeout=12)\n                if audit.get("ok") is not True:\n                    raise RuntimeError(f"housekeeping audit failed: {audit}")\n\n                log("PASS final ZIP Bridge v0.12 + Wants reconciliation + PC health endpoints")\n'''
voice_proof_new = '''                audit = no_proxy_json(f"http://127.0.0.1:{port}/housekeeping/audit?{query}", timeout=12)\n                if audit.get("ok") is not True:\n                    raise RuntimeError(f"housekeeping audit failed: {audit}")\n                voice = no_proxy_json(f"http://127.0.0.1:{port}/voice/status?{query}", timeout=8)\n                if voice.get("ok") is not True or voice.get("contract_version") != 1:\n                    raise RuntimeError(f"voice status failed: {voice}")\n                providers = voice.get("providers") if isinstance(voice.get("providers"), list) else []\n                edge = next((p for p in providers if isinstance(p, dict) and p.get("id") == "edge-neural"), None)\n                if not edge or edge.get("available") is not True or edge.get("local") is not False:\n                    raise RuntimeError(f"frozen Edge voice provider unavailable or misclassified: {voice}")\n\n                log("PASS final ZIP Bridge v0.12 + Wants + PC health + swap-ready voice contract")\n'''
if '/voice/status?' not in proof:
    if voice_proof_anchor not in proof:
        raise SystemExit("post-build live voice proof anchor missing")
    proof = proof.replace(voice_proof_anchor, voice_proof_new, 1)

PROOF.write_text(proof, encoding="utf-8")
compile(proof, str(PROOF), "exec")

for marker in [
    MARKER,
    'parsed.path == "/voice/status"',
    'requested_provider = str(payload.get("provider")',
    '"provider": resolved_provider',
    'V121_VOICE_FUTURE_LOCAL_PROVIDER = "local-neural"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.12.1 voice Bridge invariant missing: {marker}")
for marker in [
    'Tools/apply_v121_voice_foundation_bridge.py',
    '"--collect-all", "edge_tts"',
    '/voice/status?',
    'swap-ready voice contract',
]:
    if marker not in proof:
        raise SystemExit(f"v0.12.1 voice proof invariant missing: {marker}")

print("Applied v0.12.1 swap-ready Bridge voice provider contract and frozen dependency proof")
