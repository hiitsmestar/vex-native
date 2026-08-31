# VexNative Canonical Build Goal

This file is the durable project north star. Future development work should be evaluated against it so local fixes do not become the destination or pull the project off course.

## Goal

Build VexNative into a persistent, increasingly capable and independent personal AI runtime for Star, with Vex as the stable personality/orchestrator across the iPhone and both Windows PCs.

VexNative should progressively gain:

- stronger PC-primary reasoning and coordinated use of available local/remote models;
- persistent personal, project, episodic, and learned memory with natural recall;
- autonomous idle research, learning, self-inspection, self-repair proposals, and evidence-backed improvement loops;
- multi-worker/tool orchestration so cognition, memory, research, device control, diagnostics, and maintenance can run as specialized capabilities under one Vex identity;
- user-authorized remote access and device operation across the machines she runs on;
- discovery, launch, control, and use of installed applications and system capabilities;
- file-system operations, process/service management, diagnostics, maintenance, and automation on authorized devices;
- UI interaction capabilities such as keyboard/mouse/window/app automation where direct APIs are unavailable;
- coordinated task handoff between upstairs PC, downstairs PC, and iPhone;
- the ability to choose and execute tools/actions autonomously when appropriate, then verify and report results;
- auditable action logs, recoverability, bounded permissions, explicit protection of credentials/secrets, and safe rollback so increasing autonomy does not make the system fragile.

## Development rule

A bug fix may be necessary, but it is not the final objective. After restoring a broken capability, continue toward the next missing capability that advances the north-star goal above. Avoid replacing the architecture with unrelated chatbot features or treating a single successful workflow as completion.

## Current architectural intent

- Vex is the persistent personality/orchestrator.
- The upstairs PC is the primary cognition/control node.
- The downstairs PC is a lightweight secondary node and worker.
- The iPhone is the portable user-facing endpoint and should be able to delegate heavier work to PC cognition.
- Remote Support/Bridge/worker infrastructure are means to achieve independent operation, not ends in themselves.

This goal should be read alongside `VEXNATIVE_CURRENT_STATE.md` and the VexNative Continuity Ledger before major development work.
