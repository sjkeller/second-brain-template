"""Trigger, suppression, and safety tests for the session knowledge automation hook."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
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


def capture_line(call_id: str = "cap-1") -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": "mcp__second-brain__capture_note",
                        "input": {"title": "A draft", "content": "body"},
                    }
                ],
            },
        }
    )


def failed_result_line(call_id: str = "cap-1") -> str:
    return json.dumps(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": call_id, "is_error": True, "content": "nope"}
                ],
            },
        }
    )


def skill_line(skill: str = "second-brain-harvest", call_id: str = "skill-1") -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": "Skill",
                        "input": {"skill": skill},
                    }
                ],
            },
        }
    )


def vault_status_line(call_id: str = "status-1") -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": "mcp__second-brain__vault_status",
                        "input": {},
                    }
                ],
            },
        }
    )


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

    def dispatch(self, payload: dict, recall: str = "") -> tuple[int, dict | None]:
        code, raw = self.dispatch_bytes(payload, recall)
        text = raw.decode("utf-8").strip()
        return code, json.loads(text) if text else None

    def dispatch_bytes(self, payload: dict, recall: str = "") -> tuple[int, bytes]:
        stream = io.BytesIO()
        with mock.patch.object(hook, "recall_block", return_value=recall):
            with mock.patch.object(sys, "stdout", SimpleNamespace(buffer=stream)):
                code = hook.dispatch(self.root, payload)
        return code, stream.getvalue()

    def state(self, session_id: str = "session-1") -> dict:
        return hook.read_state(hook.state_file(self.root, session_id))


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

    def activity(self, turns: int, files: int) -> hook.Activity:
        activity = hook.Activity()
        activity.assistant_turns = turns
        activity.edits = files
        return activity

    def test_below_both_thresholds_is_not_due(self) -> None:
        self.assertFalse(hook.is_due(self.activity(11, 4), {}, self.settings, False))

    def test_turn_threshold_alone_is_due(self) -> None:
        self.assertTrue(hook.is_due(self.activity(12, 0), {}, self.settings, False))

    def test_edit_threshold_alone_is_due(self) -> None:
        self.assertTrue(hook.is_due(self.activity(0, 5), {}, self.settings, False))

    def test_the_due_rule_no_longer_vetoes_on_captures(self) -> None:
        activity = self.activity(30, 9)
        activity.captures = 1
        self.assertTrue(hook.is_due(activity, {}, self.settings, False))

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


class HarvestWindowTest(HookFixture):
    """A harvest ends one activity window and opens the next; it is not a permanent veto."""

    def test_work_before_a_capture_is_not_counted(self) -> None:
        self.write_transcript(claude_lines(20, ["a.c", "b.c"]) + [capture_line()])
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 0)
        self.assertEqual(activity.edits, 0)
        self.assertIsNotNone(activity.window_offset)

    def test_work_after_a_capture_is_counted(self) -> None:
        self.write_transcript(
            claude_lines(20, ["a.c"]) + [capture_line()] + claude_lines(7, ["c.c", "d.c"])
        )
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 7)
        self.assertEqual(activity.edits, 2)

    def test_enough_work_after_a_capture_becomes_due_again(self) -> None:
        self.write_transcript(claude_lines(5, []) + [capture_line()] + claude_lines(30, []))
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertTrue(hook.is_due(activity, {}, hook.DEFAULTS["harvest"], False))

    def test_a_failed_capture_does_not_end_the_window(self) -> None:
        self.write_transcript(
            claude_lines(20, []) + [capture_line("cap-x"), failed_result_line("cap-x")]
        )
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 21)
        self.assertIsNone(activity.window_offset)
        self.assertTrue(hook.is_due(activity, {}, hook.DEFAULTS["harvest"], False))

    def test_the_last_successful_capture_wins(self) -> None:
        self.write_transcript(
            claude_lines(3, [])
            + [capture_line("cap-1")]
            + claude_lines(4, [])
            + [capture_line("cap-2")]
            + claude_lines(2, [])
        )
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 2)

    def test_dispatch_persists_the_post_capture_watermark(self) -> None:
        self.write_transcript(claude_lines(20, []) + [capture_line()])
        code, payload = self.dispatch(self.payload("Stop"))
        self.assertEqual(code, 0)
        self.assertIsNone(payload)
        offset = self.state()["offset"]
        self.assertGreater(offset, 0)

        self.write_transcript(claude_lines(20, []) + [capture_line()] + claude_lines(30, []))
        activity, _ = hook.scan_transcript(str(self.transcript), offset)
        self.assertEqual(activity.assistant_turns, 30)


class NullHarvestWindowTest(HookFixture):
    """A harvest that captures nothing still closes its window.

    Its own turns must not be counted towards the next signal, or a quiet session re-fires
    the hook on the turns the previous harvest spent reporting that there was nothing to do.
    """

    def test_a_skill_invocation_closes_the_window(self) -> None:
        self.write_transcript(claude_lines(20, []) + [skill_line()])
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 0)
        self.assertIsNotNone(activity.window_offset)

    def test_a_null_harvest_is_not_immediately_due_again(self) -> None:
        self.write_transcript(
            claude_lines(30, []) + [skill_line()] + claude_lines(4, []) + [vault_status_line()]
        )
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 0)
        self.assertFalse(hook.is_due(activity, {}, hook.DEFAULTS["harvest"], False))

    def test_the_closing_vault_status_wins_over_the_invocation(self) -> None:
        self.write_transcript(
            claude_lines(3, []) + [skill_line()] + claude_lines(6, []) + [vault_status_line()]
        )
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 0)

    def test_work_after_a_null_harvest_is_counted(self) -> None:
        self.write_transcript(
            claude_lines(20, []) + [skill_line()] + claude_lines(30, ["a.c", "b.c"])
        )
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 30)
        self.assertEqual(activity.edits, 2)
        self.assertTrue(hook.is_due(activity, {}, hook.DEFAULTS["harvest"], False))

    def test_an_unrelated_skill_does_not_close_the_window(self) -> None:
        self.write_transcript(claude_lines(20, []) + [skill_line("code-review")])
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertEqual(activity.assistant_turns, 21)
        self.assertIsNone(activity.window_offset)

    def test_editing_the_hook_itself_does_not_close_the_window(self) -> None:
        edit = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "edit-1",
                            "name": "Edit",
                            "input": {
                                "file_path": "agent_hook.py",
                                "new_string": 'SKILL_NAME = "second-brain-harvest"',
                            },
                        }
                    ],
                },
            }
        )
        self.write_transcript(claude_lines(20, []) + [edit])
        activity, _ = hook.scan_transcript(str(self.transcript), 0)
        self.assertIsNone(activity.window_offset)
        self.assertEqual(activity.edits, 1)


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


class OutputEncodingTest(HookFixture):
    """Hook stdout is a byte protocol, not a locale-encoded text stream."""

    JAPANESE = "ハートレートの設定"

    def test_non_ascii_recall_survives_a_cp1252_stdout(self) -> None:
        pack = "\n".join(("<second-brain-recall>", self.JAPANESE, "</second-brain-recall>"))
        code, raw = self.dispatch_bytes(self.payload("SessionStart"), recall=pack)
        self.assertEqual(code, 0)
        raw.decode("ascii")
        restored = json.loads(raw.decode("utf-8"))
        self.assertIn(self.JAPANESE, restored["hookSpecificOutput"]["additionalContext"])

    def test_emit_writes_bytes_not_text(self) -> None:
        stream = io.BytesIO()
        with mock.patch.object(sys, "stdout", SimpleNamespace(buffer=stream)):
            hook.emit("SessionStart", self.JAPANESE)
        self.assertTrue(stream.getvalue().endswith(b"\n"))
        stream.getvalue().decode("ascii")


class DeliveryTest(HookFixture):
    """A signal is only spent on an event whose client contract can carry it."""

    def as_claude(self, payload: dict) -> tuple[int, dict | None]:
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.work)}):
            return self.dispatch(payload)

    def as_codex(self, payload: dict) -> tuple[int, dict | None]:
        with mock.patch.dict(os.environ, {}, clear=True):
            return self.dispatch(payload)

    def directive(self, payload: dict | None) -> str:
        return "" if payload is None else payload["hookSpecificOutput"].get("additionalContext", "")

    def test_claude_stop_delivers_by_additional_context_and_exits_zero(self) -> None:
        self.write_transcript(claude_lines(20, ["a.c", "b.c"]))
        code, out = self.as_claude(self.payload("Stop"))
        self.assertEqual(code, 0)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "Stop")
        self.assertIn("SECOND BRAIN HARVEST DUE", self.directive(out))

        entry = self.state()
        self.assertEqual(entry["offset"], self.transcript.stat().st_size)
        self.assertEqual(entry["signals"], 1)
        self.assertFalse(entry["pending_harvest"])

        self.assertIsNone(self.as_claude(self.payload("Stop"))[1])

    def test_codex_stop_holds_the_signal_instead_of_emitting(self) -> None:
        self.write_transcript(claude_lines(20, []))
        code, out = self.as_codex(self.payload("Stop"))
        self.assertEqual(code, 0)
        self.assertIsNone(out)

        entry = self.state()
        self.assertTrue(entry["pending_harvest"])
        self.assertEqual(entry.get("signals", 0), 0)
        self.assertNotIn("last_signal_at", entry)
        self.assertEqual(entry.get("offset", 0), 0)

    def test_precompact_holds_the_signal_in_both_clients(self) -> None:
        self.write_transcript(claude_lines(8, []))
        for run in (self.as_claude, self.as_codex):
            self.assertIsNone(run(self.payload("PreCompact", trigger="auto"))[1])
            self.assertTrue(self.state()["pending_harvest"])

    def test_a_held_signal_is_delivered_on_the_next_prompt(self) -> None:
        self.write_transcript(claude_lines(20, []))
        self.as_codex(self.payload("Stop"))
        code, out = self.as_codex(self.payload("UserPromptSubmit", prompt="ok"))
        self.assertEqual(code, 0)
        self.assertIn("SECOND BRAIN HARVEST DUE", self.directive(out))
        entry = self.state()
        self.assertFalse(entry["pending_harvest"])
        self.assertEqual(entry["signals"], 1)

    def test_a_held_signal_survives_the_cooldown_that_never_started(self) -> None:
        self.write_transcript(claude_lines(20, []))
        self.as_codex(self.payload("Stop"))
        self.as_codex(self.payload("Stop"))
        self.assertIn(
            "SECOND BRAIN HARVEST DUE",
            self.directive(self.as_codex(self.payload("UserPromptSubmit", prompt="x"))[1]),
        )

    def test_a_capture_settles_a_held_signal(self) -> None:
        self.write_transcript(claude_lines(20, []))
        self.as_codex(self.payload("Stop"))
        self.assertTrue(self.state()["pending_harvest"])

        self.write_transcript(claude_lines(20, []) + [capture_line()])
        code, out = self.as_codex(self.payload("UserPromptSubmit", prompt="x"))
        self.assertEqual(code, 0)
        self.assertIsNone(out)
        self.assertFalse(self.state()["pending_harvest"])

    def test_a_held_signal_is_not_delivered_in_plan_mode(self) -> None:
        self.write_transcript(claude_lines(20, []))
        self.as_codex(self.payload("Stop"))
        out = self.as_claude(self.payload("UserPromptSubmit", prompt="x", permission_mode="plan"))[1]
        self.assertIsNone(out)

    def test_an_extended_turn_is_left_alone(self) -> None:
        self.write_transcript(claude_lines(30, []))
        code, out = self.as_claude(self.payload("Stop", stop_hook_active=True))
        self.assertEqual(code, 0)
        self.assertIsNone(out)
        self.assertFalse(self.state().get("pending_harvest", False))

    def test_an_unsaved_watermark_suppresses_the_signal(self) -> None:
        self.write_transcript(claude_lines(30, []))
        with mock.patch.object(hook, "write_state", return_value=False):
            code, out = self.as_claude(self.payload("Stop"))
        self.assertEqual(code, 0)
        self.assertIsNone(out)

    def test_the_signal_returns_once_state_can_be_saved_again(self) -> None:
        self.write_transcript(claude_lines(30, []))
        with mock.patch.object(hook, "write_state", return_value=False):
            self.as_claude(self.payload("Stop"))
        self.assertIn(
            "SECOND BRAIN HARVEST DUE",
            self.directive(self.as_claude(self.payload("Stop"))[1]),
        )

    def test_delivery_matrix_matches_the_installed_clients(self) -> None:
        for event, claude, expected in (
            ("SessionStart", True, True),
            ("SessionStart", False, True),
            ("UserPromptSubmit", True, True),
            ("UserPromptSubmit", False, True),
            ("Stop", True, True),
            ("Stop", False, False),
            ("PreCompact", True, False),
            ("PreCompact", False, False),
        ):
            self.assertEqual(hook.delivers_to_model(event, claude), expected, (event, claude))


class DispatchTest(HookFixture):
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
        entry = self.state()
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

    def test_corrupt_state_is_replaced_rather_than_fatal(self) -> None:
        path = hook.state_file(self.root, "session-1")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ broken", encoding="utf-8")
        self.assertEqual(hook.read_state(path), {})

    def test_config_falls_back_to_defaults_when_unreadable(self) -> None:
        with mock.patch.object(hook.Path, "read_text", side_effect=OSError):
            self.assertEqual(hook.load_config()["harvest"]["assistant_turns"], 12)


class StateFileTest(HookFixture):
    """Per-session files, so concurrent sessions cannot lose each other's watermarks."""

    def test_two_sessions_do_not_clobber_each_other(self) -> None:
        first = hook.state_file(self.root, "alpha")
        second = hook.state_file(self.root, "beta")
        self.assertNotEqual(first, second)
        self.assertTrue(hook.write_state(first, {"offset": 11}))
        self.assertTrue(hook.write_state(second, {"offset": 22}))
        self.assertEqual(hook.read_state(first)["offset"], 11)
        self.assertEqual(hook.read_state(second)["offset"], 22)

    def test_a_concurrent_writer_working_from_a_stale_snapshot_loses_nothing(self) -> None:
        mine = hook.state_file(self.root, "mine")
        theirs = hook.state_file(self.root, "theirs")
        hook.write_state(mine, {"offset": 1})
        stale = hook.read_state(theirs)
        hook.write_state(mine, {"offset": 2})
        stale["offset"] = 99
        hook.write_state(theirs, stale)
        self.assertEqual(hook.read_state(mine)["offset"], 2)
        self.assertEqual(hook.read_state(theirs)["offset"], 99)

    def test_unsafe_session_ids_stay_inside_the_state_directory(self) -> None:
        path = hook.state_file(self.root, "../../etc/passwd")
        self.assertEqual(path.parent, self.root / hook.STATE_RELATIVE)
        self.assertNotIn("/", path.name.replace(".json", ""))

    def test_distinct_long_ids_never_share_a_file(self) -> None:
        prefix = "s" * 120
        self.assertNotEqual(
            hook.state_file(self.root, prefix + "one"), hook.state_file(self.root, prefix + "two")
        )

    def test_pruning_removes_only_stale_files(self) -> None:
        directory = self.root / hook.STATE_RELATIVE
        fresh = hook.state_file(self.root, "fresh")
        stale = hook.state_file(self.root, "stale")
        hook.write_state(fresh, {"offset": 1})
        hook.write_state(stale, {"offset": 1})
        old = time.time() - 40 * 86400
        os.utime(stale, (old, old))
        hook.prune_state(directory, 30)
        self.assertTrue(fresh.is_file())
        self.assertFalse(stale.is_file())

    def test_pruning_a_missing_directory_is_silent(self) -> None:
        hook.prune_state(self.root / "nowhere", 30)

    def test_the_temporary_file_is_never_left_behind(self) -> None:
        path = hook.state_file(self.root, "session-1")
        hook.write_state(path, {"offset": 3})
        self.assertEqual(list(path.parent.glob("*.tmp-*")), [])

    def test_an_unwritable_state_file_reports_failure(self) -> None:
        path = hook.state_file(self.root, "session-1")
        with mock.patch.object(hook.Path, "write_text", side_effect=PermissionError):
            self.assertFalse(hook.write_state(path, {"offset": 1}))


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
