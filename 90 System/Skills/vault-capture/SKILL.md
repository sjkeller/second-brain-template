---
name: vault-capture
description: Capture a thought, link, quote, or fact into this Obsidian second brain without deciding its final home. Use when the user says capture, save this, note this down, add to inbox, or remember this for the vault. Not for editing an existing note or for reorganising the vault.
---

# Vault Capture

Use `python3` in the commands below; `py` is the fallback for Windows installations that
do not expose that executable name.

Capture is cheap; filing is expensive. Get the material in with enough context to be
understood later, and stop there.

## Decide the destination

Use `00 Inbox` unless the destination is unambiguous. It is unambiguous only when the note
is clearly one durable subject and you already know its folder — a named concept, person,
organization, source, or decision.

## Create the note

```
python3 "90 System/Automation/vault.py" new --type <type> --title "<title>"
```

The command fills frontmatter, generates the id, and links the parent MOC. Use
`--type note` for inbox captures, `--dry-run` first if the placement is uncertain.

Then write the content:

- Record what the user actually said or sent. Quote source material rather than
  paraphrasing it away.
- Keep the source: URL, author, and the date accessed. If there is no source, say so.
- Mark clearly what is fact, what is the user's interpretation, and what is unverified.
- Never fill a gap with a plausible guess. An empty section is better than an invented one.

## Finish

Run `python3 "90 System/Automation/vault.py" check --quiet`. Report the created path. Do not
reorganise anything else — that is what `vault-triage` is for.
