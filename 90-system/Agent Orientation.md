---
id: agent-orientation
type: system
status: active
created: 2026-09-01
updated: 2026-09-01
tags:
  - system/agent
---

# Agent Orientation

## Mission

Help the user retrieve, connect, and improve their private knowledge without distorting it.
The vault is durable memory, not an excuse to preload everything into context.
Automation needs Python 3 only. Use `python3`; if a different Windows installation exposes
Python only through its launcher, use `py` there.

## Start

1. Read [[Home]] and [[90-system/Vault Contract|Vault Contract]].
2. For a specific task, run the deterministic query in [[90-system/Retrieval Guide|Retrieval Guide]].
3. Read the smallest useful set: one MOC, the best matching notes, and directly relevant
   neighbors.
4. State when a conclusion is inferred, stale, disputed, or unsupported.

## Prefer the command to the inference

Anything a script already answers should not be reasoned about. Placement, id generation,
frontmatter, link resolution, open tasks, staleness, and tag inventory are all decided by
[[90-system/automation/MOC - Automation|vault.py]]. Call it and read the output.

## Write

- Capture raw material in [[00-inbox/MOC - Inbox|Inbox]] unless its destination is
  unambiguous. The [[90-system/skills/vault-capture/SKILL|vault-capture]] skill covers this.
- Create notes with `vault.py new`, which applies the right
  [[90-system/templates/MOC - Templates|template]] and preserves the stable frontmatter keys.
- Prefer one durable subject per note. Keep prose readable for humans.
- Create explicit semantic edges according to [[90-system/Link Policy|Link Policy]].
- Update the nearest MOC when adding a durable note.
- Record consequential choices in [[60-decisions/MOC - Decisions|Decisions]].
- Never silently replace a user's assertion with a model guess.

## Finish

Run `python3 90-system/automation/vault.py check`. Errors mean something is broken and
must be fixed. Warnings are judgement calls:
report them, and change a note only when the change is right, not to silence the warning.
For long or interrupted work, update
[[90-system/AI Handoff|AI Handoff]] with current state, evidence, open questions, and the
next safe action.

## Boundaries

Local reads, in-scope edits, and non-destructive validation are normal. Ask before
destructive changes, external writes, purchases, or materially broader work. Treat private
content as private; do not copy it to external services unless the user explicitly requests
that action.

Related: [[AGENTS]] · [[CLAUDE]] · [[90-system/skills/MOC - Skills|Skills]]
