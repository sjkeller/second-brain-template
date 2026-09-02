---
id: obsidian-setup
type: system
status: active
created: 2026-09-01
updated: 2026-09-02
tags:
  - system/obsidian
---

# Obsidian Setup

Open the cloned vault folder itself, for example `private-second-brain`, as an Obsidian
vault. The portable defaults in `.obsidian` are version-controlled by the template and
work on Windows, Linux, and macOS. If the vault was already open when those files changed,
reload or restart Obsidian once.

Last verified against the official documentation and Obsidian Desktop 1.13.7 on
2026-09-02.

## Files and links

- New notes go to `00-inbox`.
- New attachments go to `99-attachments`.
- New internal links use Wikilinks with absolute vault paths for unambiguous agent-authored
  links.
- Obsidian automatically updates internal links when a note is renamed.
- All supported file types are visible, including the automation and skill-support files.

## Useful core plugins

The shared profile enables Graph view, Backlinks, Outgoing links, Properties view,
Templates, Daily notes, Bases, Search, File explorer, Quick switcher, Outline, Page
preview, Bookmarks, Command palette, Note composer, Word count, and File recovery.

Templates use `90-system/templates`. Daily notes use `50-journal/daily`, the
`YYYY-MM-DD` filename format, and
[[90-system/templates/Daily Note Template|Daily Note Template]]. The Properties view
treats `created` and `updated` as dates and keeps `id`, `type`, and `status` as text.

No community plugin is installed or enabled. Canvas, Publish, Sync, Workspaces, Slides,
and other nonessential core plugins remain disabled in the template; enable them locally
when you deliberately need them. The [[90-system/bases/MOC - Bases|Bases]] dashboards use
the supported core Bases plugin and need no community dependency.

The safe capture and URI bridge is documented in
[[90-system/Obsidian Integration|Obsidian Integration]]. It includes an importable official
Web Clipper template but does not install a browser extension, launch Obsidian, or enable a
remote model interpreter.

## Graph view

The global graph starts with arrows enabled, only existing files, orphans visible, and
attachment and tag nodes hidden. It filters out `90-system/templates` and the generated
`90-system/indexes` files. Orphans remain visible intentionally: a disconnected note is a
quality signal rather than something the default view should conceal.

The color groups are mutually exclusive, so their result does not depend on overlap or
group precedence:

- `[type:moc]` — gold navigation hubs.
- `path:"90-system/skills" -[type:moc]` — teal agent skills.
- `path:"00-inbox" -[type:moc]` — orange unprocessed notes.
- `path:"10-projects" -[type:moc]` — blue projects.
- `path:"20-areas" -[type:moc]` — green areas.
- `path:"30-resources" -[type:moc]` — cyan resources and sources.
- `path:"40-knowledge" -[type:moc]` — purple durable knowledge.
- `path:"50-journal" -[type:moc]` — slate journal entries.
- `path:"60-decisions" -[type:moc]` — red decisions.
- `path:"80-archive" -[type:moc]` — gray archived material.
- `path:"90-system" -path:"90-system/skills" -[type:moc]` — muted system material.

Groups color matching notes; they do not create graph edges or hard cluster boundaries.
Only internal Markdown links create edges. MOCs therefore remain visible as the semantic
representation of hierarchy and membership, while the graph forces place strongly linked
notes near one another. Use a local graph depth of 1–2 for focused navigation; local graph
depth is workspace state and is intentionally not forced by the template.

The graph display and group definitions are shared defaults, so changes made in Graph view
can update `.obsidian/graph.json`. Commit intentional improvements to the template; keep
purely personal layout changes out of it.

## Shared and local configuration

The portable files committed under `.obsidian` are application settings, core-plugin
selection, graph groups, Templates and Daily Notes locations, and property types.
`.obsidian/workspace*.json` remains ignored because it contains frequently changing open
tabs, pane layouts, and recent file state. Hotkeys, appearance, bookmarks, account and Sync
configuration, installed community plugins, and community themes are also ignored and left
to each user and device. A future shared CSS snippet may still be committed deliberately
under `.obsidian/snippets`.

## What Obsidian ignores

Obsidian ignores dot-folders, so the runtime adapters in “.agents” and “.claude” do not
appear in the graph. They are regular Markdown files with relative references, not
symbolic links. Every skill body lives once under [[90-system/skills/MOC - Skills|Skills]],
where it stays graph-visible. This design is portable when the vault is synchronised
between Windows and a Linux VPS; `vault.py check` detects adapter drift.

`.base` files are YAML rather than Markdown, so they show in the file explorer but not in
the graph. The retrieval cache at `90-system/indexes/.vault-cache.sqlite3` is a dotfile for
the same reason — it is disposable and rebuilt on demand.

## Claude Code

`.claude/settings.json` pre-approves the `vault.py` commands and installs a `PostToolUse`
hook that stamps `updated:` and reports unresolved links after an edit. It invokes
`python3`, available on the supported Windows and Linux hosts. Claude Code asks you to
trust this folder once before either takes effect; until then you will still see permission
prompts and the hook will not run.

Related: [[90-system/Link Policy|Link Policy]] · [[90-system/Design Rationale|Design Rationale]] · [[Home]]
