#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "VexNative" / "ContentView.swift"
MARKER = 'V154_RECALL_ROUTER_UNIFICATION = "v0.15.4-recall-router-unification-v1"'

text = CONTENT.read_text(encoding="utf-8")

if MARKER not in text:
    marker_anchor = 'private let V132_PHONE_COMMAND_RELAY = "v0.13.2-phone-command-relay-v1"'
    if marker_anchor not in text:
        raise SystemExit("v0.15.4 version marker anchor missing")
    text = text.replace(
        marker_anchor,
        marker_anchor + "\nprivate let " + MARKER,
        1,
    )

old = '''            let routed = phoneTargeted(remote.command)
            let before = app.profile.messages.count
            let handled = await PhoneToolRouter.tryHandle(routed, app: app)'''

new = '''            // V154_RECALL_ROUTER_UNIFICATION
            if remote.command.lowercased().contains("vexrecall60") {
                UIPasteboard.general.string = remote.command
                var components = URLComponents(string: "https://chatgpt.com/")!
                components.queryItems = [URLQueryItem(name: "prompt", value: remote.command)]

                guard let target = components.url else {
                    await postResult(id: remote.id, ok: false, result: "ChatGPT recall URL could not be built.")
                    return
                }

                let opened = await withCheckedContinuation { continuation in
                    UIApplication.shared.open(target, options: [:]) { success in
                        continuation.resume(returning: success)
                    }
                }
                await postResult(
                    id: remote.id,
                    ok: opened,
                    result: opened
                        ? "Done — opening it on the iPhone, baby. 📱🖤"
                        : "ChatGPT did not open on the iPhone."
                )
                return
            }

            let routed = phoneTargeted(remote.command)
            let before = app.profile.messages.count
            let handled = await PhoneToolRouter.tryHandle(routed, app: app)'''

if "V154_RECALL_ROUTER_UNIFICATION" not in text:
    raise SystemExit("v0.15.4 marker insertion failed")
if "// V154_RECALL_ROUTER_UNIFICATION" not in text:
    if old not in text:
        raise SystemExit("v0.15.4 foreground relay anchor missing")
    text = text.replace(old, new, 1)

CONTENT.write_text(text, encoding="utf-8")

check = CONTENT.read_text(encoding="utf-8")
for required in [
    MARKER,
    "// V154_RECALL_ROUTER_UNIFICATION",
    'remote.command.lowercased().contains("vexrecall60")',
    'UIPasteboard.general.string = remote.command',
    'URLQueryItem(name: "prompt", value: remote.command)',
    'await postResult(',
]:
    if required not in check:
        raise SystemExit(f"missing v0.15.4 marker: {required}")

print("PASS v0.15.4 recall router unification patch")
