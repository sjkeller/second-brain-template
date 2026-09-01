#!/usr/bin/env python3
"""PostToolUse hook: stamp `updated` on an edited note, then report vault health.

Wired to Write|Edit through `python3` in .claude/settings.json. Reads the hook payload on
stdin and:

1. stamps `updated:` on the edited note, skipping Journal, System, and Attachments
   (see `is_auto_stamp_target` in vault.py -- those are dated, generated, or binary);
2. resolves note and attachment links and prints unresolved targets to stderr as a warning.

It never blocks. Every failure path exits 0, because a broken hook must not stop an edit
that already happened. Exit 2 would block; that is deliberately unreachable here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VAULT_SCRIPT = PROJECT_ROOT / "90-system" / "automation" / "vault.py"


def load_vault_module():
    spec = importlib.util.spec_from_file_location("vault_tools", VAULT_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    # Register before executing: vault.py uses `from __future__ import annotations`, and
    # dataclass field resolution looks the module up in sys.modules by name.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    raw_path = (payload.get("tool_input") or {}).get("file_path")
    if not raw_path or not VAULT_SCRIPT.is_file():
        return 0

    try:
        relative = Path(raw_path).resolve().relative_to(PROJECT_ROOT).as_posix()
    except (ValueError, OSError):
        return 0  # Edited something outside the vault.

    try:
        vault = load_vault_module()
        if vault is None:
            return 0

        messages: list[str] = []
        if vault.is_auto_stamp_target(relative):
            note = PROJECT_ROOT / relative
            if note.is_file():
                text = note.read_text(encoding="utf-8-sig")
                stamped, changed = vault.bump_updated(text, vault.date.today().isoformat())
                if changed:
                    note.write_text(stamped, encoding="utf-8", newline="")
                    messages.append(f"stamped updated: on {relative}")

        cache = vault.open_cache(PROJECT_ROOT)
        notes = cache.notes()
        cache.close()
        _, unresolved = vault.graph(notes, vault.asset_maps(PROJECT_ROOT))
        if unresolved:
            broken = ", ".join(
                f"{item['source']} -> [[{item['target']}]]" for item in unresolved[:3]
            )
            more = f" (+{len(unresolved) - 3} more)" if len(unresolved) > 3 else ""
            messages.append(f"{len(unresolved)} unresolved link(s): {broken}{more}")

        if messages:
            print("vault: " + "; ".join(messages), file=sys.stderr)
    except Exception as error:  # noqa: BLE001 - a hook must never break the session.
        print(f"vault hook skipped: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
