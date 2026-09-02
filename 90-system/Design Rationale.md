---
id: design-rationale
type: system
status: active
created: 2026-09-01
updated: 2026-09-01
tags:
  - system/design
---

# Design Rationale

This vault combines three complementary patterns:

- PARA supplies shallow action-oriented storage: [[10-projects/MOC - Projects|Projects]],
  [[20-areas/MOC - Areas|Areas]], [[30-resources/MOC - Resources|Resources]], and
  [[80-archive/MOC - Archive|Archive]].
- Maps of Content provide human-curated graph hubs because Obsidian visualizes explicit
  links rather than folders.
- Atomic knowledge and entity notes provide a stable layer that survives project moves.

For agent efficiency, the root instructions are intentionally small. Detailed workflows
live in [[90-system/skills/MOC - Skills|Skills]], repeatable mechanics live in
[[90-system/automation/MOC - Automation|scripts]], and retrieval begins with compact
indexes rather than a whole-vault read.

## Why not one universal hierarchy?

A folder answers “where is this file now?” A link answers “how is this idea related?” A
property answers “what kind of record is this?” Keeping those roles separate makes the
system easier to navigate and easier to validate.

## Why machine-checkable structural rules become checks

A structural rule that only exists in prose is easy to forget as the vault grows. The
machine-checkable rules therefore have matching checks in `vault.py`: resolvable note and
attachment links, unique ids and titles, MOC coverage, type-to-folder placement, bounded tag
vocabulary, freshness of active notes, and portable skill adapters. Principles that require
judgement — source quality, factual accuracy, meaningful relationships, or whether a note
is truly atomic — remain review responsibilities and are not presented as automated checks.

`check` separates errors from warnings for the same reason. If a check fails on ordinary
housekeeping, people learn to ignore it. Only genuine breakage — broken links, duplicate
ids, a skill pointer aimed at nothing — fails the command.

## Why duplication is avoided rather than synchronised

Every skill body exists once, under `90-system/skills`. The files in `.claude/skills` and
`.agents/skills` are small relative-path adapters, and `CLAUDE.md` imports `AGENTS.md`
instead of restating it. `check` verifies each adapter's target, name, and trigger
description. Regular text adapters were chosen over symlinks so the synchronized vault
behaves consistently on Windows and Linux.

## Why retrieval is lexical and cached

Ranking is BM25F over an inverted index, with parsing cached incrementally against file
mtime and size. This keeps retrieval inspectable — you can read why a note ranked where it
did — and keeps it local, so no private note is sent anywhere to be embedded. It also stays
fast as the vault grows, because queries touch posting lists rather than every file.
Semantic search can be layered on later only when the human-judged evidence gate in
[[90-system/Retrieval Evaluation|Retrieval Evaluation]] identifies a material lexical gap.
The template's fictional examples do not meet that gate, so no semantic engine or embedding
dependency is installed. Lexical retrieval remains the fallback that always works and
always explains itself.

## Research basis

- Obsidian Help: https://obsidian.md/help/plugins/graph
- Obsidian internal links: https://obsidian.md/help/links
- Obsidian properties: https://obsidian.md/help/properties
- Obsidian Bases syntax: https://obsidian.md/help/bases/syntax
- PARA: https://fortelabs.com/blog/para/
- Linking Your Thinking maps: https://blog.linkingyourthinking.com/maps/
- Claude Code hooks: https://code.claude.com/docs/en/hooks
- Claude Code settings and permissions: https://code.claude.com/docs/en/settings
- Claude Code memory and `@` imports: https://code.claude.com/docs/en/memory
- Claude Code skills: https://code.claude.com/docs/en/skills
- OpenAI skill guidance: https://learn.chatgpt.com/docs/build-skills
- Robertson & Zaragoza, *The Probabilistic Relevance Framework: BM25 and Beyond* (2009),
  for the fielded ranking used by `query`.

Related: [[90-system/Link Policy|Link Policy]] · [[90-system/Vault Contract|Vault Contract]] · [[Home]]
