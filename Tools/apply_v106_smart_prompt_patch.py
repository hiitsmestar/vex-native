#!/usr/bin/env python3
from pathlib import Path


def replace_function(text: str, name: str, replacement: str) -> str:
    start = text.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"missing function: {name}")
    end = text.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"could not find end of function: {name}")
    return text[:start] + replacement.rstrip() + text[end:]


path = Path("Tools/VexArtWorker.py")
text = path.read_text(encoding="utf-8")
if 'VERSION = "0.10.5"' not in text:
    raise SystemExit("VexArtWorker v0.10.5 marker missing")
text = text.replace('VERSION = "0.10.5"', 'VERSION = "0.10.6"', 1)

# Smart Prompt is deliberately deterministic and local. It does not call Bridge,
# Ollama, or an external API. Its job is to translate ordinary short requests into
# a stable SD1.5-oriented prompt scaffold so users do not have to learn magic words.
marker = 'REALISM_NEGATIVE = "illustration, anime, cartoon, painting, drawing, 3d render, cgi, large breasts, huge breasts, exaggerated breasts, cropped body, close-up, missing arms, missing hands, missing legs, missing feet, extra limbs, deformed hands, bad anatomy, blurry, low quality, text, watermark, logo"\n'
if marker not in text:
    raise SystemExit("realism negative marker missing")
text = text.replace(marker, marker + '''SMART_NEGATIVE = "wrong clothing colors, swapped clothing colors, unintended extra clothing, duplicate person, multiple people, cropped head, cropped feet, out of frame, visible light stands, visible backdrop stands, visible clamps, studio equipment"\n''', 1)

helper_marker = '\n\ndef _realism_checkpoint_path() -> Path:\n'
if helper_marker not in text:
    raise SystemExit("realism helper marker missing")
helpers = r'''
def _smart_prompt(user_prompt: str, orientation: str = "portrait") -> tuple[str, str]:
    """Compile ordinary language into a stable SD1.5 realism prompt.

    This is intentionally cheap/deterministic: no LLM is loaded, so the Art Worker
    can use it even while Bridge/cognition are asleep on low-memory machines.
    """
    import re

    raw = " ".join(str(user_prompt or "").split()).strip()
    if not raw:
        return raw, REALISM_NEGATIVE + ", " + SMART_NEGATIVE

    low = raw.lower()
    parts: list[str] = []

    # Image type and composition live at the front because CLIP tends to respect
    # early tokens more strongly on small SD1.5 prompts.
    if any(k in low for k in ("photo", "photoreal", "realistic")):
        parts.append("photorealistic fashion photograph")
    else:
        parts.append("photorealistic photograph")

    wants_full = any(k in low for k in ("full body", "full-body", "head to toe", "feet visible", "visible feet", "platform sandals", "shoes"))
    if wants_full:
        parts.append("single adult woman, full body, head to toe in frame, both arms visible, both hands visible, both legs visible, both feet visible, centered standing pose")
    else:
        parts.append("single adult woman")

    # Reinforce common attribute bindings the base model has repeatedly confused.
    bindings: list[str] = []
    patterns = [
        (r"(?:long\s+)?(?:straight\s+)?black hair(?:\s+with\s+(?:hot\s+)?pink streaks)?", "long straight black hair with clearly visible hot pink streaks" if "pink streak" in low else "black hair"),
        (r"(?:tiny\s+|micro\s+)?(?:bright\s+)?pink\s+(?:crop top|cropped top|top)", "tiny bright pink crop top"),
        (r"black\s+(?:side[- ]string\s+)?thong", "black side-string thong"),
        (r"black\s+platform\s+sandals", "black platform sandals"),
        (r"dark\s+(?:smudged\s+)?eyeliner", "dark smudged eyeliner"),
        (r"black\s+choker", "black choker"),
        (r"small\s+chest", "small chest"),
        (r"flat\s+stomach", "flat stomach"),
        (r"very\s+slim|very\s+skinny|skinny", "very slim body"),
        (r"pale\s+skin|very\s+pale", "pale skin"),
    ]
    remainder = raw
    for pattern, canonical in patterns:
        if re.search(pattern, low, flags=re.IGNORECASE):
            bindings.append(canonical)
            remainder = re.sub(pattern, " ", remainder, flags=re.IGNORECASE)

    if bindings:
        # Repeating exact color/garment pairings once is more reliable than a long
        # adjective list, without requiring the user to understand prompt weights.
        parts.append(", ".join(bindings))
        parts.append("clothing colors exactly as described")

    # Keep the user's remaining intent, but remove wording that has been causing
    # the checkpoint to literally draw photography equipment.
    remainder = re.sub(r"studio\s+(?:photo|photograph)", "fashion photo", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"(?:plain\s+)?(?:pink\s+)?studio\s+background", "solid plain pink seamless backdrop", remainder, flags=re.IGNORECASE)
    remainder = " ".join(remainder.replace(", ,", ",").split()).strip(" ,")
    if remainder:
        parts.append(remainder)

    if "background" not in low and "backdrop" not in low:
        parts.append("simple seamless neutral backdrop")
    elif "pink" in low and ("background" in low or "backdrop" in low):
        parts.append("solid plain pink seamless backdrop, no visible photography equipment")

    # Generic realism helpers belong at the end; users never need to type them.
    parts.append("natural human proportions, realistic skin texture, anatomically coherent hands and feet")
    compiled = ", ".join(p for p in parts if p)
    negative = REALISM_NEGATIVE + ", " + SMART_NEGATIVE
    return compiled, negative
'''
text = text.replace(helper_marker, '\n\n' + helpers.strip() + helper_marker, 1)

