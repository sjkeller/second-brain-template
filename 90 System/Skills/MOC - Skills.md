---
id: moc-skills
type: moc
status: active
created: 2026-09-01
updated: 2026-09-01
tags:
  - system/moc
  - system/skills
---

# Skills

Skills are reusable, progressively disclosed workflows. Their descriptions should make triggering precise; their main instructions should stay short; conditional detail belongs in references; deterministic mechanics belong in scripts.

## Canonical skills

<!-- vault:links — machine insertion point; `vault.py new` adds links below this line. -->
- [[90 System/Skills/vault-capture/SKILL|Vault Capture]] — get material in without deciding its home.
- [[90 System/Skills/vault-triage/SKILL|Vault Triage]] — clarify, file, and link the Inbox.
- [[90 System/Skills/vault-review/SKILL|Vault Review]] — the weekly pass over the whole vault.
- [[90 System/Skills/vault-maintenance/SKILL|Vault Maintenance]] — retrieval, linking, and health.
- [[90 System/Skills/vault-maintenance/references/schema|Vault skill schema]]
- [[90 System/Skills/_template/SKILL|Skill Template]]

## One copy, two runtimes

Every skill body lives here and nowhere else. `.claude/skills/<name>/SKILL.md` and
`.agents/skills/<name>/SKILL.md` are regular Markdown adapters. Each uses the relative path
`../../../90 System/Skills/<name>/SKILL.md` to tell Claude Code or Codex to read the
canonical file. Regular files were chosen instead of symbolic links because they survive a
synchronised Windows-to-Linux vault without depending on filesystem or sync-client link
semantics. This keeps workflows unduplicated and their canonical notes visible in
Obsidian's graph, which normally ignores dot-folders.

`python3 "90 System/Automation/vault.py" check` verifies every adapter's exact relative
target, target existence, directory name, declared `name`,
and trigger `description`. It also
rejects absolute and vault-root-relative targets. Regenerate an adapter by copying the
canonical `name` and `description`, then restore its runtime-specific relative reference.

Validate a new skill with the applicable creator/validator before activating it. Do not install a skill merely because it exists; inspect its instructions, scripts, network behavior, and license first.

Related: [[90 System/MOC - System|System]] · [[90 System/Automation/MOC - Automation|Automation]] · [[90 System/Design Rationale|Design Rationale]]
