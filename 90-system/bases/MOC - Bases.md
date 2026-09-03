---
id: moc-bases
type: moc
status: active
created: 2026-09-01
updated: 2026-09-02
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
- `Review.base` — due reviews, unreviewed AI drafts, and raw sources awaiting sealing.
- `Context.base` — notes that link to the note in which this Base is embedded.

Open them from the file explorer. They are YAML, not Markdown, so they do not appear in
the graph and are not indexed by [[90-system/automation/MOC - Automation|Automation]].

## Division of labour

Bases answers **what exists** by property. It filters, groups, and calculates simple view
conditions such as a due date. It does not replace the validator or retrieval engine.

[[90-system/automation/MOC - Automation|vault.py]] answers **what is wrong**: unresolved
links, duplicate ids, notes with no MOC edge, notes filed under the wrong type, staleness
measured against `updated`, and tag sprawl. Those need graph traversal and date
arithmetic, so they stay in the script where they are tested.

Prefer a Base when a human wants to look at a list. Prefer `vault.py` when an agent needs
a decision, or when the answer requires following links.

## Embedding

Embed a named view in an ordinary note:

```markdown
![[90-system/bases/Review.base#Review due]]
![[90-system/bases/Context.base#Linked notes]]
```

`Context.base` uses `file.hasLink(this.file)`. When embedded, `this.file` is the containing
note, so the view becomes a contextual reverse lookup without the performance-heavy
`file.backlinks` property. Open it through an embedding note rather than as a standalone
dashboard.

## Compatibility

These files use documented Bases constructs: recursive filters, `file.inFolder()`,
`file.hasLink()`, `today()`, property comparison, `groupBy`, property display names, and
named views. Bases has changed its file format before, so if a view stops loading, check
the current syntax reference rather than assuming the data is wrong. Nothing else in this
vault depends on these files.

Related: [[90-system/MOC - System|System]] · [[90-system/Obsidian Setup|Obsidian Setup]] · [[Home]]
