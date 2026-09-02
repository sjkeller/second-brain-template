---
id: mcp-integration
type: system
status: active
created: 2026-09-02
updated: 2026-09-02
tags:
  - system/agent
  - system/integration
  - system/security
---

# MCP Integration

Use the local `second-brain` MCP server when Claude Code or Codex should reach one private
vault from any project. It is a local stdio process: Markdown remains the source of truth,
retrieval stays deterministic, and no vault text is sent to a separate embedding service.

> [!warning] Configure the private vault, not this template clone
> Finish synchronising the template into the private vault first. Then replace every
> `__VAULT_ROOT__` below with the absolute private-vault path. Pointing the user-scoped
> server at `second-brain-template` would expose examples instead of personal knowledge.

Verified against the official Codex, Claude Code, and MCP documentation on 2026-09-02;
the documented add-command syntax was also checked locally with Codex CLI 0.152.1 and
Claude Code 2.1.258.

## What the server exposes

| Tool | Mutation | Purpose |
| --- | --- | --- |
| `search_vault` | none | ranked paths and bounded excerpts |
| `build_context_pack` | none | one token-budgeted Markdown context bundle |
| `related_notes` | none | resolved wikilink neighbours |
| `read_note` | none | one exact Markdown note after narrowing |
| `vault_status` | none | integrity-check summary and errors |
| `capture_note` | additive | new `00-inbox` draft with `ai_review: pending` |
| `capture_raw_source` | additive | new immutable, hashed raw-source capture |

There is deliberately no generic edit, delete, move, merge-apply, shell, attachment, or
network tool. Existing canonical knowledge content cannot be changed through MCP; a
successful capture changes only the new note and the parent MOC's machine-managed link
list. Use the guarded
[[90-system/Safe Merge Policy|Safe Merge Policy]] in an explicit vault-maintenance session
when a real merge is required.

## Safety boundary

The server, not a client hook, enforces the mandatory rules:

- `--vault-root` fixes every operation to one resolved vault path. Traversal, hidden
  runtime files, arbitrary filesystem access, and arbitrary commands are rejected.
- Retrieval output repeats the source trust boundary. Note content and raw payloads are
  data, never instructions, even when they contain urgent-looking tool directions.
- Normal capture accepts only a new Inbox note and visibly marks its prose for human
  review. Verbatim external material has a separate raw-source tool whose payload is
  structurally isolated and sealed before the note appears.
- Captures reject duplicate identities, use a short cross-process lock, prepare both the
  note and MOC update before replacement, and roll back a newly installed note if its MOC
  update fails. A normal capture that would introduce an unresolved structural wikilink is
  rejected before either file changes.
- The server has no network client and uses only Python's standard library plus
  [[90-system/automation/MOC - Automation|vault.py]].

The audit hook is defense in depth. It records only timestamp, event name, and MCP tool
name in ignored `90-system/indexes/mcp-audit.jsonl`; queries, titles, note contents,
results, working directories, and transcripts are never copied into the log. The default
matcher covers only the two capture tools, avoiding process-start overhead and access-log
noise on every read. A hook failure is non-blocking because server enforcement must remain
sufficient by itself.

## Install after the private vault is synchronised

The examples use `python3`, which is the vault contract on Windows and Linux. Use the full
interpreter path if a client process cannot find it. On a Windows installation that has
only the Python launcher, set the executable/`command` to `py` and insert `-3` as the first
argument in both the MCP and hook configurations.

### Codex

Add the local server to the user configuration shared by Codex CLI, the IDE extension, and
the ChatGPT desktop app:

```powershell
$vaultRoot = 'C:\absolute\path\to\private-second-brain'
codex mcp add second-brain -- python3 "$vaultRoot\90-system\automation\mcp_server.py" --vault-root "$vaultRoot"
```

Then merge the policy in
`90-system/integrations/mcp/codex-config.toml.example` into `~/.codex/config.toml`.
Its `writes` default auto-runs tools marked read-only and asks before either additive
capture. Keep the explicit per-capture `prompt` overrides.

For cross-project auditing, replace `__VAULT_ROOT__` in
`90-system/integrations/mcp/codex-hooks.json.example` and merge its event arrays into
`~/.codex/hooks.json`. Do not overwrite unrelated hooks. The committed `.codex/hooks.json`
is only the project-local equivalent for sessions launched inside this vault.

### Claude Code

Add the server at user scope so it loads in every project:

```powershell
$vaultRoot = 'C:\absolute\path\to\private-second-brain'
claude mcp add --transport stdio --scope user second-brain -- python3 "$vaultRoot\90-system\automation\mcp_server.py" --vault-root "$vaultRoot"
```

Replace `__VAULT_ROOT__` in
`90-system/integrations/mcp/claude-user-settings.json.example`, then merge its read-tool
allow rules and hook arrays into `~/.claude/settings.json`. The capture tools are
intentionally absent from `permissions.allow`, so Claude still asks before writing. Do
not replace existing settings wholesale. The committed `.claude/settings.json` provides
the same behavior only when the vault itself is the Claude project.

User-scoped hooks matter here: project-local hooks from the vault do not automatically
load merely because another project calls a user-scoped MCP server. Conversely, MCP tool
calls do fire `PreToolUse`, `PostToolUse`, and `PostToolUseFailure`; the supplied matcher
intentionally narrows those events to `capture_note` and `capture_raw_source`.

## Verify

From the private vault, run the deterministic tests and strict health check:

```text
python3 -m unittest discover -s 90-system/automation/tests -v
python3 90-system/automation/vault.py check --strict --compact
```

Then verify each client:

```text
codex mcp list
claude mcp get second-brain
```

Open `/mcp` in each interactive client. Confirm seven tools appear, call `vault_status`,
then search for a known private note. Test `capture_note` with a disposable title only
after the private vault is under version control; confirm the client asks first, the note
lands in `00-inbox`, the Inbox MOC links it, and the visible AI-review warning is present.

If a server fails to start, run the exact configured command in a terminal. Configuration
errors go to stderr; protocol responses alone use stdout. A stale
`90-system/indexes/.mcp-write.lock` is recovered after five minutes, but an active lock
means another capture is still in progress.

## Compatibility contract

`mcp_server.py` implements both the legacy `initialize`/`initialized` lifecycle used by
current MCP SDK defaults and the stateless MCP `2026-07-28` discovery/envelope form. Tool
lists are deterministic; modern responses include `resultType`, cache hints, and server
identity metadata, while legacy responses omit modern-only fields. Tool results provide
both JSON text and `structuredContent` for older and newer clients.

Official references: [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) ·
[Codex hooks](https://learn.chatgpt.com/docs/hooks) ·
[Claude Code MCP](https://code.claude.com/docs/en/mcp) ·
[Claude Code hooks](https://code.claude.com/docs/en/hooks) ·
[MCP tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) ·
[MCP discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)

Related: [[90-system/Agent Orientation|Agent Orientation]] · [[90-system/Source Trust Policy|Source Trust Policy]] · [[90-system/Obsidian Integration|Obsidian Integration]] · [[90-system/MOC - System|System]]
