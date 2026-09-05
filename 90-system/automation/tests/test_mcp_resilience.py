"""Failure-injection tests against the actual stdio process, never a private vault."""

from __future__ import annotations

import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest import mock

from test_mcp_server import McpVaultFixture, SERVER_SCRIPT, mcp


class StdioProcess:
    def __init__(self, root, script=SERVER_SCRIPT, arguments=(), env=None):
        self.process = subprocess.Popen(
            [sys.executable, str(script), "--vault-root", str(root), *arguments],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        )
        self.responses = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            self.responses.put(json.loads(line.decode("utf-8")))

    def send(self, request):
        self.process.stdin.write(json.dumps(request).encode("utf-8") + b"\n")
        self.process.stdin.flush()

    def call(self, identity, name, arguments=None):
        self.send({"jsonrpc": "2.0", "id": identity, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments or {}}})

    def receive(self, timeout=5):
        return self.responses.get(timeout=timeout)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=10)
        self.reader.join(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


class ResilienceFixture(McpVaultFixture):
    def tearDown(self):
        self.doCleanups()  # Close processes/SQLite before Windows removes the fixture.
        super().tearDown()


class TransportResilienceTests(ResilienceFixture):
    def test_diagnostic_sink_failure_does_not_escape(self):
        job = mcp.ToolJob({"id": 1, "params": {"name": "read_note"}})
        with mock.patch.object(mcp.sys, "stderr") as stderr:
            stderr.write.side_effect = OSError("closed diagnostic pipe")
            mcp.diagnostic("tool_error", job)

    def start(self, **kwargs):
        process = StdioProcess(self.root, **kwargs)
        self.addCleanup(process.close)
        return process

    def stalled_script(self, command="command_query", delay=2):
        """Inject slow filesystem-like work only into this test's copied vault module."""
        script = self.root / "90-system/automation/mcp_server.py"
        shutil.copy2(SERVER_SCRIPT, script)
        vault_script = script.with_name("vault.py")
        with vault_script.open("a", encoding="utf-8") as stream:
            stream.write(
                f"\n_original_command = {command}\n"
                f"def {command}(*args, **kwargs):\n"
                "    import time\n"
                "    Path(__file__).with_suffix('.started').touch()\n"
                f"    time.sleep({delay})\n"
                "    Path(__file__).with_suffix('.completed').touch()\n"
                "    return _original_command(*args, **kwargs)\n"
            )
        return script

    def wait_started(self):
        deadline = time.monotonic() + 5
        while not (self.root / "90-system/automation/vault.started").exists():
            if time.monotonic() > deadline:
                self.fail("test worker did not start")
            time.sleep(0.01)

    def test_unicode_read_uses_utf8_even_with_windows_legacy_pipe_encoding(self):
        expected = "Grüße — 知識 🧠"
        self.write("00-inbox/Unicode.md", "# Unicode\n\n" + expected)
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "read_note", "arguments": {"path": "00-inbox/Unicode.md"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        ]
        process = subprocess.run(
            [sys.executable, str(SERVER_SCRIPT), "--vault-root", str(self.root)],
            input=b"".join(json.dumps(item).encode("utf-8") + b"\n" for item in requests),
            capture_output=True, timeout=10,
            env={**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"},
        )
        self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", errors="replace"))
        responses = {item["id"]: item for item in map(json.loads, process.stdout.decode("utf-8").splitlines())}
        self.assertIn(expected, responses[1]["result"]["structuredContent"]["content"])
        self.assertEqual(responses[2]["result"], {})

    def test_deep_json_does_not_disconnect_and_next_ping_succeeds(self):
        process = subprocess.run(
            [sys.executable, str(SERVER_SCRIPT), "--vault-root", str(self.root)],
            input=b"[" * 2000 + b"0" + b"]" * 2000 + b'\n{"jsonrpc":"2.0","id":2,"method":"ping"}\n',
            capture_output=True, timeout=10,
        )
        self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", errors="replace"))
        responses = list(map(json.loads, process.stdout.splitlines()))
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual(responses[1]["id"], 2)

    def test_ping_is_responsive_while_retrieval_is_stalled(self):
        process = self.start(script=self.stalled_script())
        process.call(1, "search_vault", {"query": "retrieval"})
        self.wait_started()
        process.send({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        self.assertEqual(process.receive(timeout=1)["id"], 2)
        self.assertEqual(process.receive()["id"], 1)

    def test_read_deadline_preserves_connection_and_next_read_succeeds(self):
        process = self.start(script=self.stalled_script(delay=5), arguments=("--read-timeout-seconds", "0.5"))
        process.call(1, "search_vault", {"query": "retrieval"})
        response = process.receive(timeout=3)
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"]["structuredContent"]["error"], "retrieval_timeout")
        process.call(2, "read_note", {"path": "Home.md"})
        self.assertFalse(process.receive()["result"]["isError"])
        self.assertIsNone(process.process.poll())

    def test_active_read_cancellation_stops_work_without_a_late_response(self):
        process = self.start(script=self.stalled_script(delay=5))
        process.call(1, "search_vault", {"query": "retrieval"})
        self.wait_started()
        process.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}})
        process.call(2, "read_note", {"path": "Home.md"})
        self.assertEqual(process.receive(timeout=2)["id"], 2)
        self.assertTrue(process.responses.empty())

    def test_cancelled_queued_capture_never_writes(self):
        process = self.start(script=self.stalled_script(delay=5))
        process.call(1, "search_vault", {"query": "retrieval"})
        self.wait_started()
        process.call(2, "capture_note", {"title": "Cancelled capture", "content": "Must not be saved."})
        for identity in (2, 1):
            process.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": identity}})
        process.call(3, "read_note", {"path": "Home.md"})
        self.assertEqual(process.receive(timeout=2)["id"], 3)
        self.assertFalse((self.root / "00-inbox/Cancelled capture.md").exists())

    def test_started_capture_finishes_transaction_after_cancel_and_read_deadline(self):
        process = self.start(script=self.stalled_script(command="command_new", delay=0.6),
                             arguments=("--read-timeout-seconds", "0.3"))
        process.call(1, "capture_note", {"title": "Accepted capture", "content": "Save exactly once."})
        self.wait_started()
        process.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}})
        process.send({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        self.assertEqual(process.receive(timeout=0.4)["id"], 2)
        deadline = time.monotonic() + 5
        while not (self.root / "00-inbox/Accepted capture.md").exists():
            if time.monotonic() > deadline:
                self.fail("admitted capture did not complete")
            time.sleep(0.02)
        process.call(3, "read_note", {"path": "00-inbox/MOC - Inbox.md"})
        response = process.receive()
        self.assertEqual(response["id"], 3)
        self.assertIn("Accepted capture", response["result"]["structuredContent"]["content"])
        self.assertFalse((self.root / "90-system/indexes/.mcp-write.lock").exists())

    def test_worker_crash_is_a_tool_error_not_a_disconnect(self):
        script = self.stalled_script(delay=0)
        vault_script = script.with_name("vault.py")
        with vault_script.open("a", encoding="utf-8") as stream:
            stream.write("\ndef command_query(*args, **kwargs):\n    raise SystemExit(17)\n")
        process = self.start(script=script)
        process.call(1, "search_vault", {"query": "private-query-must-not-be-logged"})
        response = process.receive()
        self.assertEqual(response["result"]["structuredContent"]["error"], "tool_worker_failed")
        process.call(2, "read_note", {"path": "Home.md"})
        self.assertFalse(process.receive()["result"]["isError"])
        process.process.stdin.close()
        process.process.wait(timeout=5)
        diagnostics = process.process.stderr.read().decode("utf-8")
        self.assertIn("tool_error", diagnostics)
        self.assertNotIn("private-query", diagnostics)
        self.assertNotIn(str(self.root), diagnostics)

    def test_invalid_frames_are_contained_and_following_ping_works(self):
        frames = [b"\xff", b'{"bad":NaN}', b'{"bad":1e999}', b'{"bad":"\\ud800"}',
                  b"x" * (mcp.MAX_REQUEST_BYTES + 10)]
        process = subprocess.run(
            [sys.executable, str(SERVER_SCRIPT), "--vault-root", str(self.root)],
            input=b"\n".join(frames) + b'\n{"jsonrpc":"2.0","id":2,"method":"ping"}\n',
            capture_output=True, timeout=10,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = list(map(json.loads, process.stdout.splitlines()))
        self.assertEqual(len(responses), len(frames) + 1)
        self.assertTrue(all(item["error"]["code"] == -32700 for item in responses[:-1]))
        self.assertEqual(responses[-1]["id"], 2)

    def test_parent_termination_does_not_leave_read_worker_running(self):
        process = self.start(script=self.stalled_script(delay=1))
        process.call(1, "search_vault", {"query": "retrieval"})
        self.wait_started()
        process.process.terminate()  # Abrupt client disconnect, not orderly MCP cancellation.
        process.process.wait(timeout=5)
        time.sleep(1.2)
        self.assertFalse((self.root / "90-system/automation/vault.completed").exists())
        next_process = self.start()
        next_process.call(2, "search_vault", {"query": "retrieval"})
        self.assertFalse(next_process.receive()["result"]["isError"])

    def test_queue_is_bounded_and_control_messages_bypass_it(self):
        process = self.start(script=self.stalled_script(delay=5))
        process.call(1, "search_vault", {"query": "retrieval"})
        self.wait_started()
        for identity in range(2, mcp.MAX_PENDING_TOOLS + 2):
            process.call(identity, "read_note", {"path": "Home.md"})
        response = process.receive(timeout=2)
        self.assertEqual(response["id"], mcp.MAX_PENDING_TOOLS + 1)
        self.assertEqual(response["result"]["structuredContent"]["error"], "server_busy")
        process.send({"jsonrpc": "2.0", "id": "health", "method": "ping"})
        self.assertEqual(process.receive(timeout=1)["id"], "health")
        for identity in range(1, mcp.MAX_PENDING_TOOLS + 1):
            process.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": identity}})

    def test_simultaneous_clients_share_a_cold_cache_without_partial_schema(self):
        processes = [self.start() for _ in range(3)]
        for identity, process in enumerate(processes):
            process.call(identity, "search_vault", {"query": "retrieval"})
        for identity, process in enumerate(processes):
            response = process.receive(timeout=5)
            payload = response["result"]["structuredContent"]
            if response["result"]["isError"]:
                self.assertEqual(payload["error"], "cache_busy")
                process.call(identity + 10, "search_vault", {"query": "retrieval"})
                response = process.receive()
            self.assertFalse(response["result"]["isError"], response)
            self.assertGreater(response["result"]["structuredContent"]["result_count"], 0)
        with mcp.vault.open_cache(self.root) as cache:
            self.assertEqual(len(cache.notes()), len(mcp.vault.scan_notes(self.root)))

    def test_modern_timeout_result_retains_protocol_envelope(self):
        process = self.start(script=self.stalled_script(delay=5), arguments=("--read-timeout-seconds", "0.5"))
        process.send({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "search_vault", "arguments": {"query": "retrieval"},
            "_meta": {"io.modelcontextprotocol/protocolVersion": mcp.MODERN_PROTOCOL},
        }})
        result = process.receive(timeout=3)["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["structuredContent"]["error"], "retrieval_timeout")
        self.assertEqual(result["_meta"]["io.modelcontextprotocol/serverInfo"]["version"], mcp.SERVER_VERSION)

    def test_response_limit_does_not_disconnect(self):
        # A deliberately inflated handler response models a graph/status fan-out.
        script = self.stalled_script(delay=0)
        with script.with_name("vault.py").open("a", encoding="utf-8") as stream:
            stream.write("\ndef command_query(*args, **kwargs):\n"
                         f"    emit({{'oversized': 'x' * {mcp.MAX_RESPONSE_BYTES}}}, True)\n    return 0\n")
        process = self.start(script=script)
        process.call(1, "search_vault", {"query": "retrieval"})
        self.assertEqual(process.receive()["error"]["code"], -32603)
        process.call(2, "read_note", {"path": "Home.md"})
        self.assertFalse(process.receive()["result"]["isError"])

    def test_closed_output_pipe_exits_without_shutdown_traceback(self):
        process = subprocess.Popen(
            [sys.executable, str(SERVER_SCRIPT), "--vault-root", str(self.root)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            process.stdout.close()
            process.stdin.write(b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
            process.stdin.flush()
            returncode = process.wait(timeout=5)
            diagnostics = process.stderr.read()
            self.assertEqual(returncode, 0, diagnostics.decode("utf-8", errors="replace"))
            self.assertEqual(diagnostics, b"")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            process.stdin.close()
            process.stderr.close()


class CacheResilienceTests(ResilienceFixture):
    def test_sync_failure_rolls_back_and_releases_the_writer_lock(self):
        cache = mcp.vault.open_cache(self.root)
        self.addCleanup(cache.close)
        original = cache.connection.execute("SELECT sha256 FROM docs WHERE path='Home.md'").fetchone()[0]
        home = self.root / "Home.md"
        home.write_text(home.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")
        self.write("zz-bad.md", "bad")
        (self.root / "zz-bad.md").write_bytes(b"\xff")
        with self.assertRaises(UnicodeDecodeError):
            cache.sync()
        self.assertFalse(cache.connection.in_transaction)
        other = sqlite3.connect(cache.path, timeout=0.05)
        try:
            other.execute("BEGIN IMMEDIATE")
            self.assertEqual(other.execute("SELECT sha256 FROM docs WHERE path='Home.md'").fetchone()[0], original)
        finally:
            other.close()

    def test_failed_open_closes_connection_without_waiting_for_garbage_collection(self):
        constructed = []
        original = mcp.vault.VaultCache
        def remember(*args, **kwargs):
            cache = original(*args, **kwargs)
            constructed.append(cache)
            self.addCleanup(cache.close)
            return cache
        with mock.patch.object(mcp.vault, "VaultCache", side_effect=remember), \
                mock.patch.object(original, "sync", side_effect=OSError("simulated sync race")):
            with self.assertRaises(OSError):
                mcp.vault.open_cache(self.root)
        self.assertEqual(len(constructed), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            constructed[0].connection.execute("SELECT 1")

    def test_busy_cache_returns_retryable_error_then_recovers_without_reconnect(self):
        cache = mcp.vault.open_cache(self.root)
        cache.close()
        self.write("00-inbox/New.md", "# New\n\nRetrieval evidence.")
        connection = sqlite3.connect(self.root / mcp.vault.CACHE_RELATIVE)
        self.addCleanup(connection.close)
        connection.execute("BEGIN IMMEDIATE")
        start = time.monotonic()
        result = self.call("search_vault", {"query": "retrieval"})
        self.assertLess(time.monotonic() - start, 2.5)
        self.assertEqual(result["structuredContent"]["error"], "cache_busy")
        self.assertTrue(result["structuredContent"]["retryable"])
        connection.rollback()
        self.assertFalse(self.call("search_vault", {"query": "retrieval"})["isError"])

    def test_corrupt_cache_is_reported_without_deleting_it_or_blocking_exact_reads(self):
        path = self.root / mcp.vault.CACHE_RELATIVE
        path.write_bytes(b"not a sqlite database")
        result = self.call("search_vault", {"query": "retrieval"})
        self.assertEqual(result["structuredContent"]["error"], "cache_unavailable")
        self.assertEqual(path.read_bytes(), b"not a sqlite database")
        self.assertFalse(self.call("read_note", {"path": "Home.md"})["isError"])

    def test_schema_migration_failure_preserves_old_schema_and_closes_connection(self):
        with mcp.vault.open_cache(self.root) as cache:
            original_count = len(cache.notes())
        real_connect = sqlite3.connect
        connections = []
        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, *args, **kwargs):
                if sql.strip().startswith("CREATE TABLE postings"):
                    raise sqlite3.OperationalError("simulated migration failure")
                return super().execute(sql, *args, **kwargs)
        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs, factory=FailingConnection)
            connections.append(connection)
            self.addCleanup(connection.close)
            return connection
        with mock.patch.object(mcp.vault.sqlite3, "connect", side_effect=connect), \
                mock.patch.object(mcp.vault, "SCHEMA_VERSION", mcp.vault.SCHEMA_VERSION + 1):
            with self.assertRaises(sqlite3.OperationalError):
                mcp.vault.open_cache(self.root)
        with self.assertRaises(sqlite3.ProgrammingError):
            connections[0].execute("SELECT 1")
        with mcp.vault.open_cache(self.root) as cache:
            self.assertEqual(len(cache.notes()), original_count)

    def test_query_failure_also_closes_an_already_open_cache(self):
        cache = mcp.vault.open_cache(self.root)
        self.addCleanup(cache.close)
        with mock.patch.object(mcp.vault, "open_cache", return_value=cache), \
                mock.patch.object(mcp.vault, "rank", side_effect=RuntimeError("simulated query failure")):
            with self.assertRaises(RuntimeError):
                mcp.vault.command_query(self.root, "retrieval", mcp.vault.QueryOptions(), True)
        with self.assertRaises(sqlite3.ProgrammingError):
            cache.connection.execute("SELECT 1")
