---
id: freshness-policy
type: system
status: active
created: 2026-09-02
updated: 2026-09-03
tags:
  - system/provenance
  - system/quality
---

# Freshness Policy

Store durable knowledge without making an old observation look current. Every fact that
needs freshness handling should use one of three forms:

1. **Timeless** — a stable definition, mechanism, rationale, or historical statement.
2. **Snapshot** — what was observed on a specific date. Dated journal and source notes are
   naturally snapshots.
3. **Pointer** — where the current truth lives, plus the date it was last verified. Use
   pointers for balances, prices, inventory, open work, schedules, roles, and other live
   state rather than copying a value that will silently decay.

## Optional frontmatter

Declare freshness only when it adds information; ordinary durable notes need no boilerplate.

```yaml
freshness: timeless | snapshot | pointer
observed: YYYY-MM-DD             # required for an explicit snapshot
truth_source: https://...        # required for a pointer
# Or use a quoted Wikilink: "[[30-resources/Example|Example]]"
last_verified: YYYY-MM-DD        # required for a pointer
freshness_window_days: 30        # optional; default 30
valid_from: YYYY-MM-DD            # optional fact lifetime
valid_until: YYYY-MM-DD | present
```

`vault.py check` validates declared metadata and warns when pointer verification expires.
It deliberately does not guess whether natural-language prose is volatile: that would be
fragile across German, English, domain terminology, quotations, and hypothetical examples.

## Maintenance

When a pointer expires, re-check its truth source and update `last_verified`, remove the
copied value and retain only the pointer, or move the old value into a dated snapshot. Do
not rewrite historical snapshots to make them current. `updated` records note maintenance;
it is not evidence that every external claim was re-verified.

Related: [[90-system/Vault Contract|Vault Contract]] · [[90-system/Source Trust Policy|Source Trust Policy]] · [[90-system/Link Policy|Link Policy]]
