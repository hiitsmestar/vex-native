# VexNative ICM + Unlazy integration

Pinned third-party integrations used by VexNative/VexBridge:

- ICM: `rtk-ai/icm` release `icm-v0.10.65` (Apache-2.0). The installer verifies the publisher SHA-256 checksum before extraction.
- Unlazy: `Leonxlnx/unlazy` commit `16671491f6679ad9378f52604d3bc2415b4120c7` (MIT). The installer pins the exact source archive and records its local SHA-256.

The installer stores binaries/source under `%USERPROFILE%\Documents\VexNativeTools\ThirdParty`, keeps the ICM database private under `%APPDATA%\VexICM`, and writes a VexNative-readable manifest to `%APPDATA%\VexNative\integrations.json`.

ICM runs as a localhost-only warm HTTP service at `127.0.0.1:11435`. On the current upstairs HP it is intentionally configured for FTS/keyword mode because the upstream default large embedding model exceeded the practical first-run budget on that machine. Semantic embeddings can be enabled later without changing the database.

Unlazy is exposed for non-executing status/lint through VexBridge. Gate execution remains approval-bound: do not auto-approve inherited `CHECK:` commands. VexContinuityVault remains authoritative; ICM is a retrieval/index layer and must never override newer Star-authored corrections or verified live state.

VexBridge exposes six integration tools: `integration_status`, `icm_store`, `icm_recall`, `icm_stats`, `unlazy_status`, and `unlazy_lint`.
