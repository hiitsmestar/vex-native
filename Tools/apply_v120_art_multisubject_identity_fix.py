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
if "def _smart_prompt(" not in text:
    raise SystemExit("Smart Prompt function missing")

replacement = r'''
def _smart_prompt(user_prompt: str, orientation: str = "portrait") -> tuple[str, str]:
    """Compile natural language without collapsing multiple subjects into one identity.

    Multi-person requests must remain multi-person. Subject-specific appearance and outfit
    details stay in the user's original wording instead of being hoisted into a global
    attribute block that SD1.5 can smear across every person in the scene.
    """
    import re

    raw = " ".join(str(user_prompt or "").split()).strip()
    if not raw:
        return raw, REALISM_NEGATIVE + ", " + SMART_NEGATIVE

    low = raw.lower()

    # Detect explicit multi-subject intent conservatively. This is intentionally lexical:
    # the art worker must remain local, deterministic and cheap on the field PC.
    multi_patterns = (
        r"\b(two|three|four|five|six)\s+(people|persons|adults|women|men|girls|guys|subjects|characters)\b",
        r"\b(couple|pair|group|trio|crowd)\b",
        r"\b(two|three|four|five|six)\s+distinct\b",
        r"\bwoman\s+and\s+(a\s+)?man\b",
        r"\bman\s+and\s+(a\s+)?woman\b",
        r"\bwomen\s+and\s+men\b",
        r"\bmen\s+and\s+women\b",
        r"\bwith\s+(another|two|three|four)\s+(adult|woman|man|person|people)\b",
    )
    multi = any(re.search(p, low) for p in multi_patterns)

    parts: list[str] = []
    parts.append("photorealistic fashion photograph" if any(k in low for k in ("photo", "photoreal", "realistic")) else "photorealistic photograph")

    wants_full = any(k in low for k in ("full body", "full-body", "head to toe", "feet visible", "visible feet", "platform sandals", "shoes"))
    if multi:
        framing = "multiple distinct adult people"
        if wants_full:
            framing += ", full bodies visible, head to toe in frame"
        framing += ", clearly different faces, clearly different hair, distinct body shapes, distinct outfits, no cloned subjects"
        parts.append(framing)

        # Preserve the original prompt as the authoritative per-subject binding source.
        # Do not extract/repeat one person's traits globally in multi-subject scenes.
        remainder = re.sub(r"studio\s+(?:photo|photograph)", "fashion photo", raw, flags=re.IGNORECASE)
        remainder = re.sub(r"(?:plain\s+)?(?:pink\s+)?studio\s+background", "solid plain pink seamless backdrop", remainder, flags=re.IGNORECASE)
        parts.append(remainder.strip(" ,"))
        parts.append("each person's described traits, hair, clothing, body, and accessories apply only to that person")
        parts.append("preserve subject count and subject order; do not merge identities")
    else:
        # Solo mode keeps the older useful attribute reinforcement behavior.
        if re.search(r"\b(man|male|guy)\b", low) and not re.search(r"\b(woman|female|girl)\b", low):
            subject = "single adult man"
        elif re.search(r"\b(woman|female|girl)\b", low):
            subject = "single adult woman"
        else:
            subject = "single adult person"
        if wants_full:
            subject += ", full body, head to toe in frame, both arms visible, both hands visible, both legs visible, both feet visible, centered standing pose"
        parts.append(subject)

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
            parts.append(", ".join(bindings))
            parts.append("clothing colors exactly as described")
        remainder = re.sub(r"studio\s+(?:photo|photograph)", "fashion photo", remainder, flags=re.IGNORECASE)
        remainder = re.sub(r"(?:plain\s+)?(?:pink\s+)?studio\s+background", "solid plain pink seamless backdrop", remainder, flags=re.IGNORECASE)
        remainder = " ".join(remainder.replace(", ,", ",").split()).strip(" ,")
        if remainder:
            parts.append(remainder)

    if "background" not in low and "backdrop" not in low:
        parts.append("simple seamless neutral backdrop")
    elif "pink" in low and ("background" in low or "backdrop" in low):
        parts.append("solid plain pink seamless backdrop, no visible photography equipment")

    parts.append("natural human proportions, realistic skin texture, anatomically coherent hands and feet")
    compiled = ", ".join(p for p in parts if p)

    negative = REALISM_NEGATIVE + ", " + SMART_NEGATIVE
    if multi:
        # The historical negative contained 'multiple people', which directly fought
        # every requested group scene. Remove only that phrase and strengthen anti-clone
        # language instead.
        negative = re.sub(r"(?:^|,\s*)multiple people(?:,|$)", ", ", negative, flags=re.IGNORECASE)
        negative = re.sub(r",\s*,", ",", negative).strip(" ,")
        negative += ", cloned face, same face on different people, duplicate identity, merged bodies"
    return compiled, negative
'''

text = replace_function(text, "_smart_prompt", replacement)

# Contract marker used by CI and field diagnostics.
marker = 'V120_ART_MULTISUBJECT_IDENTITY = "v0.12-multisubject-identity-v1"\n'
if "V120_ART_MULTISUBJECT_IDENTITY" not in text:
    version_line_end = text.find("\n", text.find("VERSION = ")) + 1
    text = text[:version_line_end] + marker + text[version_line_end:]

compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8")
print("Applied v0.12 multi-subject identity scoping fix")
