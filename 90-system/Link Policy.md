---
id: link-policy
type: system
status: active
created: 2026-09-01
updated: 2026-09-01
tags:
  - system/graph
---

# Link Policy

Obsidian's graph shows links, not folder containment. Folder index notes therefore act as visible hubs.

## Required edges

- Every durable note links upward to at least one MOC.
- Projects link to their area, relevant knowledge/resources, and decisions.
- Source notes link to the claims or entity notes they support.
- Decisions link to affected work, evidence, and any superseding decision.
- Journal notes link to the entities and work they mention when useful.

## Useful lateral edges

Add a link when it answers one of these questions: “supports what?”, “contradicts what?”, “depends on what?”, “is an example of what?”, or “changed because of what?” Explain non-obvious relationships in prose instead of creating unexplained link lists.

## Link format

Use vault-root paths for machine-authored links: `[[40-knowledge/concepts/Concept Name|Concept Name]]`. This avoids ambiguous filenames while keeping readable display text. Avoid duplicate filenames for canonical notes.

Tags classify and filter; links express relationships. Keep tag vocabularies small. Do not create links merely to make the global graph denser.

## Graph use

Use the local graph at depth 1–2 for navigation. In the global graph, group by `path:` for the numbered top-level folders and hide templates or attachments when they add noise.

Related: [[Home]] · [[90-system/Design Rationale|Design Rationale]] · [[90-system/automation/MOC - Automation|Automation]]
