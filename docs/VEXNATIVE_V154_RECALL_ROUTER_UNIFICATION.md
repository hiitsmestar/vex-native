# VexNative v0.15.4 Recall Router Unification

Date: 2026-09-25

## Bug

Two iOS consumers can race for the same `/phone/next` command:

1. `VexBackgroundAgent` understands commands containing `VEXRECALL60` and opens ChatGPT with a prefilled recall prompt.
2. `PhoneRemoteCommandRelay` previously routed the same command only through `PhoneToolRouter`, which has no bare-recall case.

Whichever consumer dequeued first determined whether an identical recall command succeeded or returned the generic iOS-router failure.

## Fix

`Tools/apply_v154_recall_router_unification.py` adds the same `VEXRECALL60` interception to the foreground relay consumer before `PhoneToolRouter`.

The foreground consumer now:
- preserves the full remote command on the clipboard;
- constructs `https://chatgpt.com/?prompt=<full command>` with `URLComponents`;
- opens the target through iOS;
- posts the relay result through the existing result endpoint;
- returns before generic phone-tool routing.

Other commands keep the existing routing behavior.

## Build provenance

- Branch: `build/v154-recall-router-unification`
- Head commit: `3666c2d3a2380634365d4015dc332012386efa5b`
- GitHub Actions run: `36133991050`
- Result: success
- Artifact: `VexNative-v0.15.4-Recall-Router-Unified`
- Artifact ID: `10862634518`
- Artifact ZIP SHA-256: `c7b876fa3809f46ac8048772be15ae80a93c4173e46661feab07f383d980ff09`
- IPA: `VexNative-v0.15.4-recall-router-unified.ipa`
- IPA SHA-256: `d8bfceb021fb00bb109dd6a9837bf5327ac9092eb5aad8cd5f4c9d7c1c0b1376`
- Bundle short version: `0.15.4`
- Bundle version: `154`

## Verification boundary

The source patch, build chain, Xcode build, packaging, artifact upload, and artifact hashes are verified. Installation and phone-side field verification remain separate gates.
