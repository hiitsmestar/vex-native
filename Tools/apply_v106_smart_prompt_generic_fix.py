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
if 'VERSION = "0.10.6"' not in text or 'def _smart_prompt' not in text:
    raise SystemExit("v0.10.6 Smart Prompt patch must run first")

text = replace_function(text, "_smart_prompt", r'''def _smart_prompt(user_prompt: str, orientation: str = "portrait") -> tuple[str, str]:
    """Compile ordinary language into a stable SD1.5 realism prompt.

    Deterministic/local by design: no Bridge, Ollama or cloud API is loaded.
    Human-specific scaffolding is only applied to human/fashion requests.
    """
    import re

    raw = " ".join(str(user_prompt or "").split()).strip()
    negative = REALISM_NEGATIVE + ", " + SMART_NEGATIVE
    if not raw:
        return raw, negative

    low = raw.lower()
    photo_prefix = "photorealistic fashion photograph" if any(k in low for k in ("fashion", "woman", "girl", "model", "outfit", "thong", "crop top")) else "photorealistic photograph"

    human_terms = (
        "woman", "girl", "female", "man", "male", "person", "model", "body", "face",
        "hair", "eyeliner", "chest", "stomach", "thong", "crop top", "dress", "skirt",
        "pants", "shorts", "sandals", "shoes", "boots", "choker",
    )
    is_human = any(term in low for term in human_terms)

    # Generic object/scene requests should remain generic. Smart Prompt only adds a
    # realism bias and removes literal studio-equipment wording.
    if not is_human:
        remainder = re.sub(r"studio\s+(?:photo|photograph)", "photograph", raw, flags=re.IGNORECASE)
        remainder = re.sub(r"(?:plain\s+)?(?:[a-z]+\s+)?studio\s+background", "simple seamless backdrop", remainder, flags=re.IGNORECASE)
        return f"{photo_prefix}, {remainder}, realistic materials, natural lighting", negative

    parts: list[str] = [photo_prefix]
    wants_full = any(k in low for k in ("full body", "full-body", "head to toe", "feet visible", "visible feet", "platform sandals", "shoes", "boots"))

    if "woman" in low or "girl" in low or "female" in low:
        subject = "single adult woman"
    elif "man" in low or "male" in low:
        subject = "single adult man"
    else:
        subject = "single adult person"

    if wants_full:
        parts.append(subject + ", full body, head to toe in frame, both arms visible, both hands visible, both legs visible, both feet visible, centered standing pose")
    else:
        parts.append(subject)

    # Reinforce attribute bindings that the small checkpoint commonly swaps or drops.
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
        (r"pale\s+skin|very\s+pale|pale\s+(?=woman|girl|female|person)", "pale skin"),
    ]

    remainder = raw
    for pattern, canonical in patterns:
        if re.search(pattern, remainder, flags=re.IGNORECASE):
            bindings.append(canonical)
            remainder = re.sub(pattern, " ", remainder, flags=re.IGNORECASE)

    if bindings:
        parts.append(", ".join(bindings))
        parts.append("clothing colors exactly as described, do not swap garment colors")

    remainder = re.sub(r"studio\s+(?:photo|photograph)", "fashion photograph", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"(?:plain\s+)?pink\s+studio\s+background", "solid plain pink seamless backdrop", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"\s+,", ",", remainder)
    remainder = " ".join(remainder.replace(", ,", ",").split()).strip(" ,")
    if remainder:
        parts.append(remainder)

    if "background" not in low and "backdrop" not in low:
        parts.append("simple seamless neutral backdrop")
    elif "pink" in low and ("background" in low or "backdrop" in low):
        parts.append("solid plain pink seamless backdrop, no visible photography equipment")

    parts.append("natural human proportions, realistic skin texture, anatomically coherent hands and feet")
    return ", ".join(p for p in parts if p), negative
''')

path.write_text(text, encoding="utf-8")
print("Applied v0.10.6 generic Smart Prompt fix")