# Compile automatically inside render(), so GUI, command-line and the future Bridge
# adapter all receive the same natural-language behavior.
old_sig = 'def render(prompt: str, *, orientation: str = "portrait", seed: int | None = None, test: bool = False, timeout: int = 1200) -> dict:'
if old_sig not in text:
    raise SystemExit("render signature marker missing")
text = text.replace(old_sig, 'def render(prompt: str, *, orientation: str = "portrait", seed: int | None = None, test: bool = False, timeout: int = 1200, smart_prompt: bool = True) -> dict:', 1)

old_norm = '''    prompt = " ".join(str(prompt or "").split()).strip()\n    if not prompt:\n'''
new_norm = '''    prompt = " ".join(str(prompt or "").split()).strip()\n    if not prompt:\n'''
if old_norm not in text:
    raise SystemExit("prompt normalization marker missing")
text = text.replace(old_norm, new_norm, 1)

# v0.10.5 chooses its negative later; compile after model profile is known and use
# smart negative only for the realism path.
old_profile = '''    if model_profile == "sd15-realism":\n        steps = 6 if test else 12\n        cfg = 6.5\n        sampler_name = "dpmpp_2m"\n        scheduler = "karras"\n        negative = REALISM_NEGATIVE\n'''
new_profile = '''    if model_profile == "sd15-realism":\n        steps = 6 if test else 12\n        cfg = 6.5\n        sampler_name = "dpmpp_2m"\n        scheduler = "karras"\n        if smart_prompt and not test:\n            prompt, negative = _smart_prompt(prompt, orientation)\n        else:\n            negative = REALISM_NEGATIVE\n'''
if old_profile not in text:
    raise SystemExit("realism render profile marker missing")
text = text.replace(old_profile, new_profile, 1)

# Report the prompt mode locally without publishing prompt contents through the
# sanitized remote-support surface.
result_marker = '"elapsed_seconds": round(time.time() - started, 1)}\n        _write_report(result)\n        return result\n'
# Too broad to replace safely; add mode to the final success result only.
success_old = 'result = {"ok": True, "status": "done", "width": width, "height": height, "seed": seed, "mode": mode, "checkpoint": checkpoint, "image_path": str(target), "image_bytes": len(data), "elapsed_seconds": round(time.time() - started, 1)}'
if success_old not in text:
    raise SystemExit("success result marker missing")
