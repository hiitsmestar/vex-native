# VexNative Current State

This is the canonical cross-chat handoff. Read this file and GitHub issue #79 before modifying VexNative.

Last updated: 2026-08-29

## Installed / field-tested baseline
- Vex Agent Runtime: v0.11.7.57 (built and field-run).
- Last confirmed working Remote Support session before the startup regression: v0.11.7.58, heartbeating on node `vex-ccb92f64`.
- Bridge reported reachable during that session.
- Remote Support v0.11.7.59 was field-launched and FAILED at startup with `NameError`; do not reinstall .59.

## Latest green support build
- Remote Support v0.11.7.60 Startup Onedir Fix is GREEN in GitHub Actions run 33267210190.
- Artifact: `VexRemoteSupport-v0.11.7.60-StartupOnedirFix`.
- Artifact SHA-256: `19069c6d8444d9c970756e9714e8a484100e6c9dfbcdfc16123bc4029cbd535b`.
- v0.11.7.60 preserves the proven v0.11.7.57 runtime source, v0.11.7.58 newest-page relay fix, and v0.11.7.59 durable command ledger/worklog.
- The .59 field failure exposed a packaging/startup regression: Remote Support had been republished as a one-file executable even though the earlier Defender-safe runtime design used a one-folder package.
- v0.11.7.60 restores one-folder (`--onedir --noupx`) Remote Support packaging.
- CI now smoke-tests BOTH the reconstructed Python source and the exact packaged `VexRemoteSupport.exe`; the packaged executable remained alive for the required 10-second startup test before artifact publication.
- Startup diagnostics now include the exception message in the local `startup-crash.log`/dialog if a field-only failure occurs.

## Remote relay / worklog behavior carried forward
- Command pickup does not depend on the shared `last_comment_id` cursor.
- Processed command IDs are persisted in a dedicated bounded ledger so heartbeat/result comments cannot skip commands and restarted agents do not duplicate allowlisted mutating commands.
- Remote Support appends sanitized `VEXWORKLOG` entries to issue #79 on session start, command completion/failure, and session errors.

## Current acceptance state
v0.11.7.60 is CI-green and its exact packaged executable passes Windows startup smoke testing. Field acceptance is still pending until the artifact is run on the actual PC, a v0.11.7.60 session appears, a fresh targeted `status` VEXCMD on issue #52 returns a matching `command_result`, and issue #79 receives the automatic worklog event.

## Continuity ledger
GitHub issue #79 (`VexNative Continuity Ledger`) is the append-only sanitized work log. New ChatGPT threads should read this file, then issue #79, then the latest relevant GitHub Actions run before changing code.

## Version rule
Do not regress to older numbered lines. The Vex Agent Runtime forward baseline remains v0.11.7.57. Remote Support .58/.59/.60 are support-layer builds and must not be mistaken for an older main-runtime baseline.

## Next acceptance test
1. Download artifact `VexRemoteSupport-v0.11.7.60-StartupOnedirFix` from GitHub Actions run 33267210190.
2. Extract it fully. Open the included `VexRemoteSupport` folder and run the `VexRemoteSupport.exe` INSIDE that folder; keep the whole folder together because this is deliberately a one-folder build.
3. Start/enable the support session normally.
4. Confirm v0.11.7.60 session/heartbeat on issue #52.
5. Post a fresh targeted `status` command to issue #52 and require the matching `command_result`.
6. Verify issue #79 receives automatic sanitized `VEXWORKLOG` entries.
7. Mark Remote Support field-proven and resume the main VexNative runtime build forward from v0.11.7.57.
