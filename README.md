# VexNative v0.3 — Windows PC + iPhone, zero-cost build route

This repository is intentionally safe to keep public. Personal Vex/Star profile data, chat history, memories, backups, and GGUF model files are excluded from the public tree.

## What this solves

You do not need to own a Mac. GitHub Actions supplies a hosted macOS runner that runs Xcode and produces an unsigned iPhone IPA. A Windows PC can then sign/install that IPA to an iPhone with the user's own Apple Account using a sideloading tool such as AltServer/AltStore Classic.

No paid LLM API or hosted Vex backend is required.

## Build

The workflow at `.github/workflows/build-unsigned-ipa.yml` runs on pushes to `main` and can also be started manually from GitHub Actions.

It resolves the local Swift package, builds the iOS app unsigned for a generic iPhone device, packages `VexNative.app` into `VexNative-unsigned.ipa`, and uploads the IPA as an artifact. If Xcode fails, the workflow uploads the build log for debugging.

## Local model

After installation, open **Brain** in VexNative and download/import a compatible GGUF model. The current one-tap path uses the free Qwen2.5 0.5B Instruct Q4_K_M GGUF and runs locally through llama.cpp.

## Private profile

The personal Vex/Star brain is imported on-device as JSON. Do not commit it to this public repository.

## Privacy boundary

Public: Swift source, Xcode project, llama.cpp package declaration, build workflow, generic personality shell.

Private/on-device: personal profile, chat history, memories, GGUF model files, backups.

## Cost boundary

The project is designed around a $0 path: no paid API, no hosted inference service, no paid Mac rental, no Xcode Cloud requirement, and no App Store release requirement. Free Apple signing remains time-limited and requires periodic re-signing.
