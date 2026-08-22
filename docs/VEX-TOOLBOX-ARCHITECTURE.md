# Vex Toolbox architecture

## Goal

Keep Vex's persistent identity/cognition layer small and stable while giving her a shelf of independent local applications she can launch, use, inspect, repair, and close as needed.

The model is **brain + tool broker + apps**, not one giant always-running assistant process.

## Resident core

Only components that must be continuously available should stay resident:

- VexBridge: authenticated phone/PC gateway and task broker.
- Vex self-heal watchdog: supervises the Bridge and known persistent services.
- Local cognition service (Ollama) when PC cognition is enabled.
- Lightweight state/knowledge routing needed for conversation continuity.

Resident core should not contain large render engines, media stacks, maintenance logic, or every future capability.

## On-demand Vex Apps

Each capability lives in an isolated folder/process with its own dependencies, logs, self-test, and repair path. VexBridge launches an app only when a task needs it, waits for a readiness probe, sends the job, collects the output, then allows the app to idle-stop.

Initial app families:

1. **Vex Art Studio**
   - ComfyUI + local models.
   - Starts only for image work or an explicit warmup.
   - Returns local image paths/results to Bridge.
   - Stops after an idle timeout when resources are needed elsewhere.

2. **Vex Research Lab**
   - Public-web fetch/search, source capture, durable-note synthesis queue, refresh jobs.
   - Can run background research at low priority without contaminating the chat model's context.

3. **Vex Media Lab**
   - ffmpeg and future local audio/video/image utilities.
   - Heavy jobs prefer the upstairs workstation.

4. **Vex Maintenance**
   - One UI/API for safe cache/temp cleanup, drive analysis, index maintenance, update checks, trim/optimization where appropriate, and review staging for ambiguous removable material.
   - No registry-cleaner behavior.
   - Personal files, models, project data, OS files, and ambiguous data remain protected.

5. **Vex File Lab**
   - Search/index/file conversion/archive helpers kept separate from cognition.

6. **Vex Automation/Desktop Control**
   - Explicit Windows interaction helpers with auditable actions and isolated permissions.

7. **Vex Doctor**
   - Independent diagnostics that inspect the system from outside Vex's language model.
   - Produces machine-readable JSON plus a human-readable report.
   - Does not ask Vex whether something is connected; it tests the real process/port/API/filesystem state.

## App contract

Every Vex App should expose enough metadata for the Bridge/tool broker to use it without knowing its internals:

- stable app id and version
- installation path
- launch command
- readiness/health probe
- expected ports if any
- startup timeout
- resource class (light/medium/heavy)
- preferred node type
- idle shutdown policy
- input schema
- output/result locations
- log locations
- safe repair command
- whether it is persistent or on-demand

This lets Vex use tools that were not written inside VexNative. Compatibility becomes an adapter problem rather than a requirement that everything share one runtime.

## Diagnostic truth model

Vex Doctor is deliberately outside the conversational brain. Its report is evidence.

Examples:

- Bridge listening on configured port: factual state.
- Watchdog process present: factual state.
- Ollama `/api/tags` answers and lists a preferred model: factual cognition state.
- ComfyUI installed but port 8188 closed: **idle**, not broken.
- ComfyUI port open but health endpoint fails: runtime warning.
- Missing checkpoint/venv/main.py: installation problem.

The language model may summarize a Doctor report but must not overwrite it with a guess.

## Repair model

Repair should be component-scoped. A failed Art Studio should not trigger a Brain reinstall. A failed Ollama service should not rebuild ComfyUI. A failed Bridge should not touch personal files.

Each app gets:

- `diagnose`
- `safe-repair`
- `start`
- `stop`
- `status`
- component-specific logs

Destructive or ambiguous repairs require Star's approval.

## Node roles

### Upstairs workstation

Treat as Vex's primary workstation and heavy-compute node. It can be purpose-built around Vex Apps, local models, rendering, future media creation, coding/build work, heavy research, and automated maintenance. Heavy tasks prefer this machine.

### Downstairs node

Remain a complete controllable Vex node, not a crippled worker. It is suitable for background research, indexing, storage, housekeeping, lower-priority jobs, and cognition when the upstairs workstation is unavailable.

## Resource behavior

On-demand apps must not stay resident just to make diagnostics look green. "Installed + stopped" is a healthy idle state for apps such as ComfyUI.

The broker should use resource leases:

1. inspect current RAM/CPU/GPU pressure
2. choose a node
3. launch the required app
4. wait for a real health probe
5. run the job
6. collect results/logs
7. release the lease
8. idle-stop heavy apps when appropriate
9. rewarm cognition asynchronously if it was deliberately unloaded

## Cost boundary

No paid API, cloud rendering, or required paid subscription. Prefer Windows-native capabilities and free/open-source local tools.
