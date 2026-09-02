#!/usr/bin/env python3
"""Non-blocking Claude/Codex hook for privacy-preserving MCP call auditing.

The MCP server itself enforces every safety rule. This hook records only event and tool
names; it deliberately never copies note titles, queries, content, results, paths, or
transcripts into the audit log. Any hook failure exits successfully so it cannot break a
session after the server has already enforced its boundary.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SERVER_TOOL_PREFIX = "mcp__second-brain__"
AUDIT_RELATIVE = Path("90-system/indexes/mcp-audit.jsonl")
ALLOWED_EVENTS = {"PreToolUse", "PostToolUse", "PostToolUseFailure"}


def event_record(payload: Any) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    event = payload.get("hook_event_name")
    tool = payload.get("tool_name")
    if event not in ALLOWED_EVENTS or not isinstance(tool, str) or not tool.startswith(SERVER_TOOL_PREFIX):
        return None
    return {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        "tool": tool,
    }


def append_record(root: Path, record: dict[str, str]) -> None:
    destination = (root / AUDIT_RELATIVE).resolve()
    destination.relative_to(root.resolve())
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--vault-root", required=True)
    try:
        args = parser.parse_args(argv)
        payload = json.load(sys.stdin)
        record = event_record(payload)
        if record is not None:
            append_record(Path(args.vault_root).expanduser().resolve(), record)
    except Exception:  # A defense-in-depth audit hook must never block an MCP call.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
