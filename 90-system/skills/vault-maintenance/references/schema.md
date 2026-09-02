# Vault schema

Read this only when creating, moving, or validating notes.

## Core properties

- `id`: stable lowercase kebab-case identifier; never reuse.
- `type`: one of `moc`, `project`, `area`, `resource`, `source`, `raw-source`, `concept`,
  `person`, `organization`, `journal`, `review`, `decision`, `note`, or `system`.
- `status`: normally `draft`, `active`, `accepted`, `ready`, `superseded`, or `archived`.
- `created` and `updated`: ISO `YYYY-MM-DD`.
- `aliases` and `tags`: optional lists.

Add domain properties only when they will be queried or validated. Keep values atomic; put
explanation in the body.

`vault.py check` verifies that the five core keys are present and that `type` is known.
Prefer `vault.py new` over writing frontmatter by hand — it fills all of this correctly.

## Placement

Each type has a home folder, and `check` reports notes that sit outside it:

| Type | Folder |
| --- | --- |
| `project` | `10-projects` |
| `area` | `20-areas` |
| `resource` | `30-resources` |
| `source` | `30-resources/sources` |
| `raw-source` | `30-resources/sources/raw` |
| `concept` | `40-knowledge/concepts` |
| `person` | `40-knowledge/people` |
| `organization` | `40-knowledge/organizations` |
| `journal` | `50-journal/daily` |
| `review` | `50-journal/weekly` |
| `decision` | `60-decisions` |
| `system` | `90-system` |

`note` and `moc` are unconstrained: `note` is the catch-all capture type, and a MOC lives
inside the folder it indexes. Notes under `00-inbox` are exempt because they are not filed
yet, and notes under `80-archive` keep the type they had when they were archived.

Unclear destination → `00-inbox`. Inactive material → `80-archive`. Operating metadata →
`90-system`.

`raw-source` notes begin as drafts. Their verbatim payload is bounded by fixed sentinels and
becomes immutable when `vault.py source-seal` records its SHA-256 digest. Metadata and
derived-note links outside the payload may still change. See [[90-system/Source Trust Policy]].

## Linking

Use root-relative wikilinks with paths and readable aliases. Every durable note needs a
parent MOC edge — `check` reports notes that have none, which is the failure that quietly
degrades the graph. Sources support claims; decisions affect work; projects belong to
areas. Do not use tags as a substitute for semantic links, and keep the tag vocabulary
small: `check` warns when it sprawls, and `vault.py tags` shows the inventory.

## MOC anchors

Every MOC that receives notes contains a line holding `vault:links`. `vault.py new`
inserts the link to a new note directly below it. A MOC without that anchor is never
modified automatically.
