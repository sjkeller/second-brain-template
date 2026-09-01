---
id: moc-bases
type: moc
status: active
created: 2026-09-01
updated: 2026-09-01
tags:
  - system/moc
  - system/bases
---

# Bases

Bases is Obsidian's built-in, property-driven table view. These `.base` files render
dashboards from the frontmatter the templates already write, so routine questions —
what is active, what is still a draft, what is waiting in the Inbox — are answered by
opening a file instead of by asking a model.

## Files

- `Active Work.base` — projects and areas, active first.
- `Knowledge.base` — concepts, people and organizations, and everything still a draft.
- `Triage.base` — Inbox captures and drafts anywhere in the vault.

Open them from the file explorer. They are YAML, not Markdown, so they do not appear in
the graph and are not indexed by [[90 System/Automation/MOC - Automation|Automation]].

## Division of labour

Bases answers **what exists** by property. It filters and groups; it does not compute.

[[90 System/Automation/MOC - Automation|vault.py]] answers **what is wrong**: unresolved
links, duplicate ids, notes with no MOC edge, notes filed under the wrong type, staleness
measured against `updated`, and tag sprawl. Those need graph traversal and date
arithmetic, so they stay in the script where they are tested.

Prefer a Base when a human wants to look at a list. Prefer `vault.py` when an agent needs
a decision, or when the answer requires following links.

## Compatibility

These files use only constructs from Obsidian's documented Bases example: `filters` with
`and`/`or`, `file.inFolder()`, property comparison, `properties` display names, and
`views` with `type`, `name`, `filters`, and `order`. Bases has changed its file format
before, so if a view stops loading, check the current syntax reference rather than
assuming the data is wrong. Nothing else in this vault depends on these files.

Related: [[90 System/MOC - System|System]] · [[90 System/Obsidian Setup|Obsidian Setup]] · [[Home]]
