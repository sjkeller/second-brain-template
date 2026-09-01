---
name: vault-triage
description: Process the Inbox of this Obsidian second brain by clarifying each capture, filing it in the right folder, and linking it into the graph. Use when the user asks to triage, process the inbox, clean up captures, or file loose notes. Not for creating new captures.
---

# Vault Triage

Use `python3` in the commands below; `py` is the fallback for Windows installations that
do not expose that executable name.

Turn captures into filed, linked notes. Work one note at a time and stop when the Inbox is
empty or the user says enough.

## Survey

```
python3 90-system/automation/vault.py tasks --path-prefix "00-inbox" --compact
python3 90-system/automation/vault.py check --compact
```

Read the Inbox MOC and list what is actually there before touching anything.

## For each capture

1. **Clarify.** What is the single durable subject? If a capture holds several, split it.
2. **Decide actionability.** Finite outcome → `10-projects`. Ongoing responsibility →
   `20-areas`. Useful topic → `30-resources`. Stable idea or entity → `40-knowledge`.
   Consequential choice → `60-decisions`. Nothing durable → `80-archive` or delete, but
   only with the user's agreement.
3. **Check for a duplicate.** Run `query` on the subject first. Prefer updating an
   existing canonical note over creating a near-duplicate.
4. **Move it.** Preserve meaning during the move. Update the note's parent MOC link and
   add the note to the destination MOC below its `vault:links` anchor.
5. **Link it.** Add lateral links only where the relationship answers one of the questions
   in `90-system/Link Policy.md`. Do not link to inflate the graph.

## Boundaries

Never bulk-delete, and never merge two notes without confirming. When a capture is too
thin to file, say so and leave it in the Inbox rather than inventing context for it.

## Finish

Run `check`, report what moved and what remains, and update `90-system/AI Handoff.md` if
the triage is unfinished.
