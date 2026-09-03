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

## Typed relations

When the relationship itself must be queryable, use one of these optional flat frontmatter
lists. Values are root-relative wikilinks; an edge is a factual claim and must not be guessed.

| Field | Inverse | Meaning |
| --- | --- | --- |
| `supersedes` | `superseded_by` | this note replaces an earlier note or decision |
| `depends_on` | `required_by` | this note requires the target |
| `supports` | `supported_by` | this source or evidence supports the target |
| `contradicts` | `contradicts` | the two notes contain a real unresolved conflict |

```yaml
depends_on:
  - "[[40-knowledge/concepts/Example|Example]]"
supports: []
```

`vault.py check` fails on malformed, dangling, self-referential, or cyclic supersession
relations and warns when the inverse declaration is missing. Add both directions when the
relationship is worth typing; ordinary prose links remain valid and need no inverse field.

## Redirects

A retired path uses `type: redirect`, `status: superseded`, and exactly one quoted
`redirect_to: '[[root-relative/canonical|Canonical]]'` value. Redirects preserve old
backlinks; they are not ordinary typed relations and do not need a parent MOC. Create them
only with the guarded command in [[90-system/Safe Merge Policy|Safe Merge Policy]]. The
checker rejects missing targets, self-links, chains, and cycles.

## Link format

Use vault-root paths for machine-authored links: `[[40-knowledge/concepts/Concept Name|Concept Name]]`. This avoids ambiguous filenames while keeping readable display text. Avoid duplicate filenames for canonical notes.

Tags classify and filter; links express relationships. Keep tag vocabularies small. Do not create links merely to make the global graph denser.

## Graph use

Use the local graph at depth 1–2 for navigation. In the global graph, group by `path:` for the numbered top-level folders and hide templates or attachments when they add noise.

Related: [[Home]] · [[90-system/Design Rationale|Design Rationale]] · [[90-system/automation/MOC - Automation|Automation]]
