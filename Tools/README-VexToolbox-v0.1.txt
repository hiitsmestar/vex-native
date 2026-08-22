Vex Toolbox v0.1 - Modular Apps + Diagnostics Foundation
=========================================================

This package is deliberately independent from the VexBridge build.
It does not replace, reinstall, or modify VexBridge, Ollama, ComfyUI, or VexNative.

WHY IT EXISTS
-------------
Vex should act increasingly like an operating-system-level coordinator that can use
specialized local apps when needed instead of stuffing every implementation into the
conversation/cognition process. Heavy tools can remain idle until a job needs them.
Failures can be isolated and diagnosed without asking a language model to guess what
is running.

INCLUDED
--------
RUN-VEX-DIAGNOSTIC.cmd
  Double-click this. It runs Vex Doctor and opens a plain-text report.

VexDoctor.ps1
  Independent read-only diagnostics for:
  - Windows host, RAM, CPU, fixed-drive free space
  - VexBridge config/process/listening port/authenticated /status
  - Ollama API + installed models
  - Bridge /llm/status cognition path
  - VexArt/ComfyUI installation + checkpoint + live /system_stats
  - detailed ComfyUI render-error log when present
  - Vex learning SQLite store
  - learning status route when available
  - self-heal watchdog process and recent watchdog log evidence when discoverable

  Reports are written to:
    %APPDATA%\VexBridge\diagnostics\

  latest.txt and latest.json always point to the newest run.
  Bridge pairing tokens are NEVER written into reports.

VexAppRegistry.json
  Trusted local capability catalog. It records which capabilities should be
  always-on, on-demand, or idle-background; resource class; preferred node; health
  contract; and whether the capability is truly external yet or still Bridge-managed.

VexAppHost.ps1
  First app-host layer. It can list registered Vex apps, report direct health state,
  and start apps that already have a safe explicit launcher contract. It refuses to
  pretend Bridge-internal capabilities are independent before they are actually
  extracted.

NO PAID API. NO CLOUD RENDERING. NO SUBSCRIPTION REQUIRED.

FIRST TEST
----------
1. Extract this ZIP anywhere on either Windows Vex node.
2. Leave the existing v0.9.7.3 Bridge/watchdog exactly as they are.
3. Double-click RUN-VEX-DIAGNOSTIC.cmd.
4. Read the report that opens in Notepad.

This is phase one of the modular architecture. The next extraction target is the art
runner: ComfyUI is already an independent program, so its workflow/launch/health job
logic can move behind a clean app contract without changing Vex's conversation brain.
