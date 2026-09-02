---
id: writing-and-documentation-guide
type: system
status: active
created: 2026-09-02
updated: 2026-09-02
tags:
  - system/writing
  - system/documentation
---

# Writing and Documentation Guide

Write for a person returning later with limited context. The durable Markdown body is the
canonical explanation; properties support filtering and validation but do not replace it.

## First-screen contract

1. Use a specific H1 containing words a person would search for.
2. Keep the parent MOC link near the top.
3. State the current answer, status, decision, or takeaway before history and detail.
4. Separate evidence, interpretation, uncertainty, and next action.

For a durable note longer than roughly 250 words, use an early `Summary`, `Current status`,
`Decision`, `Takeaway`, or equivalent type-specific section. Short notes need not repeat
their entire content in a summary.

Use a short abstract callout when it improves scanning:

```markdown
> [!abstract] Summary
> State the current answer in one to three sentences or a few concise bullets.
```

The summary in the body is authoritative. Do not maintain a second full summary in a text
property. If a future Base genuinely needs a navigation label, define a separate short
property with a distinct purpose.

## Stable headings by note type

| Type | Put near the top | Supporting sections |
| --- | --- | --- |
| Project | `Current status`, `Outcome`, `Next actions` | `Waiting for`, `Constraints and risks`, `Evidence and decisions`, `Completion` |
| Area | `At a glance`, `Responsibility` | `Desired standard`, `Current attention`, `Review cadence`, `Active projects`, `Risks and open loops` |
| Decision | `Decision` | `Context`, `Alternatives considered`, `Evidence`, `Consequences`, `Review trigger` |
| Source | `Takeaway` | `Source identity`, `Evidence`, `Interpretation`, `Supports or challenges`, `Reliability and limitations` |
| Concept | `Summary` | `Explanation`, `Why it matters`, `Evidence`, `Connections`, `Open questions` |
| Person or organization | `At a glance` | factual context, dated interactions, provenance, connections, open questions |
| Resource | `At a glance` | boundary, return condition, material, promoted knowledge, open questions |

Do not create empty sections forever. Delete an optional heading when it does not apply;
retain the early answer/status section and the evidence boundary where relevant.

## Language

- Prefer concrete nouns, active verbs, explicit dates, and short paragraphs.
- Define an abbreviation on first use unless it is part of the note title and universally
  understood in its context.
- Use descriptive link aliases in sentences. Avoid unexplained `Related` lists or aliases
  such as “here”.
- Preserve the user's terminology and voice. Do not rewrite durable notes into compressed
  “AI language”, JSON, or YAML prose.
- Put important qualifications beside the claim they qualify, not in a distant appendix.
- Split a note when its subjects need independent reuse, review, or lifecycle. Do not split
  a coherent explanation merely to satisfy an arbitrary atomic-note rule.

## Callouts

Keep the vocabulary small and predictable:

- `[!abstract]` — the current summary or takeaway.
- `[!warning]` — unverified, unsafe, or unreviewed AI material.
- `[!question]` — an unresolved issue.
- `[!quote]` — attributed source evidence.
- `[!info]-` — secondary detail that may start folded.

Callouts are presentation, not evidence. A warning must not replace provenance, and a quote
must still identify its source and location.

## Reuse without duplication

Use heading embeds when the same maintained section must appear elsewhere:

```markdown
![[10-projects/Example#Current status]]
![[60-decisions/Example decision#Decision]]
```

Prefer heading embeds to block references for durable cross-note reuse. A copied summary
will drift; an embed keeps one authoritative section. Do not embed a large note when one
heading answers the reader's question.

## System documentation

Classify system documentation by the need it serves:

- **Tutorial** — a safe, guided learning sequence.
- **How-to** — steps for completing a concrete task.
- **Reference** — precise rules, schemas, and command behavior.
- **Explanation** — rationale, trade-offs, and background.

Do not overload a how-to with long rationale. Link to an explanation instead. Do not hide
required operational steps inside a design essay.

## Human and agent retrieval

Stable headings and early answers improve navigation for people and make deterministic
context packs more useful. Keep critical evidence close to the claim. Let
[[90-system/automation/MOC - Automation|vault.py]] select a small context pack rather than
preparing an unnatural model-specific version of every note.

Run the warning-only readability report during reviews:

```text
python3 90-system/automation/vault.py readability
```

Warnings identify places to inspect; they never prove that prose is good or bad.

## Research basis

- Obsidian Properties: https://help.obsidian.md/properties
- Obsidian internal links and embeds: https://help.obsidian.md/links
- Obsidian callouts: https://help.obsidian.md/callouts
- Diataxis documentation framework: https://diataxis.fr/start-here/
- Liu et al., *Lost in the Middle* (2024): https://aclanthology.org/2024.tacl-1.9/
- He et al., prompt-format sensitivity (2024): https://arxiv.org/abs/2411.10541

These sources inform the conventions; they do not empirically validate this particular
vault. Measure real retrieval and human tasks through
[[90-system/Human Usability Evaluation|Human Usability Evaluation]].

Related: [[90-system/Vault Contract|Vault Contract]] · [[90-system/AI Collaboration Policy|AI Collaboration Policy]] · [[Home]]
