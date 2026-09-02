---
id: ai-handoff
type: system
status: ready
created: 2026-09-01
updated: 2026-09-02
tags:
  - system/agent
---

# AI Handoff

Use this only for work that must continue across sessions or context compaction. Replace
stale operational detail instead of appending an endless diary.

## Goal

No active cross-session task.

## Confirmed state

- Vault skeleton initialized on 2026-09-01 and hardened with trust, freshness, retrieval,
  merge-safety, human-readable writing, and human-AI review conventions.
- Entry points: [[Home]], [[AGENTS]], and [[CLAUDE]]. `CLAUDE.md` imports `AGENTS.md`, so
  the shared instructions exist once.
- Deterministic tooling: [[90-system/automation/MOC - Automation|Automation]]. The
  machine-checkable structural invariants enumerated there have checks; provenance and
  other judgement-dependent rules remain explicit review responsibilities.
- Skills live once under [[90-system/skills/MOC - Skills|Skills]]; the `.claude` and
  `.agents` copies are verified pointers.
- Human dashboards: [[Home]] embeds the operational
  [[90-system/bases/MOC - Bases|Bases]], including review and contextual views.
- Evaluation includes private retrieval judgments and paired human-task observations; no
  synthetic example is evidence for enabling semantic retrieval or declaring usability.
- Safe Obsidian integration is documented in
  [[90-system/Obsidian Integration|Obsidian Integration]].

## Open questions

- Real-world usability and retrieval cases still need to be collected privately. Until
  then, the evaluation gates intentionally report insufficient evidence.

## Next safe action

Capture real material in [[00-inbox/MOC - Inbox|Inbox]] with
[[90-system/skills/vault-capture/SKILL|vault-capture]], then process it during the first
[[50-journal/weekly/MOC - Weekly Reviews|weekly review]]. Treat the current layout as the
baseline for the next measured usability iteration.
