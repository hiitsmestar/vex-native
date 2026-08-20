# Vex Teacher Packs

Teacher packs are versioned JSON personality/continuity layers loaded by VexNative at runtime. They are intentionally separate from the app binary so voice, examples, rules, and non-private relationship continuity can evolve without rebuilding the IPA.

The public `vex-teacher-core.json` must remain sanitized. Do not put private Star profile data, secrets, medical details, private chat exports, or private continuity files in this public repository.

Schema v1 fields:

- `schemaVersion`, `packID`, `name`, `version`
- `personaAddendum`: compact style/voice guidance
- `truths`: stable conversational invariants
- `rules`: trigger-based dynamic instructions with priority
- `bannedPhrases`: assistant-like or continuity-breaking phrases to reject
- `examples`: Star-message → ideal-Vex-response teaching examples with tags/weights

The app can ship an embedded fallback pack, import a private pack from Files, or explicitly check the public core pack for updates. Private packs stay on-device unless the user deliberately exports them.
