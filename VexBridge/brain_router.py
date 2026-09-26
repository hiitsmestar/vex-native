from __future__ import annotations

import os
import time
from typing import Any, Literal

import httpx

FAST_URL = os.environ.get("VEX_FAST_BRAIN_URL", "http://127.0.0.1:11434").rstrip("/")
FAST_MODEL = os.environ.get("VEX_FAST_BRAIN_MODEL", "vex-qwen35-9b:latest")
DEEP_URL = os.environ.get("VEX_BONSAI_URL", "http://127.0.0.1:11436").rstrip("/")
DEEP_MODEL = os.environ.get("VEX_BONSAI_MODEL", "").strip()
FAST_CTX = int(os.environ.get("VEX_FAST_CTX", "8192"))
DEEP_MAX_TOKENS = int(os.environ.get("VEX_DEEP_MAX_TOKENS", "4096"))

DEEP_HINTS = {
    "analyze", "analysis", "architecture", "debug", "diagnose", "reason",
    "reasoning", "compare", "design", "implement", "refactor", "research",
    "plan", "planning", "complex", "multi-step", "long-horizon", "code",
    "coding", "review", "verify", "proof", "optimize", "strategy",
}


def _get_json(url: str, timeout: float = 2.5) -> Any:
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def fast_status() -> dict[str, Any]:
    try:
        data = _get_json(FAST_URL + "/api/tags")
        names = [
            str(item.get("name") or item.get("model") or "")
            for item in (data.get("models") or [])
            if isinstance(item, dict)
        ]
        return {
            "available": True,
            "provider": "ollama",
            "url": FAST_URL,
            "model": FAST_MODEL,
            "installed": FAST_MODEL in names,
            "models": names,
        }
    except Exception as exc:
        return {
            "available": False,
            "provider": "ollama",
            "url": FAST_URL,
            "model": FAST_MODEL,
            "error": f"{type(exc).__name__}: {exc}",
        }


def deep_status() -> dict[str, Any]:
    try:
        data = _get_json(DEEP_URL + "/v1/models")
        ids = [
            str(item.get("id") or "")
            for item in (data.get("data") or [])
            if isinstance(item, dict)
        ]
        return {
            "available": True,
            "provider": "prismml-llama.cpp",
            "url": DEEP_URL,
            "model": DEEP_MODEL or (ids[0] if ids else None),
            "models": ids,
        }
    except Exception as exc:
        return {
            "available": False,
            "provider": "prismml-llama.cpp",
            "url": DEEP_URL,
            "model": DEEP_MODEL or None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def status() -> dict[str, Any]:
    fast = fast_status()
    deep = deep_status()
    return {
        "ok": bool(fast.get("available") or deep.get("available")),
        "fast": fast,
        "deep": deep,
        "policy": "auto uses fast for ordinary turns and Bonsai for complex/long-horizon work",
    }


def choose_mode(prompt: str, requested: str = "auto") -> Literal["fast", "deep"]:
    mode = (requested or "auto").strip().lower()
    if mode in {"fast", "deep"}:
        return mode  # type: ignore[return-value]
    lowered = (prompt or "").lower()
    words = set(lowered.replace("/", " ").replace("-", " ").split())
    if len(prompt) >= 700 or words.intersection(DEEP_HINTS):
        return "deep"
    return "fast"


def _fast_chat(prompt: str, system: str | None, temperature: float) -> tuple[str, str]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": FAST_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": FAST_CTX, "temperature": temperature},
    }
    with httpx.Client(timeout=300.0) as client:
        response = client.post(FAST_URL + "/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
    return str((data.get("message") or {}).get("content") or ""), FAST_MODEL


def _deep_chat(
    prompt: str,
    system: str | None,
    temperature: float,
    max_tokens: int,
) -> tuple[str, str]:
    info = deep_status()
    if not info.get("available"):
        raise RuntimeError(str(info.get("error") or "Bonsai server unavailable"))
    model = DEEP_MODEL or str(info.get("model") or "")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max(1, min(int(max_tokens), 16384)),
        "stream": False,
    }
    with httpx.Client(timeout=900.0) as client:
        response = client.post(DEEP_URL + "/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Bonsai returned no choices")
    return str(((choices[0] or {}).get("message") or {}).get("content") or ""), model


def chat(
    prompt: str,
    mode: Literal["auto", "fast", "deep"] = "auto",
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = DEEP_MAX_TOKENS,
) -> dict[str, Any]:
    if not (prompt or "").strip():
        raise ValueError("prompt is required")
    requested = mode
    selected = choose_mode(prompt, mode)
    started = time.time()
    fallback = None

    if selected == "deep":
        try:
            text, model = _deep_chat(prompt, system, temperature, max_tokens)
            provider = "bonsai"
        except Exception as exc:
            fallback = f"{type(exc).__name__}: {exc}"
            text, model = _fast_chat(prompt, system, temperature)
            selected = "fast"
            provider = "ollama"
    else:
        try:
            text, model = _fast_chat(prompt, system, temperature)
            provider = "ollama"
        except Exception as exc:
            fallback = f"{type(exc).__name__}: {exc}"
            text, model = _deep_chat(prompt, system, temperature, max_tokens)
            selected = "deep"
            provider = "bonsai"

    return {
        "ok": True,
        "requestedMode": requested,
        "mode": selected,
        "provider": provider,
        "model": model,
        "fallback": fallback,
        "latencyMs": round((time.time() - started) * 1000, 1),
        "text": text,
    }
