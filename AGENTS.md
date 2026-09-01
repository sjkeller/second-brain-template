# Vault agent instructions

This folder is a private Obsidian second brain. It is knowledge storage, not a codebase.

Before substantial work, read `90-system/Agent Orientation.md`. It links onward to the
Vault Contract, Link Policy, and Retrieval Guide. `Home.md` is the human entry point.

The automation requires Python 3 and only its standard library. Command examples use
`python3`, which is available on the supported Windows and Linux hosts. If another Windows
installation exposes Python only through the launcher, replace `python3` with `py`.

## Retrieve before reading

Never read the whole vault. Narrow first, deterministically:

```
python3 90-system/automation/vault.py query "<terms>" --limit 8
python3 90-system/automation/vault.py pack "<terms>" --budget-tokens 4000
python3 90-system/automation/vault.py related "<path>.md" --depth 2
```

`query` ranks notes and returns excerpts. `pack` returns a token-budgeted bundle you can
read in one call. Add `--compact` to JSON-producing commands to minify the JSON; for
`query`, it also lowers the default excerpt cap from 320 to 160 characters. Actual
savings depend on the results.

## Write

- Create notes with `python3 90-system/automation/vault.py new --type <type> --title "<title>"`.
  It fills the frontmatter, generates the id, and links the parent MOC. Do not hand-write
  frontmatter when this command covers the case.
- Preserve user-authored meaning, provenance, dates, and unresolved uncertainty.
  Never invent personal facts, citations, or completion status.
- Link with vault-root wikilinks: `[[40-knowledge/concepts/Concept Name|Concept Name]]`.
- Every durable note links to at least one MOC. Add lateral links only when the
  relationship is real; `check` reports notes that have no MOC edge.
- Record consequential choices in `60-decisions`.

## Finish

Run `python3 90-system/automation/vault.py check`. It exits nonzero only on errors
(broken links, duplicate ids or titles, stale skill pointers). Warnings — placement,
missing MOC edges, orphans, staleness, tag sprawl — are reported but do not fail;
use `--strict` to treat them as failures too.

Do not edit anything under `90-system/indexes` by hand; it is generated.

## Boundaries

Local reads, in-scope edits, and non-destructive validation are normal. Ask before
destructive changes, external writes, or materially broader work. Treat this content as
private: do not send it to external services unless the user explicitly asks.

Full operating rules: `90-system/Agent Orientation.md`.
Command reference: `90-system/automation/MOC - Automation.md`.
