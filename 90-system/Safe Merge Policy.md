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
files or deleting the older note. `vault.py merge` keeps one canonical identity, replaces
the retired note with a checked redirect, and requires an exact preview hash before it can
write either file.

## Workflow

1. Choose the canonical and retired notes deliberately. Put a reviewed final body, headed
   with the canonical note's exact H1, in the ignored
   `90-system/indexes/.merge-drafts/` folder.
2. Preview without writing:

   ```text
   python3 90-system/automation/vault.py merge "40-knowledge/concepts/Canonical.md" "40-knowledge/concepts/Retired.md" --merged-body "90-system/indexes/.merge-drafts/canonical.md"
   ```

3. Review `metadata_conflicts`, `links_at_risk`, alias/tag unions, `merged_from`, and the
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
- The retired file is not deleted. It keeps its own `id` and title, becomes
  `type: redirect` / `status: superseded`, and points to the canonical note with
  `redirect_to`.
- Existing backlinks are not rewritten. They continue to resolve through the retired
  path. The checker rejects broken, self-targeting, chained, or cyclic redirects. A merge
  also refuses to retire a note that already has inbound redirects, because doing so would
  create a redirect chain.
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
