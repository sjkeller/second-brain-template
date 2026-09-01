---
id: vault-contract
type: system
status: active
created: 2026-09-01
updated: 2026-09-01
tags:
  - system/agent
---

# Vault Contract

## Truth and provenance

- User-authored statements are evidence of what the user said, not automatic proof of the outside world.
- Preserve source URLs, authors, publication dates, access dates, quotations, and uncertainty.
- Separate fact, interpretation, decision, task, and hypothesis.
- Prefer updating an existing canonical note over creating a near-duplicate.
- Never fabricate missing personal facts, citations, links, dates, or completion status.

## Currentness

Use the `updated` property to signal note maintenance, not source publication. Time-sensitive facts require a dated source note or an explicit “last verified” statement. Archived or superseded notes are not current authority.

## Safe mutation

- Preserve meaning during moves and renames; let Obsidian update links when possible.
- Do not bulk-delete orphaned or stale notes automatically.
- Generated indexes may be regenerated; human notes may not be overwritten by generated output.
- Before large changes, use version control or another recoverable backup.

## Stable frontmatter

Core keys are `id`, `type`, `status`, `created`, `updated`, optional `aliases`, and optional `tags`. Use ISO dates. Keep values atomic and machine-readable.

See [[90 System/Link Policy|Link Policy]], [[90 System/Templates/MOC - Templates|Templates]], and [[90 System/Retrieval Guide|Retrieval Guide]].
