from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

OLLAMA_CHAT = "http://127.0.0.1:11434/api/chat"
MODEL_CANDIDATES = (
    "vex-qwen35-9b-q6:latest",
    "vex-qwen35-9b:latest",
)
MAX_IMAGE_BYTES = 30_000_000

REVIEW_SYSTEM = """You are Vex Visual QA, a strict local image-quality reviewer.
Return one JSON object only. No markdown and no prose outside JSON.
Judge only visible fidelity and quality. Check subject count, identity consistency,
hair and signature details, clothing and color fidelity, pose/framing, anatomy,
hands/feet, unwanted duplicate people or limbs, background contamination and realism.
If the image is acceptable, pass must be true and revised_prompt must be empty.
If a meaningful visible defect exists, pass must be false and revised_prompt must be
a single complete replacement image prompt preserving the user's original intent while
correcting only the observed problems. Do not invent extra subjects or scene elements.
JSON keys: pass, summary, issues, revised_prompt, confidence."""

def _image_b64(path: Path) -> str:
    data = path.read_bytes()
    if len(data) < 1000:
        raise ValueError("render image is unexpectedly small")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("render image exceeds visual QA size limit")
    return base64.b64encode(data).decode("ascii")

def _extract_json(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    try:
        obj = json.loads(value)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    start=value.find("{")
    end=value.rfind("}")
    if start >= 0 and end > start:
        try:
            obj=json.loads(value[start:end+1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    raise ValueError("visual reviewer did not return valid JSON")

def _normalize(obj: dict[str, Any]) -> dict[str, Any]:
    issues=obj.get("issues")
    if not isinstance(issues, list):
        issues=[] if issues in (None, "") else [str(issues)]
    try:
        confidence=max(0.0,min(1.0,float(obj.get("confidence") or 0.0)))
    except Exception:
        confidence=0.0
    return {
        "pass": bool(obj.get("pass", True)),
        "summary": str(obj.get("summary") or "")[:1000],
        "issues": [str(x)[:300] for x in issues[:12] if str(x).strip()],
        "revised_prompt": str(obj.get("revised_prompt") or "").strip()[:7000],
        "confidence": confidence,
    }

def review_image(image_path: str, original_prompt: str) -> dict[str, Any]:
    path=Path(str(image_path or "")).expanduser()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    encoded=_image_b64(path)
    user=(
        "Review this finished AI render against the original request. "
        "Do not critique things the request did not specify.\n\n"
        f"ORIGINAL REQUEST:\n{str(original_prompt or '').strip()[:7000]}"
    )
    last_error: Exception | None=None
    for model in MODEL_CANDIDATES:
        body=json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": REVIEW_SYSTEM},
                {"role": "user", "content": user, "images": [encoded]},
            ],
            "stream": False,
            "think": False,
            "keep_alive": 0,
            "format": "json",
            "options": {"num_ctx": 2048, "num_predict": 384, "temperature": 0.05},
        }).encode("utf-8")
        request=urllib.request.Request(
            OLLAMA_CHAT, data=body,
            headers={"Content-Type":"application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                payload=json.loads(response.read().decode("utf-8"))
            content=str((payload.get("message") or {}).get("content") or "")
            review=_normalize(_extract_json(content))
            review["model"]=str(payload.get("model") or model)
            return review
        except Exception as exc:
            last_error=exc
            continue
    raise RuntimeError(f"all visual-review models failed: {last_error}")

def _attach(result: dict[str, Any], review: dict[str, Any], *, corrected: bool) -> dict[str, Any]:
    value=dict(result)
    value["visual_review_used"]=True
    value["visual_review_pass"]=bool(review.get("pass", True))
    value["visual_review_summary"]=str(review.get("summary") or "")
    value["visual_review_issues"]=list(review.get("issues") or [])
    value["visual_review_confidence"]=review.get("confidence", 0.0)
    value["visual_review_model"]=str(review.get("model") or "")
    value["visual_review_corrected"]=bool(corrected)
    return value

def review_and_correct(
    result: dict[str, Any],
    original_prompt: str,
    orientation: str,
    vex_preset: bool,
    render_fn,
    stop_comfy_fn,
    *,
    allow_correction: bool=True,
) -> dict[str, Any]:
    if not isinstance(result, dict) or not result.get("ok") or not result.get("image_path"):
        try:
            stop_comfy_fn()
        except Exception:
            pass
        return result

    # The HP is RAM-constrained. Release worker-owned Comfy before loading Q6 vision.
    try:
        stop_comfy_fn()
    except Exception:
        pass

    try:
        first_review=review_image(str(result["image_path"]), original_prompt)
    except Exception as exc:
        value=dict(result)
        value.update({
            "visual_review_used": False,
            "visual_review_pass": True,
            "visual_review_summary": f"visual QA unavailable: {exc.__class__.__name__}",
            "visual_review_issues": ["review_unavailable"],
            "visual_review_confidence": 0.0,
            "visual_review_corrected": False,
        })
        return value

    first=_attach(result, first_review, corrected=False)
    revised=str(first_review.get("revised_prompt") or "").strip()
    if bool(first_review.get("pass", True)) or not allow_correction or not revised:
        return first

    corrected=render_fn(
        revised,
        orientation=orientation,
        seed=None,
        smart_prompt=True,
        vex_preset=bool(vex_preset),
    )
    try:
        stop_comfy_fn()
    except Exception:
        pass

    if not isinstance(corrected, dict) or not corrected.get("ok") or not corrected.get("image_path"):
        first["visual_review_correction_attempted"]=True
        first["visual_review_correction_failed"]=True
        return first

    try:
        second_review=review_image(str(corrected["image_path"]), original_prompt)
        final=_attach(corrected, second_review, corrected=True)
    except Exception as exc:
        final=dict(corrected)
        final.update({
            "visual_review_used": False,
            "visual_review_pass": True,
            "visual_review_summary": f"second-pass visual QA unavailable: {exc.__class__.__name__}",
            "visual_review_issues": ["second_review_unavailable"],
            "visual_review_confidence": 0.0,
            "visual_review_corrected": True,
        })

    final["visual_review_first_image"]=str(result.get("image_path") or "")
    final["visual_review_first_summary"]=str(first_review.get("summary") or "")
    final["visual_review_first_issues"]=list(first_review.get("issues") or [])
    final["visual_review_revised_prompt"]=revised
    return final