---
id: "mcp-reliability-investigation"
type: "system"
status: "active"
created: "2026-09-05"
updated: "2026-09-05"
aliases: []
tags: []
---

# MCP Reliability Investigation

Parent: [[90-system/reports/MOC - Reports|Reports]]

## Summary

The old server has reproducible failure paths that can explain an apparently unreachable
MCP connection: a slow retrieval blocks health checks, Windows pipe encoding can crash a
Unicode response, and an interrupted cache update can retain a database writer lock.
These defects are fixed in server version `1.1.1`. This is not proof of which defect caused
the reported historical timeout: no timestamped client error or traceback was available.

Investigation baseline: template commit `c5fc3b4`. Read-only inspection also confirmed that
the private vault's version `1.0.0` contains the affected output and synchronous-serving
code. Private notes, client registrations, and the running private server were not changed.

## Findings and changes

| Finding | Evidence and consequence | Implemented correction |
| --- | --- | --- |
| Connection loop blocked by tools | A two-second injected retrieval stall prevented a ping response within one second. The old `serve` called the entire handler inline. | Keep framing, health checks, discovery, and cancellation in the connection process; run one tool at a time in an isolated child. |
| Windows output encoding | A real subprocess with `PYTHONIOENCODING=cp1252` crashed with `UnicodeEncodeError` when reading multilingual text and an emoji. Plain Western non-ASCII output can also violate UTF-8 framing. | Write UTF-8-compatible JSON bytes directly, independent of the inherited text encoding. |
| Cache transaction and connection leaks | An invalid-UTF-8 note encountered after an earlier update left `connection.in_transaction` true; failed `open_cache` retained an open connection. | Roll back failed sync transactions; close failed constructors and syncs; use deterministic cleanup around cache-consuming commands. |
| Non-atomic schema replacement | The old schema path mixed DROP statements with `executescript`, which commits before executing its script. Initialization failure could expose partial tables. | Serialize schema replacement with `BEGIN IMMEDIATE`, recheck the version after acquiring the lock, and keep DDL and version publication in one transaction. Failure injection proves the old schema survives. |
| Cancellation and worker lifetime | The old server ignored cancellation notifications and had no read deadline. A new child-process design also needs protection against orphaned readers after abrupt parent death. | Cancel queued jobs without executing them; terminate only active read workers; enforce a read deadline and watch the parent's pipe lifetime. Never automatically replay captures. |
| Pipe-close shutdown | The actual Windows runtime reported a closed output pipe as `OSError(EINVAL)` and exited with code 120 while re-flushing stdout. | Normalize output-pipe failures and prevent a second flush of the broken descriptor. |

Additional defensive coverage now rejects oversized/deep/malformed frames, invalid request
IDs, non-finite numbers, and lone Unicode surrogates. Responses and tool admission are
bounded. These are hardening measures, not established causes of the historical incident.
Worker crashes return a tool error instead of killing discovery or subsequent reads.

The committed MCP audit hook matches captures, not read tools, so its normal execution
does not explain read-only timeouts. The separate post-edit hook can access the same cache
after note edits, which makes contention handling important. Installed custom hooks were
not audited; no client hooks were disabled or changed.

## Runtime and safety contract

- The read deadline defaults to 30 seconds, including the admitted tool queue. Configure
  `--read-timeout-seconds` only when measurements justify another positive value, up to 300.
- At most eight tool calls are admitted per connection, including the active one. Excess
  calls return `server_busy`; a queued read can expire before it starts. Pings bypass tools.
- SQLite contention waits at most one second per busy operation and returns `cache_busy`
  through MCP. A corrupt cache returns `cache_unavailable`; ordinary reads never delete it.
- Active captures are not forcibly stopped by the read deadline or cancellation. They
  finish their existing guarded note/MOC transaction, but no response is sent after their
  cancellation. An uncertain capture must be checked by title/path before any retry.
- EOF drains admitted work. On an output disconnect, reads are stopped and an active
  capture is allowed to finish. Abrupt OS termination of a capture still has the existing
  crash-consistency limitations of a two-file write; this is not a new durable journal.
- Only protocol JSON goes to stdout. Error/slow/cancellation diagnostics on stderr contain
  the tool name, event, and elapsed milliseconds, not queries, note contents, paths, IDs,
  or exception details. A failed diagnostic sink does not break protocol handling.
- The seven MCP tools, hook matchers, source trust boundary, capture approvals, lexical
  ranking, and one shared cache remain unchanged. No SDK or other dependency was added.

## Verification

Result on 2026-09-05: all 178 tests passed with Python resource warnings enabled. The
strict template vault check found 74 notes, zero errors, and zero warnings; `git diff
--check` passed. No interactive Codex/Claude session or Linux host was tested.

```text
python3 -m unittest discover -s 90-system/automation/tests -v
python3 90-system/automation/vault.py check --strict --compact
```

The resilience tests use temporary synthetic vaults and actual stdio subprocesses. They
cover Unicode under a legacy Windows encoding; ping during a stalled read; timeout and
successful subsequent reads without reconnecting; active and queued cancellation; capture
completion after cancellation; worker crash; abrupt parent death; queue/response bounds;
modern timeout envelopes; closed output pipes; malformed frames; simultaneous cold-cache
clients; lock contention; corruption reporting; and rollback/connection cleanup failures.
The pre-existing capture, immutable-source, retrieval, merge, hook, and schema tests remain.

A local Windows/Python 3.14.5 timing sample used seven small synthetic notes, one initialized
connection, and 20 searches: initialize 89 ms; first search 153 ms; warm search median 132 ms,
maximum 141 ms. Direct in-process handlers measured a 2.5 ms median. Isolation therefore
adds about 0.13 seconds of process/dispatch overhead in this fixture; it does not speed up
ranking. This bounded overhead buys crash/timeout containment. It is not a large-vault,
Nextcloud, Linux, or interactive Codex/Claude performance qualification.

## Remaining uncertainties and deployment

The cache lives inside the synchronized vault tree. Filesystem stalls, placeholder hydration,
sync conflicts, and concurrent external cache rebuilds are additional possibilities, not
observed causes. Git ignore rules do not configure the sync client. Its actual exclusion
rules and the original client timeout settings were not audited in this investigation.
Do not rebuild/delete the cache while clients or maintenance commands are using it.

This fix is on `bugfix/mcp-retrieval-resilience`, based on
`feature/engineering-memory-workflows`; the engineering branch is its ancestor. Merge the
bugfix branch back into that feature branch, or merge the combined branch to main after
review. It is not an independent main-only patch without the engineering-memory changes.

After the normal reviewed template-to-private update, restart both MCP connections and
confirm `serverInfo.version` is `1.1.1`. Test a known multilingual note, search, context
pack, related notes, and status. Keep the client's call timeout above the server's read
deadline. If a timeout persists, retain the tool name, time, and privacy-safe stderr event;
distinguish `retrieval_timeout`/`cache_busy` results from a genuinely closed transport.
See [[90-system/MCP Integration|MCP Integration]] for the operational runbook.

## Protocol and database references

The [MCP transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
requires UTF-8 protocol messages; the [ping contract](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/ping)
requires a prompt response and permits clients to disconnect after a failed health check.
The [legacy cancellation rules](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation)
and [modern stdio cancellation rules](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)
define cancellation on the shared connection. Existing write side effects cannot always
be rolled back, so the server preserves capture completion rather than killing a write.

Python's [SQLite documentation](https://docs.python.org/3/library/sqlite3.html)
distinguishes transaction context management from connection closure and documents
`executescript`'s implicit commit behavior and the configurable busy timeout.
