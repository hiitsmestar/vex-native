# VexNative Current State

This is the canonical cross-chat handoff. Read this file and GitHub issue #79 before modifying VexNative.

Last updated: 2026-08-29

## Installed / field-tested baseline
- Vex Agent Runtime: v0.11.7.57 (built and field-run).
- Remote Support installed at last live check: v0.11.7.58, heartbeating on node `vex-ccb92f64`.
- Bridge reported reachable during the v0.11.7.58 session.

## Latest green support build
- Remote Support v0.11.7.59 Command Ledger is GREEN in GitHub Actions run 33265483086.
- Artifact: `VexRemoteSupport-v0.11.7.59-CommandLedger`.
- v0.11.7.59 preserves the proven v0.11.7.57 runtime source and v0.11.7.58 newest-page relay fix.
- Command pickup no longer depends on the shared `last_comment_id` cursor.
- Processed command IDs are persisted in a dedicated bounded ledger so heartbeat/result comments cannot skip commands and restarted agents do not duplicate allowlisted mutating commands.
- Remote Support now appends sanitized `VEXWORKLOG` entries to issue #79 on session start, command completion/failure, and session errors.

## Current defect / acceptance state
v0.11.7.58 publishes session/heartbeat events but did not return fresh `VEXCMD` results. v0.11.7.59 is built to fix that defect, but field acceptance remains pending until it is run on the PC and returns a matching `command_result`.

## Continuity ledger
GitHub issue #79 (`VexNative Continuity Ledger`) is the append-only sanitized work log. New ChatGPT threads should read this file, then issue #79, then the latest relevant GitHub Actions run before changing code.

## Version rule
Do not regress to older numbered lines. The Vex Agent Runtime forward baseline is v0.11.7.57. Remote Support fixes v0.11.7.58/v0.11.7.59 are support-layer builds and must not be mistaken for an older main-runtime baseline.

## Next acceptance test
1. Run `VexRemoteSupport.exe` from artifact `VexRemoteSupport-v0.11.7.59-CommandLedger` using the normal existing cutover behavior.
2. Confirm a v0.11.7.59 session/heartbeat.
3. Post a fresh targeted `status` command to issue #52.
4. Require a matching `command_result`.
5. Verify issue #79 receives automatic sanitized `VEXWORKLOG` entries.
6. Mark Remote Support proven and resume the main VexNative runtime build forward from v0.11.7.57.
