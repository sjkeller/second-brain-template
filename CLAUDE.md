@AGENTS.md

## Claude Code specifics

The shared instructions above are the single source of truth; this section adds only what
is specific to this runtime.

- A `PostToolUse` hook (`.claude/hooks/post-edit.py`) runs through `python3`, stamps
  `updated:` after you edit a note, and warns about unresolved links. It skips `50-journal`,
  `90-system`, and `99-attachments`. Do not also stamp `updated:` by hand — you would be
  duplicating it.
- `.claude/settings.json` pre-approves the `vault.py` commands. Invoke the script exactly
  as written in the shared instructions so the allow rules match. Both files need the
  folder to be trusted once before their rules and hooks take effect.
- Skills live in `90-system/skills` only. `.claude/skills/*/SKILL.md` are regular Markdown
  adapters with portable relative references to them, so the vault has one copy of every
  workflow and Obsidian's graph can see the canonical notes.
- Prefer `pack` over several `Read` calls when you need the substance of a topic rather
  than one specific note.
