---
name: vault-review
description: Run the weekly review of this Obsidian second brain — process the inbox, check projects and areas for stalled work, promote durable knowledge, and repair vault health. Use when the user asks for a weekly review, a vault review, or a periodic cleanup.
---

# Vault Review

Use `python3` in the commands below; `py` is the fallback for Windows installations that
do not expose that executable name.

A weekly pass over the whole vault. Produce a review note, not just a chat summary.

## Gather the facts deterministically

```
python3 90-system/automation/vault.py check --compact
python3 90-system/automation/vault.py tasks --state open --compact
python3 90-system/automation/vault.py stale --days 180 --compact
python3 90-system/automation/vault.py tags --compact
```

These four commands answer most review questions without reading a single note. Read notes
only where a finding needs judgement.

## Create the review note

```
python3 90-system/automation/vault.py new --type review --title "<YYYY-Www>"
```

Then work through it:

- **Inbox.** Anything left uncaptured or unfiled? Hand off to `vault-triage`.
- **Projects.** Every active project needs a next action and a finish condition. Flag any
  with neither. Completed ones move to `80-archive`.
- **Areas.** Which standards were neglected this week?
- **Knowledge.** Promote durable lessons out of journal entries and projects into
  `40-knowledge`. This is the step that most often gets skipped.
- **Engineering, when used.** Review scoped feedback and stale or conflicted patterns using
  [[90-system/Engineering Memory]]. Consolidate into the existing subject, preserving
  evidence and exceptions. Do not create a second style profile or copy session summaries.
- **Health.** Work the `check` errors first, then warnings. Broken links and duplicate ids
  are real breakage; placement and staleness warnings are judgement calls.

## Report honestly

State what you did not get to. A review that claims completeness it does not have is worse
than one that names its gaps. Do not mark work complete on the user's behalf.
