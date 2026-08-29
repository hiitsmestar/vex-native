# VexNative Current State

This is the canonical cross-chat handoff. Read this file and GitHub issue #79 before modifying VexNative.

Last updated: 2026-08-29

## Installed / field-tested baseline
- Vex Agent Runtime: v0.11.7.57 (built and field-run).
- Remote Support: v0.11.7.58 installed and actively heartbeating on node `vex-ccb92f64`.
- Bridge reported reachable during the v0.11.7.58 session.

## Current defect
Remote Support v0.11.7.58 publishes session/heartbeat events but fresh `VEXCMD` relay commands have not returned `command_result`. Issue #52 contains the live relay.

## Current engineering action
Build v0.11.7.59 Remote Support with command pickup independent of the shared `last_comment_id` cursor. It should persist a bounded set of processed command IDs, scan the newest relay pages every poll, and never let heartbeat/result comments cause a command to be skipped.

## Continuity ledger
GitHub issue #79 (`VexNative Continuity Ledger`) is the append-only sanitized work log. Remote Support should append `VEXWORKLOG` entries for session start, successful command completion, runtime version changes, and material health changes.

## Version rule
Do not regress to older numbered lines. The Vex Agent Runtime forward baseline is v0.11.7.57. Remote Support fixes after that use v0.11.7.58+ and must preserve the v0.11.7.57 runtime feature chain unless explicitly superseded by a newer green runtime build.

## Next acceptance test
1. Install/start the newest Remote Support build.
2. Confirm session heartbeat/version.
3. Post a fresh targeted `status` command to issue #52.
4. Require a matching `command_result`.
5. Verify issue #79 receives an automatic sanitized work-log entry.
6. Only then resume the main VexNative runtime build forward from v0.11.7.57.
