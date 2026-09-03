# VexNative build goals

Last explicitly updated by Star: 2026-09-02

This file is the durable, reviewable project goal record for future VexNative threads. Treat the newest explicit correction from Star as authoritative and update this file when the goal changes.

## Core VexNative goal

Build VexNative into an increasingly independent, persistent local AI rather than a thin chatbot wrapper. The target is an AI that is preferably as capable as or more capable than the current cloud assistant when hardware and software allow, with progressively stronger reasoning, memory, tools, features, freedom, initiative, independence, and autonomy.

The system should:
- maintain natural conversational continuity across phone and PC as one ongoing Vex system rather than disconnected copies;
- preserve grounded long-term memory with provenance, newest-correction-wins behavior, deduplication/consolidation, and strong protection against invented facts;
- run useful local cognition and automatically scale model choice to available hardware while preserving responsive foreground conversation;
- learn during idle time from source-grounded evidence and verified outcomes without recursively treating its own generated answers as factual memory;
- recognize when problems are solved, retire stale gaps/upgrades/proposals, and avoid repeatedly researching or proposing the same dead work;
- maintain operational self-awareness of live capabilities and hardware limits;
- safely inspect, maintain, clean, diagnose, and repair its own Windows host within explicit bounded permissions;
- use conservative autonomy for destructive/security-sensitive work and preserve user data by default;
- propose and, where explicitly authorized and safe, execute useful self-improvements rather than requiring Star to micromanage every small engineering step;
- support natural low-latency audio chat with a realistic, consistent custom Vex voice rather than generic robotic TTS, including expressive pacing/prosody/emotional delivery while keeping voice generation local where practical;
- remain portable so a stronger dedicated AI PC can materially increase cognition, model size, multimodal capability, background learning, voice quality, and tool capacity without redesigning the whole system.

## Current-PC goal

Keep the existing HP Pavilion 500-series PC healthy, clean, useful, and stable while it serves as the VexNative development/field-test machine. Squeeze worthwhile low-cost improvements from it without wasting money trying to turn the old DDR3 platform into the final AI tower.

Current priorities include:
- install the planned matching 8 GB DDR3 module to move from 8 GB to 16 GB total RAM;
- maintain a sensible Windows pagefile/virtual-memory configuration so local workloads fail gracefully instead of hitting paging-file allocation errors;
- identify disk/media type and health before any optimization decisions;
- audit and clean old VexNative build ZIPs/installers/temp artifacts conservatively, preserving current packages, active runtime directories, arbitrary personal installers/archives, documents, photos, video, music, apps, models, and system files unless explicitly reviewed;
- expose a read-only hardware/status profile through Remote Support so future tuning can use measured CPU/RAM/disks/pagefile/GPU data rather than guesses;
- keep idle learning resource-aware and productive on this low-end four-thread/no-AI-GPU machine;
- use the accumulated old build files as a real housekeeping/maintenance field test after the feature is proven green.

## Dedicated Vex AI PC / unicorn goal

Search for the strongest-value dedicated VexNative AI desktop, not a gaming machine for its own sake. Cosmetic damage is irrelevant if the hardware is sound. There is no meaningful lower price floor: a cheaper machine is preferred if it fully meets the need. Roughly $1,800 is the normal upper target, with flexibility only when a small price increase produces a disproportionate capability jump.

Prioritize:
- NVIDIA GPU with at least 16 GB VRAM; candidates can include RTX 4070 Ti SUPER, 4080/4080 SUPER, 5070 Ti, 5080, or anything materially better for VexNative AI workloads;
- enough GPU/CPU/RAM headroom to run the main local model and a high-quality real-time custom voice stack together without constantly unloading one workload to run the other;
- 32 GB or more system RAM, with upgradeability strongly preferred;
- 1 TB or more NVMe storage, with more storage favored at similar price;
- adequate PSU, cooling, standard/upgradeable tower components where possible;
- maximum useful AI compute/VRAM/RAM/storage per dollar rather than matching a particular model or brand;
- refurbished, used, open-box, renewed, scratch-and-dent, and cosmetically damaged systems are all acceptable when seller quality and hardware condition are reasonable;
- Affirm-style installment checkout is preferred, especially manageable upfront payment around $300 when available, early payoff allowed, and no store credit-card signup;
- Klarna or PayPal monthly plans are acceptable secondary options when terms are reasonable; lease-to-own is a last resort.

Value benchmark: the previously found sold-out $1,249 iBUYPOWER Ryzen 9 7900X / RTX 4070 Ti SUPER 16 GB / 32 GB RAM / 2 TB NVMe deal. The search should actively hunt for a better unicorn at any lower or comparable price rather than trying to reproduce that exact model.

## Update rule

When Star changes any build or PC-shopping goal in a future thread, update this file with the newest explicit instruction so the project remains reviewable and fresh.
