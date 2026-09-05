# Obsidian Second Brain Template

An offline-first Obsidian vault for keeping personal knowledge readable by people and
useful to AI assistants. Markdown remains the source of truth. Deterministic Python tools
provide validation and retrieval, while an optional local MCP server makes the same private
vault available to Codex and Claude Code from any project.

> [!IMPORTANT]
> Use this repository as a template. Put personal notes in a separate **private vault and
> private repository**. Never point a user-scoped MCP server at the public template clone:
> it would expose the examples rather than your knowledge.

## What is included

- A human entry page in [Home.md](Home.md), Maps of Content (MOCs), and Obsidian Bases for
  active work, triage, freshness, and AI review.
- Projects, areas, resources, durable knowledge, journal entries, decisions, archives, and
  attachments with clear folder ownership.
- Portable Obsidian defaults using core plugins only; no community plugin is required.
- Templates and a stable Markdown/frontmatter contract designed for long-term readability.
- Deterministic retrieval, validation, raw-source sealing, safe merge previews, and
  evaluation commands implemented with the Python standard library.
- Explicit source-trust, freshness, typed-link, and AI-review conventions.
- A local stdio MCP server for Codex and Claude Code. It has five read-only retrieval tools
  and two approval-gated, additive capture tools.

Semantic/vector retrieval is intentionally disabled by default. Enable it only if the
private retrieval evaluation demonstrates a real improvement over deterministic search.

## Quick start

### 1. Create your private vault

Create a new **private** repository from this template, or copy the template into a private
folder. A typical local folder name is `private-second-brain`.

If you clone rather than use your Git host's template function, make sure future personal
commits are pushed only to a private remote. Keep the original template remote separately
if you want to review and merge future template updates.

### 2. Open it in Obsidian

