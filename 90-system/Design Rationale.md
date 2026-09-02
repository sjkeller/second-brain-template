---
id: design-rationale
type: system
status: active
created: 2026-09-01
updated: 2026-09-02
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

## Why notes remain human-first

The first screen of a durable note carries its current answer, status, decision, or
takeaway. Stable headings make that information skimmable and reusable through Obsidian
heading embeds. Properties remain small because Obsidian does not render Markdown inside
text properties and because maintaining the same summary twice creates drift.

This also serves model retrieval without distorting the source material. Long-context
models do not use every position equally, and prompt-format experiments do not establish
one universal machine-optimal representation. The vault therefore keeps readable Markdown
canonical and generates narrow context packs when an agent needs them.

## Why Obsidian integration stays core-first

Embedded Bases answer operational questions from existing properties and links. A
contextual Base uses `file.hasLink(this.file)` rather than the documented performance-heavy
backlinks property. Official Web Clipper capture lands inside the immutable raw-source
boundary, and `obsidian-uri` only generates validated open/search links. Community plugins,
automatic GUI execution, and mutable URI actions remain outside the initial trust surface.

## Why AI drafts have two markers

`ai_review: pending` makes unreviewed material queryable; a visible warning callout protects
the reader who never opens Properties. The markers are removed together after review.
Evidence and uncertainty are shown instead of a persuasive model rationale because human-AI
research shows that explanations can increase acceptance even when a recommendation is
wrong.

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
- Obsidian embeds: https://help.obsidian.md/embeds
- Obsidian URI: https://help.obsidian.md/Extending+Obsidian/Obsidian+URI
- Obsidian Web Clipper: https://github.com/obsidianmd/obsidian-clipper
- Diataxis documentation framework: https://diataxis.fr/start-here/
- PARA: https://fortelabs.com/blog/para/
- Linking Your Thinking maps: https://blog.linkingyourthinking.com/maps/
- Claude Code hooks: https://code.claude.com/docs/en/hooks
- Claude Code settings and permissions: https://code.claude.com/docs/en/settings
- Claude Code memory and `@` imports: https://code.claude.com/docs/en/memory
- Claude Code skills: https://code.claude.com/docs/en/skills
- OpenAI skill guidance: https://learn.chatgpt.com/docs/build-skills
- Robertson & Zaragoza, *The Probabilistic Relevance Framework: BM25 and Beyond* (2009),
  for the fielded ranking used by `query`.
- Amershi et al., *Guidelines for Human-AI Interaction* (2019):
  https://doi.org/10.1145/3290605.3300233
- Bansal et al., *Does the Whole Exceed its Parts?* (2021):
  https://doi.org/10.1145/3411764.3445717
- Liu et al., *Lost in the Middle* (2024): https://aclanthology.org/2024.tacl-1.9/
- Dumais et al., *Stuff I've Seen* (2003):
  https://www.microsoft.com/en-us/research/publication/stuff-ive-seen-a-system-for-personal-information-retrieval-and-re-use/

Related: [[90-system/Link Policy|Link Policy]] · [[90-system/Vault Contract|Vault Contract]] · [[Home]]
