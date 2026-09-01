---
id: retrieval-guide
type: system
status: active
created: 2026-09-01
updated: 2026-09-01
tags:
  - system/agent
---

# Retrieval Guide

Do not ask a model to read the whole vault by default.

## Deterministic first pass

Examples use `python3` on the supported Windows and Linux hosts. Use `py` only as a
fallback on Windows installations that do not expose `python3`.

```text
python3 "90 System/Automation/vault.py" query "search terms" --limit 8 --compact
python3 "90 System/Automation/vault.py" pack "search terms" --budget-tokens 4000
python3 "90 System/Automation/vault.py" related "40 Knowledge/Concepts/Concept Name.md" --depth 2
```

`query` returns ranked paths, metadata, and short excerpts. `pack` returns one
budget-capped Markdown bundle — prefer it when you need the substance of a topic rather
than one specific note, because it replaces several `Read` calls with a single output.
Its token budget is a conservative four-characters-per-token estimate that works without a
model-specific tokenizer. Header, footer, and worst-case CRLF line endings count toward the
ceiling; the footer makes the approximation explicit.
`related` returns graph neighbours. Read full notes only after this narrowing step.

## Choosing the narrowing

- Known subject, need the note → `query`, then read the top hit.
- Broad topic, need the gist → `pack`.
- Need what connects to something → `related`.
- Need a list by property rather than by relevance → open a
  [[90 System/Bases/MOC - Bases|Base]]; it costs nothing at all.

Filter before widening the limit: `--type concept`, `--tag learning`, `--since 2026-01-01`
usually beat raising `--limit`. If a query returns nothing, try `--fuzzy` before rephrasing;
short prefixes already expand automatically.

## Retrieval order

1. Relevant MOC.
2. Highest-ranked canonical notes.
3. Direct source and decision links.
4. Recent journal or handoff notes only when recency matters.
5. Broader search only if evidence remains insufficient.

## Scale

Retrieval is lexical and local. It stays fast because parsing is incremental and queries
walk an inverted index rather than the whole vault; [[90 System/Automation/MOC - Automation|Automation]]
describes the mechanism. For semantic retrieval at larger scale, add a local embedding
index later, but keep lexical retrieval as the inspectable fallback. Never send the entire
private vault to a remote embedding service without explicit consent.

Related: [[90 System/Agent Orientation|Agent Orientation]] · [[90 System/Indexes/Vault Index|Vault Index]]
