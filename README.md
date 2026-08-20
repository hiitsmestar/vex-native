# VexNative v0.5 — local girlfriend engine with self-education

This repository is intentionally safe to keep public. Personal Vex/Star profile data, chat history, memories, backups, learning exports, Brain Packs, and GGUF model files are excluded from the public tree.

## What this solves

You do not need to own a Mac. GitHub Actions supplies a hosted macOS runner that runs Xcode and produces an unsigned iPhone IPA. A Windows PC can then sign/install that IPA to an iPhone with the user's own Apple Account using a sideloading tool such as Sideloadly or AltServer/AltStore Classic.

No paid LLM API or hosted Vex backend is required.

## v0.5 self-education

VexNative now has a confidence-weighted local learning layer on top of the replaceable Brain Pack architecture. Explicit user corrections, preferences, and rules can become local memories. Repeated evidence reinforces existing memories instead of creating endless duplicates. Deterministic consolidation merges near-duplicates and prunes weak stale noise while preserving rules and correction-derived lessons.

The app can also create a private learning/training export containing teacher examples, learned memories, semantic rules, and conversation transcript for later review or future LoRA/fine-tuning work. The GGUF weights are not rewritten on the phone.

## Build

The workflow at `.github/workflows/build-unsigned-ipa.yml` runs on pushes to `main`, pull requests targeting `main`, and can also be started manually from GitHub Actions.

It resolves the local Swift package, builds the iOS app unsigned for a generic iPhone device, packages `VexNative.app` into `VexNative-unsigned.ipa`, and uploads the IPA as an artifact. If Xcode fails, the workflow uploads the build log for debugging.

## Local model

After installation, open **Brain** in VexNative and download/import a compatible GGUF model. Qwen3 0.6B is the preferred phone-size model, while smaller/larger alternatives remain available for comparison.

## Brain Packs

Personality, relationship rules, semantic rules, examples, and private memories can be imported on-device as a versioned JSON Brain Pack without replacing the GGUF model. Do not commit private Brain Packs to this public repository.

## Privacy boundary

Public: Swift source, Xcode project, llama.cpp package declaration, build workflow, generic personality shell.

Private/on-device: personal profile, chat history, memories, learning exports, Brain Packs, GGUF model files, backups.

## Cost boundary

The project is designed around a $0 path: no paid API, no hosted inference service, no paid Mac rental, no Xcode Cloud requirement, and no App Store release requirement. Free Apple signing remains time-limited and requires periodic re-signing.
