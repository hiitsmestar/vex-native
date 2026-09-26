from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import zlib
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_REPO = "hiitsmestar/vex-native"
DEFAULT_OWNER = "hiitsmestar"
DEFAULT_ISSUE = 84
COMMAND_MARKER = "VEXBRIDGE_CMD\n"
RESULT_MARKER = "VEXBRIDGE_RESULT\n"
KEY_MARKER = "VEXBRIDGE_PUBLIC_KEY\n"


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def derive(shared: bytes, node: str, cmd_id: str, purpose: bytes) -> bytes:
    salt = hashlib.sha256(f"{node}:{cmd_id}".encode()).digest()
    return HKDF(algorithm=SHA256(), length=32, salt=salt, info=purpose).derive(shared)


def gh_path() -> Path:
    explicit = os.environ.get("VEXBRIDGE_GH_PATH", "").strip()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    candidates.extend(
        [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "GitHub CLI" / "gh.exe",
            local / "Programs" / "GitHubCLI" / "bin" / "gh.exe",
            local / "VexBridgeBootstrap" / "gh" / "bin" / "gh.exe",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("GitHub CLI not found. Set VEXBRIDGE_GH_PATH to gh.exe.")


def gh_api(args: list[str], input_json: Any | None = None, timeout: int = 30) -> Any:
    cmd = [str(gh_path()), "api", *args]
    stdin = None
    if input_json is not None:
        cmd.extend(["--input", "-"])
        stdin = json.dumps(input_json)
    result = subprocess.run(
        cmd,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "gh api failed")[-2000:])
    text = result.stdout.strip()
    return json.loads(text) if text else {}


def _unwrap_json_marker(body: str, marker: str) -> dict[str, Any] | None:
    if not body.startswith(marker):
        return None
    raw = body[len(marker) :].strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    data = json.loads(raw)
    return data if isinstance(data, dict) else None


def parse_public_key(body: str) -> dict[str, Any] | None:
    return _unwrap_json_marker(body, KEY_MARKER)


def parse_result(body: str) -> dict[str, Any] | None:
    return _unwrap_json_marker(body, RESULT_MARKER)


def issue_comment_count(repo: str, issue: int) -> int:
    data = gh_api([f"repos/{repo}/issues/{issue}"])
    return max(0, int(data.get("comments", 0)))


def fetch_comment_page(repo: str, issue: int, page: int) -> list[dict[str, Any]]:
    data = gh_api([f"repos/{repo}/issues/{issue}/comments?per_page=100&page={page}"])
    return data if isinstance(data, list) else []


def latest_comment_pages(repo: str, issue: int, page_count: int = 3) -> list[dict[str, Any]]:
    count = issue_comment_count(repo, issue)
    last = max(1, (count + 99) // 100)
    first = max(1, last - page_count + 1)
    out: list[dict[str, Any]] = []
    for page in range(first, last + 1):
        out.extend(fetch_comment_page(repo, issue, page))
    return out


def find_public_key(repo: str, issue: int, owner: str, node: str) -> str:
    count = issue_comment_count(repo, issue)
    last = max(1, (count + 99) // 100)
    for page in range(last, 0, -1):
        comments = fetch_comment_page(repo, issue, page)
        for comment in reversed(comments):
            if str((comment.get("user") or {}).get("login") or "").lower() != owner.lower():
                continue
            env = parse_public_key(str(comment.get("body") or ""))
            if env and str(env.get("node")) == node and env.get("public_key"):
                return str(env["public_key"])
    raise RuntimeError(f"No VexBridge public key found for node {node}")


def encrypt_command(
    node: str,
    public_key_b64: str,
    tool: str,
    arguments: dict[str, Any],
    ttl_seconds: int = 600,
    cmd_id: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    if ttl_seconds < 1 or ttl_seconds > 1800:
        raise ValueError("ttl_seconds must be between 1 and 1800")
    cmd_id = cmd_id or f"chat-{secrets.token_hex(8)}"
    ephemeral = X25519PrivateKey.generate()
    ephemeral_public = ephemeral.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    peer = X25519PublicKey.from_public_bytes(b64d(public_key_b64))
    shared = ephemeral.exchange(peer)
    key = derive(shared, node, cmd_id, b"vexbridge-command-v1")
    nonce = os.urandom(12)
    now = time.time()
    payload = {
        "tool": tool,
        "arguments": arguments,
        "created_at": now,
        "expires_at": now + ttl_seconds,
    }
    aad = f"vexbridge-command-v1:{node}:{cmd_id}".encode()
    cipher = AESGCM(key).encrypt(
        nonce,
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        aad,
    )
    envelope = {
        "v": 1,
        "id": cmd_id,
        "node": node,
        "epk": b64e(ephemeral_public),
        "nonce": b64e(nonce),
        "ciphertext": b64e(cipher),
    }
    return envelope, shared


def command_comment(envelope: dict[str, Any]) -> str:
    return COMMAND_MARKER + "```json\n" + json.dumps(envelope, separators=(",", ":")) + "\n```"


def post_command(repo: str, issue: int, envelope: dict[str, Any]) -> dict[str, Any]:
    return gh_api(
        ["-X", "POST", f"repos/{repo}/issues/{issue}/comments"],
        {"body": command_comment(envelope)},
    )


def decrypt_result_envelopes(
    node: str,
    cmd_id: str,
    shared: bytes,
    envelopes: list[dict[str, Any]],
) -> dict[str, Any]:
    matching = [
        env
        for env in envelopes
        if str(env.get("node")) == node and str(env.get("id")) == cmd_id
    ]
    if not matching:
        raise RuntimeError("No matching result envelopes")
    expected = int(matching[0].get("parts", 0))
    nonce = str(matching[0].get("nonce") or "")
    if expected < 1 or not nonce:
        raise RuntimeError("Invalid result envelope metadata")
    by_part: dict[int, str] = {}
    for env in matching:
        if int(env.get("parts", 0)) != expected or str(env.get("nonce") or "") != nonce:
            raise RuntimeError("Inconsistent multipart result metadata")
        part = int(env.get("part", 0))
        if 1 <= part <= expected:
            by_part[part] = str(env.get("data") or "")
    if len(by_part) != expected:
        raise RuntimeError(f"Incomplete result: have {len(by_part)} of {expected} parts")
    encoded = "".join(by_part[i] for i in range(1, expected + 1))
    key = derive(shared, node, cmd_id, b"vexbridge-result-v1")
    aad = f"vexbridge-result-v1:{node}:{cmd_id}".encode()
    packed = AESGCM(key).decrypt(b64d(nonce), b64d(encoded), aad)
    data = json.loads(zlib.decompress(packed).decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Decrypted result is not an object")
    return data


def wait_for_result(
    repo: str,
    issue: int,
    owner: str,
    node: str,
    cmd_id: str,
    shared: bytes,
    timeout_seconds: int,
    poll_seconds: float = 4.0,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    seen: dict[int, dict[str, Any]] = {}
    while time.time() < deadline:
        for comment in latest_comment_pages(repo, issue, page_count=3):
            if str((comment.get("user") or {}).get("login") or "").lower() != owner.lower():
                continue
            env = parse_result(str(comment.get("body") or ""))
            if not env or str(env.get("node")) != node or str(env.get("id")) != cmd_id:
                continue
            part = int(env.get("part", 0))
            if part > 0:
                seen[part] = env
        if seen:
            expected = int(next(iter(seen.values())).get("parts", 0))
            if expected > 0 and len(seen) >= expected:
                return decrypt_result_envelopes(node, cmd_id, shared, list(seen.values()))
        time.sleep(max(0.5, poll_seconds))
    raise TimeoutError(f"Timed out waiting for VexBridge result {cmd_id}")


def parse_arguments(text: str) -> dict[str, Any]:
    if text.startswith("@"):
        text = Path(text[1:]).read_text(encoding="utf-8-sig")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("arguments must decode to a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Send an encrypted VexBridge tool call through GitHub issue relay.")
    parser.add_argument("--node", required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--arguments", default="{}", help="JSON object or @path-to-json-file")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--issue", type=int, default=DEFAULT_ISSUE)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--ttl", type=int, default=600)
    args = parser.parse_args()

    arguments = parse_arguments(args.arguments)
    public_key = find_public_key(args.repo, args.issue, args.owner, args.node)
    envelope, shared = encrypt_command(args.node, public_key, args.tool, arguments, args.ttl)
    post_command(args.repo, args.issue, envelope)
    result = wait_for_result(
        args.repo,
        args.issue,
        args.owner,
        args.node,
        str(envelope["id"]),
        shared,
        args.timeout,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
