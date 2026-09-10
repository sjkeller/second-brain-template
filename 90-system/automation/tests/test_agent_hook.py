"""Trigger, suppression, and safety tests for the session knowledge automation hook."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


AUTOMATION = Path(__file__).resolve().parents[1]
HOOK_SCRIPT = AUTOMATION / "agent_hook.py"

SPEC = importlib.util.spec_from_file_location("second_brain_agent_hook_test", HOOK_SCRIPT)
hook = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = hook
SPEC.loader.exec_module(hook)


def claude_lines(turns: int, files: list[str]) -> list[str]:
    lines = []
    for index in range(turns):
        content: list[dict] = [{"type": "text", "text": f"turn {index}"}]
        if index < len(files):
            content.append(
                {
                    "type": "tool_use",
                    "id": f"t{index}",
                    "name": "Edit",
                    "input": {"file_path": files[index], "old_string": "a", "new_string": "b"},
                }
            )
        lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": content}}))
    return lines


def codex_lines(turns: int, patches: int) -> list[str]:
    lines = []
    for index in range(turns):
        lines.append(
            json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": f"turn {index}"}],
                    },
                }
            )
        )
    for index in range(patches):
        lines.append(
            json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": json.dumps(
                            {"command": ["apply_patch", f"*** Begin Patch\n*** Update File: f{index}.c\n"]}
                        ),
                    },
                }
            )
        )
    return lines


class HookFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.container = Path(self.temporary.name)
        self.root = self.container / "vault"
        (self.root / "90-system/indexes").mkdir(parents=True, exist_ok=True)
        (self.root / "Home.md").write_text("# Home\n", encoding="utf-8")
        self.work = self.container / "project"
        self.work.mkdir()
        self.transcript = self.container / "transcript.jsonl"
        self.addCleanup(self.temporary.cleanup)

    def write_transcript(self, lines: list[str]) -> None:
        self.transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def payload(self, event: str, **overrides) -> dict:
        base = {
            "hook_event_name": event,
            "session_id": "session-1",
            "cwd": str(self.work),
            "transcript_path": str(self.transcript),
            "permission_mode": "default",
        }
        base.update(overrides)
        return base

    def dispatch(self, payload: dict) -> tuple[int, dict | None]:
        buffer = io.StringIO()
        with mock.patch.object(hook, "recall_block", return_value=""):
            with mock.patch.object(sys, "stdout", buffer):
                code = hook.dispatch(self.root, payload)
        text = buffer.getvalue().strip()
        return code, json.loads(text) if text else None

    def ledger(self) -> dict:
        return hook.read_ledger(self.root / hook.LEDGER_RELATIVE)


class TranscriptScanTest(HookFixture):
    def test_counts_claude_turns_and_distinct_edits(self) -> None:
        self.write_transcript(claude_lines(6, ["a.c", "b.c", "a.c"]))
        activity, position = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 6)
        self.assertEqual(activity.edits, 2)
        self.assertEqual(position, self.transcript.stat().st_size)

    def test_counts_codex_turns_and_patch_calls(self) -> None:
        self.write_transcript(codex_lines(4, 3))
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 4)
        self.assertEqual(activity.edits, 3)

    def test_unrecognised_shape_falls_back_to_line_count(self) -> None:
        self.write_transcript([json.dumps({"kind": "mystery", "n": index}) for index in range(12)])
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 3)

    def test_offset_past_end_of_file_rereads_from_start(self) -> None:
        self.write_transcript(claude_lines(3, []))
        activity, _ = hook.scan_transcript(str(self.transcript), 10_000_000)
        self.assertEqual(activity.assistant_turns, 3)

    def test_missing_transcript_is_silent(self) -> None:
        activity, position = hook.scan_transcript(str(self.container / "absent.jsonl"), 42)
        self.assertEqual(activity.assistant_turns, 0)
        self.assertEqual(position, 42)


class DueRuleTest(HookFixture):
    def setUp(self) -> None:
        super().setUp()
        self.settings = hook.DEFAULTS["harvest"]

    def activity(self, turns: int, files: int, captures: int = 0) -> hook.Activity:
        activity = hook.Activity()
        activity.assistant_turns = turns
        activity.edited_paths = {f"file{index}.c" for index in range(files)}
        activity.captures = captures
        return activity

    def test_below_both_thresholds_is_not_due(self) -> None:
        self.assertFalse(hook.is_due(self.activity(11, 4), {}, self.settings, False))

    def test_turn_threshold_alone_is_due(self) -> None:
        self.assertTrue(hook.is_due(self.activity(12, 0), {}, self.settings, False))

    def test_edit_threshold_alone_is_due(self) -> None:
        self.assertTrue(hook.is_due(self.activity(0, 5), {}, self.settings, False))

    def test_a_capture_since_the_watermark_clears_the_debt(self) -> None:
        self.assertFalse(hook.is_due(self.activity(30, 9, captures=1), {}, self.settings, False))

    def test_precompact_uses_the_lower_thresholds(self) -> None:
        self.assertFalse(hook.is_due(self.activity(6, 0), {}, self.settings, False))
        self.assertTrue(hook.is_due(self.activity(6, 0), {}, self.settings, True))

    def test_cooldown_suppresses_a_second_signal(self) -> None:
        entry = {"last_signal_at": hook.utc_now().isoformat(timespec="seconds")}
        self.assertFalse(hook.is_due(self.activity(40, 9), entry, self.settings, False))


class RecallGateTest(HookFixture):
    def setUp(self) -> None:
        super().setUp()
        self.settings = hook.DEFAULTS["recall"]

    def test_substantive_prompt_passes(self) -> None:
        self.assertTrue(
            hook.worth_recalling("How does the CCCD bit field decode on this stack?", self.settings)
        )

    def test_short_prompt_is_skipped(self) -> None:
        self.assertFalse(hook.worth_recalling("what now?", self.settings))

    def test_slash_command_is_skipped(self) -> None:
        self.assertFalse(hook.worth_recalling("/second-brain-harvest please run it now", self.settings))

    def test_acknowledgement_is_skipped(self) -> None:
        padded = "Go ahead" + " " * 40
        self.assertFalse(hook.worth_recalling(padded, self.settings))


class PromptContractTest(HookFixture):
    """The installed clients send `prompt`; the published reference says `user_prompt`."""

    QUESTION = "How does the CCCD bit field decode on this stack, and why?"

    def queried(self, payload: dict) -> str | None:
        seen: list[str] = []
        with mock.patch.object(hook, "recall_block", side_effect=lambda r, q, s: seen.append(q) or ""):
            hook.recall_sections(self.root, payload, hook.DEFAULTS["recall"])
        return seen[0] if seen else None

    def test_claude_prompt_field_reaches_recall(self) -> None:
        payload = self.payload("UserPromptSubmit", prompt=self.QUESTION, source="user")
        self.assertEqual(self.queried(payload), self.QUESTION)

    def test_codex_prompt_field_reaches_recall(self) -> None:
        payload = {"hook_event_name": "UserPromptSubmit", "turn_id": "t1", "prompt": self.QUESTION}
        self.assertEqual(self.queried(payload), self.QUESTION)

    def test_documented_user_prompt_field_still_works(self) -> None:
        payload = self.payload("UserPromptSubmit", user_prompt=self.QUESTION)
        self.assertEqual(self.queried(payload), self.QUESTION)

    def test_automated_prompt_sources_are_skipped(self) -> None:
        for source in ("system", "loop_wakeup", "schedule_wakeup", "poll_event"):
            payload = self.payload("UserPromptSubmit", prompt=self.QUESTION, source=source)
            self.assertIsNone(self.queried(payload), source)

    def test_sdk_authored_prompts_still_recall(self) -> None:
        payload = self.payload("UserPromptSubmit", prompt=self.QUESTION, source="sdk")
        self.assertEqual(self.queried(payload), self.QUESTION)


class DispatchTest(HookFixture):
    def test_stop_signals_once_and_advances_the_watermark(self) -> None:
        self.write_transcript(claude_lines(20, ["a.c", "b.c"]))
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.work)}):
            with mock.patch.object(sys, "stderr", stderr):
                first = self.dispatch(self.payload("Stop"))[0]
        self.assertEqual(first, 2)
        self.assertIn("SECOND BRAIN HARVEST DUE", stderr.getvalue())

        entry = self.ledger()["sessions"]["session-1"]
        self.assertEqual(entry["offset"], self.transcript.stat().st_size)
        self.assertEqual(entry["signals"], 1)

        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.work)}):
            second = self.dispatch(self.payload("Stop"))[0]
        self.assertEqual(second, 0)

    def test_stop_without_claude_falls_back_to_additional_context(self) -> None:
        self.write_transcript(claude_lines(20, []))
        with mock.patch.dict(os.environ, {}, clear=True):
            code, payload = self.dispatch(self.payload("Stop"))
        self.assertEqual(code, 0)
        self.assertIn("SECOND BRAIN HARVEST DUE", payload["hookSpecificOutput"]["additionalContext"])

    def test_plan_mode_never_harvests(self) -> None:
        self.write_transcript(claude_lines(30, []))
        code, payload = self.dispatch(self.payload("Stop", permission_mode="plan"))
        self.assertEqual(code, 0)
        self.assertIsNone(payload)

    def test_sessions_inside_the_vault_never_harvest(self) -> None:
        self.write_transcript(claude_lines(30, []))
        code, payload = self.dispatch(self.payload("Stop", cwd=str(self.root / "00-inbox")))
        self.assertEqual(code, 0)
        self.assertIsNone(payload)

    def test_subagent_payloads_are_ignored(self) -> None:
        self.write_transcript(claude_lines(30, []))
        code, payload = self.dispatch(self.payload("Stop", agent_type="Explore"))
        self.assertEqual(code, 0)
        self.assertIsNone(payload)

    def test_session_start_takes_a_watermark_without_signalling(self) -> None:
        self.write_transcript(claude_lines(30, []))
        code, _ = self.dispatch(self.payload("SessionStart", started_by="startup"))
        self.assertEqual(code, 0)
        entry = self.ledger()["sessions"]["session-1"]
        self.assertEqual(entry["offset"], self.transcript.stat().st_size)
        self.assertEqual(entry.get("signals", 0), 0)

    def test_unknown_event_is_ignored(self) -> None:
        self.write_transcript(claude_lines(30, []))
        code, payload = self.dispatch(self.payload("PostToolUse"))
        self.assertEqual(code, 0)
        self.assertIsNone(payload)


class ResilienceTest(HookFixture):
    def test_malformed_transcript_lines_do_not_raise(self) -> None:
        self.transcript.write_text("not json\n{\n", encoding="utf-8")
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.lines, 2)

    def test_malformed_stdin_exits_successfully(self) -> None:
        with mock.patch.object(sys, "stdin", io.StringIO("{oops")):
            self.assertEqual(hook.main(["--vault-root", str(self.root)]), 0)

    def test_an_invalid_vault_root_exits_successfully(self) -> None:
        with mock.patch.object(sys, "stdin", io.StringIO("{}")):
            self.assertEqual(hook.main(["--vault-root", str(self.container / "nope")]), 0)

    def test_a_missing_argument_exits_successfully(self) -> None:
        self.assertEqual(hook.main([]), 0)

    def test_corrupt_ledger_is_replaced_rather_than_fatal(self) -> None:
        path = self.root / hook.LEDGER_RELATIVE
        path.write_text("{ broken", encoding="utf-8")
        self.assertEqual(hook.read_ledger(path)["sessions"], {})

    def test_config_falls_back_to_defaults_when_unreadable(self) -> None:
        with mock.patch.object(hook.Path, "read_text", side_effect=OSError):
            self.assertEqual(hook.load_config()["harvest"]["assistant_turns"], 12)


class LedgerTest(HookFixture):
    def test_pruning_keeps_the_most_recent_sessions(self) -> None:
        path = self.root / hook.LEDGER_RELATIVE
        sessions = {
            f"s{index}": {"offset": index, "updated_at": f"2026-09-{index + 1:02d}T00:00:00+00:00"}
            for index in range(5)
        }
        hook.write_ledger(path, {"sessions": sessions}, 3)
        kept = hook.read_ledger(path)["sessions"]
        self.assertEqual(sorted(kept), ["s2", "s3", "s4"])

    def test_the_temporary_file_is_never_left_behind(self) -> None:
        path = self.root / hook.LEDGER_RELATIVE
        hook.write_ledger(path, {"sessions": {"s": {"updated_at": "x"}}}, 10)
        leftovers = list(path.parent.glob(f"{path.name}.tmp-*"))
        self.assertEqual(leftovers, [])


class TrustBoundaryTest(HookFixture):
    def test_an_injected_pack_carries_the_untrusted_evidence_fence(self) -> None:
        pack = "# Context pack: x\n\n## A note\n`40-knowledge/a.md`\n\nbody"
        with mock.patch.object(hook, "build_pack", return_value=pack):
            block = hook.recall_block(self.root, "a query", hook.DEFAULTS["recall"])
        self.assertIn("<second-brain-recall>", block)
        self.assertIn("</second-brain-recall>", block)
        self.assertIn(hook.TRUST_NOTICE, block)

    def test_an_empty_pack_injects_nothing(self) -> None:
        with mock.patch.object(hook, "build_pack", return_value="# Context pack: x\n"):
            self.assertEqual(hook.recall_block(self.root, "a query", hook.DEFAULTS["recall"]), "")

    def test_a_failing_pack_build_injects_nothing(self) -> None:
        with mock.patch.object(hook, "build_pack", side_effect=RuntimeError("cache locked")):
            self.assertEqual(hook.recall_block(self.root, "a query", hook.DEFAULTS["recall"]), "")


if __name__ == "__main__":
    unittest.main()
