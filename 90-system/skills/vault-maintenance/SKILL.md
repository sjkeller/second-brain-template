---
name: vault-maintenance
description: Retrieve and diagnose an existing Obsidian second-brain vault. Use for BM25F lookup, context packs, graph navigation, indexing, task/tag/staleness reports, broken-link checks, or vault health diagnostics. Not for new capture, Inbox filing, or weekly review; use the focused vault skills.
---

# Vault Maintenance

Use `python3` in the commands below; `py` is the fallback for Windows installations that
do not expose that executable name.

Operate from the vault root. Every command below is deterministic: it costs no reasoning,
so call it instead of inferring the answer.

## Retrieve

```
python3 90-system/automation/vault.py query "<terms>" --limit 8 --compact
python3 90-system/automation/vault.py query "<terms>" --type concept --tag learning --since 2026-01-01
python3 90-system/automation/vault.py pack "<terms>" --budget-tokens 4000
python3 90-system/automation/vault.py related "<path>.md" --depth 2
```

`query` ranks with BM25F and falls back to prefix expansion; add `--fuzzy` for typos.
`pack` returns one token-budgeted bundle instead of several reads. See
[[90-system/Retrieval Guide]] for when to use which.

When changing retrieval behavior, use the ignored human-judged cases described in
[[90-system/Retrieval Evaluation]] and run `vault.py eval-retrieval`. Do not recommend or
enable semantic retrieval from anecdotes; apply the documented evidence gate.

## Maintain existing notes

Preserve meaning and provenance when repairing links, metadata, or MOC membership. Read
[[90-system/Vault Contract]] and [[90-system/Link Policy]]. When frontmatter or placement
is material, also read [references/schema.md](references/schema.md). Add only meaningful
lateral links. Hand new captures to `vault-capture`, Inbox filing to `vault-triage`, and
periodic review to `vault-review`.

For current facts, also read [[90-system/Freshness Policy]]. Treat freshness findings as
review prompts: re-verify, convert to a truth pointer, or preserve the value in a dated
snapshot. Typed-link inverse warnings require judgement; never invent an inverse merely to
silence the checker.

## Report

```
python3 90-system/automation/vault.py tasks --state open --compact
python3 90-system/automation/vault.py stale --days 180 --compact
python3 90-system/automation/vault.py tags --compact
```

## Validate

```
python3 90-system/automation/vault.py index
python3 90-system/automation/vault.py check
```

`check` separates errors from warnings and exits nonzero only on errors. Fix broken links,
duplicate ids or titles, and stale skill pointers first. Placement, MOC-coverage, orphan,
staleness, and tag warnings are judgement calls — report them, do not silently "fix" them.
Do not delete or merge notes automatically.

For interrupted multi-session work, update [[90-system/AI Handoff]] with confirmed state
and the next safe action.
