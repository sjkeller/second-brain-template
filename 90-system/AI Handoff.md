---
id: ai-handoff
type: system
status: ready
created: 2026-09-01
updated: 2026-09-01
tags:
  - system/agent
---

# AI Handoff

Use this only for work that must continue across sessions or context compaction. Replace
stale operational detail instead of appending an endless diary.

## Goal

No active cross-session task.

## Confirmed state

- Vault skeleton initialized on 2026-09-01 and hardened the same day.
- Entry points: [[Home]], [[AGENTS]], and [[CLAUDE]]. `CLAUDE.md` imports `AGENTS.md`, so
  the shared instructions exist once.
- Deterministic tooling: [[90-system/automation/MOC - Automation|Automation]]. The
  machine-checkable structural invariants enumerated there have checks; provenance and
  other judgement-dependent rules remain explicit review responsibilities.
- Skills live once under [[90-system/skills/MOC - Skills|Skills]]; the `.claude` and
  `.agents` copies are verified pointers.
- Human dashboards: [[90-system/bases/MOC - Bases|Bases]].
- No real content yet. The vault holds 52 structural notes and no user material.

## Open questions

- The vault is not under version control and has no `.obsidian` folder. Both were reviewed
  and deliberately left to the user; see [[90-system/Obsidian Setup|Obsidian Setup]] for
  the settings that still need applying by hand.

## Next safe action

Capture real material in [[00-inbox/MOC - Inbox|Inbox]] with
[[90-system/skills/vault-capture/SKILL|vault-capture]], then process it during the first
[[50-journal/weekly/MOC - Weekly Reviews|weekly review]].
