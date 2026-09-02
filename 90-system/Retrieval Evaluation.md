---
id: retrieval-evaluation
type: system
status: active
created: 2026-09-02
updated: 2026-09-02
tags:
  - system/agent
  - system/retrieval
---

# Retrieval Evaluation

Retrieval changes need measured evidence from this vault. The evaluation harness calls the
same BM25F `rank` function as `query`; it is not a simplified test-only scorer.

## Private case set

Copy `90-system/evals/retrieval-cases.example.jsonl` to the ignored default path
`90-system/evals/retrieval-cases.jsonl`. Keep one JSON object per line:

```json
{"id":"find-link-policy","query":"how are relationships checked","expected":"90-system/Link Policy.md","category":"known-item"}
```

- `query` and `expected` are required. `expected` may be one path or a list of relevant
  Markdown paths.
- `id` and `category` are recommended. IDs, rather than queries, appear in result details.
- Optional `type` and `tags` fields accept either one string or a string list and exercise
  the same filters as normal retrieval.
- Use questions and vocabulary that actually occur during work. Include known-item,
  topical, paraphrase, acronym, multilingual, and filtered queries where those patterns
  matter. Do not manufacture easy cases from note titles alone.

Both the real case set and generated reports are ignored by Git because even a query can
reveal private interests. The tracked example is fictional template data.

## Run the baseline

```text
python3 90-system/automation/vault.py eval-retrieval --compact
python3 90-system/automation/vault.py eval-retrieval --k 1,3,5,10 --report 90-system/evals/retrieval-report.json
python3 90-system/automation/vault.py eval-retrieval --fail-below-recall 0.85
```

The report contains macro recall at each requested cutoff, mean reciprocal rank (MRR),
per-category metrics, expected paths, ranks, and returned paths. It deliberately omits the
query text. `--fail-below-recall` applies to the largest requested cutoff and returns exit
code 1 when the target is missed; malformed cases return 2. Add `--fuzzy` only when typo
tolerance is part of the behavior being evaluated. Request `k=5` to obtain a meaningful
`semantic_gate`; without it, the gate reports insufficient evidence.

## Semantic-retrieval gate

Keep lexical retrieval as the default. Optional local embeddings are justified only after:

1. at least 20 representative, human-judged cases have been recorded;
2. obvious metadata, alias, link, filtering, and query-vocabulary problems have been fixed;
3. lexical recall@5 remains below 0.85 overall, or a material category with at least five
   cases remains below 0.75; and
4. a second run shows that hybrid retrieval materially improves the weak cases without
   unacceptable regressions, latency, or local storage growth.

The gate is evidence for trying a local semantic index, not permission to send vault text
to a remote service. Record the before/after report paths and decision in a
[[60-decisions/MOC - Decisions|decision note]].

`eval-retrieval` applies these numeric criteria in its `semantic_gate` output. It never
enables or installs a semantic engine. The tracked two-case example is schema documentation,
not representative evidence, so it must always leave semantic retrieval disabled.

Related: [[90-system/Retrieval Guide|Retrieval Guide]] · [[90-system/automation/MOC - Automation|Automation]] · [[90-system/Source Trust Policy|Source Trust Policy]]
