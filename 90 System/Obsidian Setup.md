---
id: obsidian-setup
type: system
status: active
created: 2026-09-01
updated: 2026-09-01
tags:
  - system/obsidian
---

# Obsidian Setup

Open “private-second-brain” itself as an Obsidian vault. It has no `.obsidian` folder yet,
so the settings below are the manual step that turns the skeleton into a working vault.

## Files and links

- Enable automatic internal-link updates.
- Set new-link format to “Absolute path in vault” for unambiguous agent-authored links.
- Set the attachment folder to “99 Attachments”.
- Set the Templates core plugin folder to “90 System/Templates”.

## Useful core plugins

Enable Graph view, Backlinks, Outgoing links, Properties view, Templates, and Daily notes
if you use the journal. Enable Bases to use the dashboards in
[[90 System/Bases/MOC - Bases|Bases]].

## Graph view

Turn on arrows when direction matters. Use local graph depth 1–2 for navigation. Suggested
global graph color groups:

- path:"10 Projects"
- path:"20 Areas"
- path:"30 Resources"
- path:"40 Knowledge"
- path:"50 Journal"
- path:"60 Decisions"
- path:"90 System"

For a quieter knowledge graph, filter out path:"90 System/Templates" and
path:"99 Attachments". Keep MOCs visible because they are the graph representation of
folder membership.

## What Obsidian ignores

Obsidian ignores dot-folders, so the runtime adapters in “.agents” and “.claude” do not
appear in the graph. They are regular Markdown files with relative references, not
symbolic links. Every skill body lives once under [[90 System/Skills/MOC - Skills|Skills]],
where it stays graph-visible. This design is portable when the vault is synchronised
between Windows and a Linux VPS; `vault.py check` detects adapter drift.

`.base` files are YAML rather than Markdown, so they show in the file explorer but not in
the graph. The retrieval cache at `90 System/Indexes/.vault-cache.sqlite3` is a dotfile for
the same reason — it is disposable and rebuilt on demand.

## Claude Code

`.claude/settings.json` pre-approves the `vault.py` commands and installs a `PostToolUse`
hook that stamps `updated:` and reports unresolved links after an edit. It invokes
`python3`, available on the supported Windows and Linux hosts. Claude Code asks you to
trust this folder once before either takes effect; until then you will still see permission
prompts and the hook will not run.

Related: [[90 System/Link Policy|Link Policy]] · [[90 System/Design Rationale|Design Rationale]] · [[Home]]