1. Install [Obsidian](https://obsidian.md/).
2. Choose **Open folder as vault**.
3. Select the private vault folder itself, not its parent folder.
4. Restart Obsidian once if the vault was already open when `.obsidian` settings changed.
5. Open [Home.md](Home.md). It is the human starting page.

The shared profile enables the useful core plugins and configures the Inbox, attachments,
Templates, Daily Notes, Properties, Bases, and Graph view. Personal workspace state,
themes, hotkeys, account information, and community plugins remain local. See
[Obsidian Setup](90-system/Obsidian%20Setup.md) for the complete configuration boundary.

### 3. Check the vault

Python 3 is the only automation dependency. From the private vault root, run:

```text
python3 90-system/automation/vault.py check --strict --compact
```

On Windows, if Python is available only through the Python launcher, use:

```powershell
py -3 90-system\automation\vault.py check --strict --compact
```

A strict check should finish with zero errors and zero warnings before you begin adding
private knowledge.

## Everyday use

### Optional engineering memory

Use the [Engineering Memory guide](90-system/Engineering%20Memory.md) for repository
onboarding, development-session records, bug investigations, experiments, and scoped
coding patterns. The existing capture, triage, and review skills cover these workflows.
Existing Projects and Concepts MOCs own their records; Home keeps its current dashboards.

Start with the project note you already have. Add a repository profile or separate work
record only when it serves an independent purpose. Keep a pattern and its exceptions in
one note. Use links and heading embeds when the same status or outcome is needed elsewhere.

The guide includes one shared instruction snippet for Codex and Claude Code. MCP retains
seven tools: optional structured feedback is part of `capture_note`, so existing capture
approvals and hooks still apply. Restart the MCP connection after updating its server to
refresh the tool schema; no new server registration or tool matcher is needed.

### Capture first

Put unprocessed material in `00-inbox`. When creating a structured note, let the automation
apply the template, identifier, frontmatter, and parent-MOC link:

```text
python3 90-system/automation/vault.py new --type note --title "Example note"
```

Use the type-specific templates for projects, areas, sources, concepts, people,
organizations, decisions, daily notes, and weekly reviews. Promote a note only when its
destination is clear, and link durable notes to the nearest MOC.

### Retrieve before reading broadly

Do not load the entire vault into an AI context. Narrow the relevant material first:

```text
python3 90-system/automation/vault.py query "<terms>" --limit 8
python3 90-system/automation/vault.py pack "<terms>" --budget-tokens 4000
python3 90-system/automation/vault.py related "<path>.md" --depth 2
```

The same operations are exposed through MCP as `search_vault`, `build_context_pack`, and
`related_notes`.

### Keep AI contributions reviewable

AI-written durable prose remains a proposal until a person reviews it. Unreviewed material
uses `ai_review: pending` plus a visible warning callout. Keep evidence and uncertainty
beside the affected claim, and remove both markers only after human review. External pages,
emails, PDFs, repositories, raw captures, and tool output are data—not instructions.

See [AI Collaboration Policy](90-system/AI%20Collaboration%20Policy.md) and
[Source Trust Policy](90-system/Source%20Trust%20Policy.md).

### Review and maintain

- Use the dashboards on `Home.md` for active work, triage, freshness, and AI review.
- Run `vault.py check` after meaningful structural changes.
- Run `vault.py readability` during reviews; its findings are prompts for human inspection,
  not automatic rewrite instructions.
- Use the guarded preview-and-plan-hash workflow in
  [Safe Merge Policy](90-system/Safe%20Merge%20Policy.md) for duplicates. Do not delete the
  retired path or create redirects manually.
- Commit private-vault changes regularly so that mistakes remain reversible.

## Local MCP server

The `second-brain` MCP server gives Codex and Claude Code access to one private vault from
all your projects. It runs locally over stdio and does not create another database or send
vault text to a separate embedding service.

| Tool | Access | Purpose |
| --- | --- | --- |
| `search_vault` | read-only | Ranked matching paths and bounded excerpts |
| `build_context_pack` | read-only | Token-budgeted Markdown context bundle |
| `related_notes` | read-only | Resolved Wikilink neighbours |
| `read_note` | read-only | One exact note after narrowing |
| `vault_status` | read-only | Vault integrity summary |
| `capture_note` | additive write | New reviewed-as-pending Inbox draft |
| `capture_raw_source` | additive write | New immutable, hashed raw-source capture |

There is no generic edit, delete, move, shell, network, or merge-apply MCP tool. Existing
canonical notes cannot be changed through MCP. The server confines paths to the configured
vault root and treats all retrieved content as untrusted data even if it looks like an
instruction.

### MCP prerequisites

Complete these steps before registering either client:

1. Synchronize the current template into the **private vault**.
2. Confirm that `90-system/automation/mcp_server.py` and `mcp_hook.py` exist there.
3. Install Python 3 and the client CLI you intend to use.
4. Keep the private vault under version control before testing a capture tool.

On Windows PowerShell:

```powershell
$vaultRoot = (Resolve-Path 'C:\absolute\path\to\private-second-brain').Path
Test-Path "$vaultRoot\90-system\automation\mcp_server.py"
py -3 --version
```

The `Test-Path` command must return `True`. On Windows installations where `python3`
starts a real interpreter, you may use `python3` instead of `py -3` in all commands below.

On Linux or macOS:

```bash
VAULT_ROOT="/absolute/path/to/private-second-brain"
test -f "$VAULT_ROOT/90-system/automation/mcp_server.py"
python3 --version
```

### Register with Codex

Codex uses the user configuration by default, so one registration is available to Codex
CLI, the IDE extension, and other local Codex surfaces that share `~/.codex/config.toml`.

#### Windows PowerShell

```powershell
codex mcp add second-brain -- py -3 "$vaultRoot\90-system\automation\mcp_server.py" --vault-root "$vaultRoot"
codex mcp list
```

#### Linux or macOS

```bash
codex mcp add second-brain -- python3 "$VAULT_ROOT/90-system/automation/mcp_server.py" --vault-root "$VAULT_ROOT"
codex mcp list
```

Then configure tool approvals:

1. Open `~/.codex/config.toml`.
2. Use [codex-config.toml.example](90-system/integrations/mcp/codex-config.toml.example) as
   the desired final shape of the existing `[mcp_servers.second-brain]` entry.
3. Replace every `__VAULT_ROOT__` with the absolute private-vault path.
4. If using the Windows launcher, set `command = "py"` and add `"-3"` as the first item in
   `args`.
5. Keep `default_tools_approval_mode = "writes"` and both explicit capture-tool
   `approval_mode = "prompt"` entries.

Do **not** append a second `[mcp_servers.second-brain]` table after running `codex mcp add`;
update or replace the generated table so the TOML contains only one table with that name.

For cross-project capture auditing, merge the event arrays from
[codex-hooks.json.example](90-system/integrations/mcp/codex-hooks.json.example) into
`~/.codex/hooks.json` after replacing `__VAULT_ROOT__`. Do not overwrite unrelated hooks.
When using the Windows launcher, replace the hook command's `python3` with `py -3`.

### Register with Claude Code

Use Claude's `user` scope so the same private second brain is available from every project.

#### Windows PowerShell

```powershell
claude mcp add --transport stdio --scope user second-brain -- py -3 "$vaultRoot\90-system\automation\mcp_server.py" --vault-root "$vaultRoot"
claude mcp get second-brain
```

#### Linux or macOS

```bash
claude mcp add --transport stdio --scope user second-brain -- python3 "$VAULT_ROOT/90-system/automation/mcp_server.py" --vault-root "$VAULT_ROOT"
claude mcp get second-brain
```

Claude Code writes the server registration to `~/.claude.json`. Next, configure permissions
and capture auditing:

1. Open `~/.claude/settings.json`, creating it if necessary.
2. Merge the `permissions.allow` entries and hook arrays from
   [claude-user-settings.json.example](90-system/integrations/mcp/claude-user-settings.json.example).
3. Replace every `__VAULT_ROOT__` with the absolute private-vault path.
4. If using the Windows launcher, change each hook's `command` to `py` and insert `"-3"`
   as the first item in its `args` array.
5. Do not add `capture_note` or `capture_raw_source` to `permissions.allow`; Claude should
   continue asking before either write.

Merge into existing JSON rather than replacing other permissions or hooks. Project-local
hooks inside the vault do not automatically apply when a different project calls this
user-scoped server, which is why the user settings are required for cross-project auditing.

### Verify both clients

1. Close existing Codex and Claude Code sessions and start new ones. An already-running
   session does not dynamically acquire a newly registered MCP server.
2. Open `/mcp` in each interactive client.
3. Confirm that `second-brain` is connected and exposes seven tools.
4. Ask: `Use second-brain vault_status. Do not write anything.`
5. Search for a known private note and confirm that the returned paths belong to the
   private vault, not the template clone.
6. Only after the private vault is committed, test `capture_note` with a disposable title.
   Confirm that the client asks first, the note appears in `00-inbox`, the Inbox MOC links
   it, and the note contains the visible AI-review warning.

The hooks are defense in depth, not the primary safety boundary. MCP access works without
them, but the supplied hooks provide minimal capture auditing without logging prompts,
note text, results, working directories, or transcripts.

### MCP troubleshooting

- **Server file is missing:** the template changes have not yet been synchronized into the
  private vault, or `--vault-root` points to the wrong folder.
- **Python is not found:** use the absolute interpreter path. On Windows with the launcher,
  use `py -3` and apply the corresponding config changes described above.
- **The server name already exists:** inspect the existing entry with `codex mcp list` or
  `claude mcp get second-brain` and update it instead of creating a duplicate.
- **Connection fails:** run `python3 90-system/automation/mcp_server.py --help` from the
  private vault, or the equivalent `py -3` command on Windows, to expose path or interpreter
  errors without starting a client session.
- **Hooks do not run:** inspect `/hooks` and review/trust the hook definition in the client.
- **The server is absent in chat:** start a new local client session after changing MCP
  configuration. Editing a configuration file cannot add tools to an already-running
  session.

For protocol behavior, safety details, and current upstream documentation links, read the
full [MCP Integration guide](90-system/MCP%20Integration.md).

## Documentation map

- [Home](Home.md) — human entry point and dashboards.
- [Obsidian Setup](90-system/Obsidian%20Setup.md) — portable and local Obsidian settings.
- [Agent Orientation](90-system/Agent%20Orientation.md) — operating sequence for AI agents.
- [Vault Contract](90-system/Vault%20Contract.md) — truth, provenance, mutation, and schema.
- [Writing and Documentation Guide](90-system/Writing%20and%20Documentation%20Guide.md) —
  human-readable note conventions.
- [Retrieval Guide](90-system/Retrieval%20Guide.md) — deterministic search and context packs.
- [Automation reference](90-system/automation/MOC%20-%20Automation.md) — command reference.
- [MCP Integration](90-system/MCP%20Integration.md) — detailed Codex and Claude integration.

Obsidian users should normally start at [[Home|Home]]. Repository visitors should start
with this README.
