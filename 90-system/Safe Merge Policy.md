---
id: safe-merge-policy
type: system
status: active
created: 2026-09-02
updated: 2026-09-02
tags:
  - system/agent
  - system/safety
---

# Safe Merge Policy

A merge changes identity and can silently discard provenance. Never merge by concatenating
files or hand-deleting the older note. `vault.py merge` keeps one canonical identity, retires
the other under a chosen `--retire-mode`, and requires an exact preview hash before it writes
anything.

- **`rewrite` (preferred)** repoints every inbound link at the canonical note and deletes the
  retired file, so no tombstone accumulates. `merged_from` on the canonical keeps the record of
  what was retired.
- **`redirect` (default)** leaves a checked redirect at the retired path. Use it when an inbound
  link cannot be rewritten — one held outside the vault, or inside a sealed raw-source payload.

## Workflow

1. Choose the canonical and retired notes deliberately. Put a reviewed final body, headed
   with the canonical note's exact H1, in the ignored
   `90-system/indexes/.merge-drafts/` folder.
2. Preview without writing:

   ```text
   python3 90-system/automation/vault.py merge "40-knowledge/concepts/Canonical.md" "40-knowledge/concepts/Retired.md" --merged-body "90-system/indexes/.merge-drafts/canonical.md"
   ```

3. Review `metadata_conflicts`, `links_at_risk`, `inbound_rewrites`, `inbound_unrewritable`,
   alias/tag unions, `merged_from`, and the
   two selected paths. Revise the draft until the preview is correct.
4. Apply the exact plan:

   ```text
   python3 90-system/automation/vault.py merge "40-knowledge/concepts/Canonical.md" "40-knowledge/concepts/Retired.md" --merged-body "90-system/indexes/.merge-drafts/canonical.md" --apply --plan <plan_sha256>
   ```

If an input changes after preview, the plan hash changes and the command refuses to write.
Metadata conflicts or links at risk add a second stop; use `--accept-warnings` only after
explicitly resolving or accepting every reported item.

## Guarantees and limits

- The canonical note keeps its `id`, path, type, and creation date. Its aliases and tags
  are unioned, the retired title becomes an alias, and `merged_from` records the old path.
- Under `rewrite` the retired file is deleted and every inbound wikilink is repointed at the
  canonical note. An alias that merely names the retired note becomes the canonical title; a
  human-written label is preserved. Links inside code fences and spans are left alone, and
  sealed raw sources and generated indexes are never edited — they are reported as
  `inbound_unrewritable` and must be accepted explicitly.
- Under `redirect` the retired file is kept. It keeps its own `id` and title, becomes
  `type: redirect` / `status: superseded`, points to the canonical note with `redirect_to`, and
  existing backlinks continue to resolve through it. The checker rejects broken,
  self-targeting, chained, or cyclic redirects. A merge also refuses to retire a note that
  already has inbound redirects, because doing so would create a redirect chain.
- Canonical-only metadata wins. Retired-only or conflicting metadata is reported rather
  than guessed. Typed relations and freshness declarations are removed from the redirect;
  incorporate any still-valid claims into the reviewed canonical draft and metadata.
- The command refuses raw sources, redirects, MOCs, system notes, journal/review notes,
  archive material, attachments, and root control files. It never deletes the draft.
- Both replacements are prepared before either target is swapped. A failed second swap
  attempts to restore the original canonical file; Git remains the recovery boundary.

Run `vault.py check` and inspect `git diff` immediately after applying. Remove the local
draft only after the result is committed or otherwise recoverable.

Related: [[90-system/Vault Contract|Vault Contract]] · [[90-system/Link Policy|Link Policy]] · [[90-system/automation/MOC - Automation|Automation]]
