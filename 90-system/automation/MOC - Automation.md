---
id: moc-automation
type: moc
status: active
created: 2026-09-01
updated: 2026-09-01
tags:
  - system/moc
  - system/automation
---

# Automation

`vault.py` uses only Python's standard library. It moves repeatable parsing, retrieval,
graph, and validation mechanics out of model reasoning. Add `--compact` to JSON-producing
commands to minify JSON; for `query`, it also lowers the default excerpt cap from 320 to
160 characters. Savings depend on the returned material.

Examples use `python3`, available on the supported Windows and Linux hosts. On another
Windows installation that exposes Python only through its launcher, use `py` instead.

## Retrieve

- `python3 90-system/automation/vault.py query "terms" --limit 8` — BM25F ranking with
  excerpts. Filters: `--type`, `--tag`, `--since YYYY-MM-DD`. Add `--fuzzy` for typos.
- `python3 90-system/automation/vault.py pack "terms" --budget-tokens 4000` — one
  Markdown bundle instead of several reads. The complete output stays under a conservative
  four-characters-per-token ceiling, including worst-case CRLF line endings; the footer
  reports the estimate.
- `python3 90-system/automation/vault.py related "path.md" --depth 2` — resolved wikilink
  neighbours.

## Author

- `... new --type concept --title "Name" --tags "a,b"` — renders the template, generates
  the id, stamps the dates, and links the parent MOC under its `vault:links` anchor.
  `--dry-run` prints the note without writing it.
- `... touch "path.md"` — stamp `updated`. `--only-durable` makes it a no-op for raw-source
  payloads, Journal, System, and Attachments, which is how the edit hook uses it.
- `... source-seal "30-resources/sources/raw/<note>.md"` — hash the delimited payload and
  change a draft raw source to `status: immutable`. Add `--verify` for a read-only check.

## Report

- `... tasks --state open` — every checkbox in the vault, with source and line.
- `... stale --days 180` — notes whose `updated` has aged out.
- `... tags` — the tag inventory, with single-use tags called out.
- `... index` — writes [[90-system/indexes/Vault Index|Vault Index]] and its JSON twin.

## Validate

- `... check` — separates **errors** from **warnings** and exits nonzero only on errors.
  - Errors: unresolved note or attachment links, duplicate ids, duplicate titles, broken
    or drifted skill pointers, and changed or structurally invalid sealed raw-source payloads.
  - Warnings: missing frontmatter keys, type/folder placement, notes with no MOC edge,
    orphans, staleness, tag sprawl, and raw sources that have not been sealed yet.
  - `--strict` fails on warnings too; `--quiet` prints the summary and errors only.
- `... cache` / `cache --rebuild` — inspect or discard the retrieval cache.
- `python3 -m unittest discover -s 90-system/automation/tests` — the test suite.

## How retrieval stays fast

Four choices matter more than the rest, and they compound:

1. **Incremental parsing.** Parsed notes live in a SQLite cache keyed by `(mtime, size)`.
   A warm command re-reads only what changed, so it costs one `stat` per note instead of a
   read plus a tokenise.
2. **An inverted index.** Queries walk posting lists for the query's terms rather than
   scanning every note, so cost scales with how rare the term is, not with vault size.
3. **On-demand bodies.** The cache stores parsed metadata, graph data, hashes, field
   lengths, and term postings, but not note bodies. Only shortlisted results are read from
   disk for excerpts or packs.
4. **BM25F ranking.** Title, frontmatter, and body are normalised by their own field
   lengths and then saturated once. This is what keeps a one-line stub from outranking a
   thorough note simply for being short.

Prefix expansion uses a range scan over the index. `--fuzzy` probes a trigram table first
and only then computes edit similarity on the shortlist, which avoids scanning the whole
vocabulary. Dynamic pruning such as WAND was considered and deliberately left out: it pays
off at millions of documents and would add complexity a personal vault never recovers.

No fixed latency or size-reduction claim is part of the contract. Benchmark representative
queries on the actual Windows and Linux vault before tuning these choices.

These commands are local preprocessing. They do not call an AI service or transmit vault
content. The disposable cache remains out of version control because it is generated local
state, not because it contains full note bodies.

Related: [[90-system/Retrieval Guide|Retrieval Guide]] · [[90-system/skills/MOC - Skills|Skills]] · [[90-system/bases/MOC - Bases|Bases]] · [[90-system/MOC - System|System]]
