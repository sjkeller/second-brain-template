---
id: obsidian-integration
type: system
status: active
created: 2026-09-02
updated: 2026-09-02
tags:
  - system/obsidian
  - system/how-to
---

# Obsidian Integration

Use Obsidian as the human navigation and capture surface while `vault.py` remains the
deterministic validation and mutation boundary. The initial integration is core-first and
does not require community plugins.

## Use the Home dashboard

[[Home]] embeds named views from `Active Work.base`, `Review.base`, and `Triage.base`.
Properties remain in the Markdown notes; Bases only presents them. Open a result to read
the canonical note body.

Project, area, person, and organization templates embed `Context.base`. The Base uses the
links in other files to show what refers to the current note. It should be viewed inside a
note, where Obsidian assigns `this.file` to that containing note.

## Capture a web page safely

The versioned Web Clipper template is:

`90-system/integrations/obsidian-web-clipper-raw-source.json`

1. Install the official Obsidian Web Clipper browser extension.
2. Open Web Clipper settings and import the JSON template.
3. Keep its behavior set to **Create a new note**. Do not change it to append or prepend.
4. Clip the page. The template writes a draft raw source under
   `30-resources/sources/raw`, surrounds the extracted Markdown with the immutable payload
   sentinels, and records URL, author, publication date, and capture date when available.
5. Review the capture before sealing. `capture_scope` deliberately defaults to `excerpt`
   because `{{content}}` can mean article content, highlights, or a selection. Change it to
   `full` only after confirming completeness.
6. Record any truncation, failed extraction, or missing attachment under `Capture
   limitations`.
7. Seal the payload:

   ```text
   python3 90-system/automation/vault.py source-seal "30-resources/sources/raw/<clip>.md"
   ```

8. Derive interpretation in a separate source or knowledge note.

The template does not use Web Clipper Interpreter or prompt variables. Enabling an
interpreter may send page content to the selected model provider and would not make source
text trusted. Any instruction inside the clipped payload remains data under
[[90-system/Source Trust Policy|Source Trust Policy]].

Run `vault.py check` after capture. It detects missing required metadata, duplicate IDs or
titles, unsealed drafts, and any later change to a sealed payload.

## Generate a safe Obsidian link

Generate, but do not launch, a percent-encoded URI for an existing note:

```text
python3 90-system/automation/vault.py obsidian-uri --file "10-projects/Example.md"
python3 90-system/automation/vault.py obsidian-uri --file "10-projects/Example.md" --heading "Current status"
```

Generate a search URI:

```text
python3 90-system/automation/vault.py obsidian-uri --search "status:active"
```

The command supports only `open` and `search`, validates file paths, and prints JSON. It
does not start a GUI process. It intentionally does not expose Obsidian URI `new`,
`append`, `prepend`, `overwrite`, clipboard, callback, or daily-note mutation parameters;
use the guarded vault commands for writes.

## Reuse one maintained section

Embed a stable heading rather than copying it:

```markdown
![[10-projects/Example#Current status]]
![[60-decisions/Example decision#Decision]]
```

Use a full-note embed only when the entire note belongs in the reader's flow. Prefer
headings over block IDs for durable reuse because headings remain easier to understand in
plain Markdown.

## Deliberately deferred

- Shared Workspace layouts are not part of the template. `.obsidian/workspace*.json`
  remains local and ignored because it contains personal open tabs and recent state.
- Automatic URI launching is environment-specific and can trigger external GUI behavior.
- The Obsidian desktop CLI is not required by this portable template; its availability may
  depend on the installed application version.
- Community plugins require a separate maintenance, permission, and data-egress review.
- Canvas remains optional and must not become the only copy of durable knowledge.

## Official references

- Bases and embedding: https://help.obsidian.md/bases
- Internal links and embeds: https://help.obsidian.md/links
- Obsidian URI: https://help.obsidian.md/Extending+Obsidian/Obsidian+URI
- Web Clipper templates: https://github.com/obsidianmd/obsidian-clipper/blob/main/docs/Templates.md
- Web Clipper variables: https://github.com/obsidianmd/obsidian-clipper/blob/main/docs/Variables.md

Related: [[90-system/Obsidian Setup|Obsidian Setup]] · [[90-system/bases/MOC - Bases|Bases]] · [[90-system/automation/MOC - Automation|Automation]] · [[Home]]