success_new = 'result = {"ok": True, "status": "done", "width": width, "height": height, "seed": seed, "mode": mode, "checkpoint": checkpoint, "prompt_mode": "smart" if (smart_prompt and model_profile == "sd15-realism" and not test) else "raw", "image_path": str(target), "image_bytes": len(data), "elapsed_seconds": round(time.time() - started, 1)}'
text = text.replace(success_old, success_new, 1)

# GUI: Smart Prompt defaults ON. Advanced users can turn it off, and Preview lets
# the user see exactly what the compiler will send instead of hiding magic behavior.
controls_marker = '    seed_var = tk.StringVar(value="")\n'
if controls_marker not in text:
    raise SystemExit("seed GUI marker missing")
text = text.replace(controls_marker, controls_marker + '    smart_var = tk.BooleanVar(value=True)\n', 1)

seed_pack = '    tk.Entry(controls, textvariable=seed_var, width=14).pack(side="left", padx=(5, 10))\n'
if seed_pack not in text:
    raise SystemExit("seed entry marker missing")
text = text.replace(seed_pack, seed_pack + '    tk.Checkbutton(controls, text="Smart Prompt", variable=smart_var).pack(side="left", padx=(8, 4))\n', 1)

old_generate = '        run_async(lambda: render(prompt, orientation=orientation.get(), seed=seed), "Rendering...")\n'
if old_generate not in text:
    raise SystemExit("GUI generate marker missing")
text = text.replace(old_generate, '        run_async(lambda: render(prompt, orientation=orientation.get(), seed=seed, smart_prompt=smart_var.get()), "Rendering...")\n', 1)

# Put a preview button in prompt_tools after the v0.10.4 clipboard controls exist.
clear_button = '    tk.Button(prompt_tools, text="Clear", command=_prompt_clear, width=10).pack(side="left", padx=4)\n'
if clear_button not in text:
    raise SystemExit("clipboard Clear button marker missing")
preview_code = r'''    def _preview_smart_prompt():
        raw = prompt_box.get("1.0", "end").strip()
        if not raw:
            messagebox.showinfo("Vex Art Worker", "Type a short request first.")
            return
        compiled, _ = _smart_prompt(raw, orientation.get()) if smart_var.get() else (raw, "")
        preview = tk.Toplevel(root)
        preview.title("Smart Prompt Preview")
        preview.geometry("760x420")
        tk.Label(preview, text="This is what Art Worker will send to the realism model:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        box = ScrolledText(preview, height=14, wrap="word", font=("Segoe UI", 10))
        box.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        box.insert("1.0", compiled)
        box.configure(state="disabled")
        tk.Button(preview, text="Close", command=preview.destroy, width=12).pack(pady=(0, 12))

'''
text = text.replace(clear_button, clear_button + preview_code + '    tk.Button(prompt_tools, text="Preview Smart Prompt", command=_preview_smart_prompt, width=18).pack(side="left", padx=8)\n', 1)

# CLI defaults to smart as well; --raw-prompt is the escape hatch.
arg_marker = '    parser.add_argument("--seed", type=int, default=None)\n'
if arg_marker not in text:
    raise SystemExit("CLI seed marker missing")
text = text.replace(arg_marker, arg_marker + '    parser.add_argument("--raw-prompt", action="store_true", help="Disable Smart Prompt compilation")\n', 1)

cli_render = '        result = render(args.prompt, orientation=args.orientation, seed=args.seed)\n'
if cli_render not in text:
    raise SystemExit("CLI render marker missing")
text = text.replace(cli_render, '        result = render(args.prompt, orientation=args.orientation, seed=args.seed, smart_prompt=not args.raw_prompt)\n', 1)

checks = [
    'VERSION = "0.10.6"',
    'def _smart_prompt',
    'Smart Prompt',
    'Preview Smart Prompt',
    'wrong clothing colors',
    'prompt_mode',
    '--raw-prompt',
]
for check in checks:
    if check not in text:
        raise SystemExit(f"smart prompt patch missing marker: {check}")

path.write_text(text, encoding="utf-8")
print("Applied VexArtWorker v0.10.6 Smart Prompt patch")
