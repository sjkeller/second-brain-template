"""Tests for the vault CLI.

Run with:  py -m unittest discover -s 90-system/automation/tests -v
"""

import contextlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "vault.py"
SPEC = importlib.util.spec_from_file_location("vault_tools", SCRIPT)
vault = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = vault
SPEC.loader.exec_module(vault)


TODAY = date.today().isoformat()


def note_text(note_id, note_type, title, body="", status="active", extra=""):
    return (
        f"---\nid: {note_id}\ntype: {note_type}\nstatus: {status}\n"
        f"created: 2026-01-01\nupdated: {TODAY}\n{extra}---\n\n# {title}\n\n{body}\n"
    )


def run(function, *args, **kwargs):
    """Call a command function and return (exit_code, parsed_json)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = function(*args, **kwargs)
    return code, json.loads(buffer.getvalue())


class FrontmatterTests(unittest.TestCase):
    def test_block_list_and_scalars(self):
        metadata, body = vault.parse_frontmatter(
            "---\nid: alpha\ntype: concept\ntags:\n  - one\n  - two\n---\n# Alpha\nSee [[Folder/Beta|Beta]]."
        )
        self.assertEqual(metadata["id"], "alpha")
        self.assertEqual(metadata["tags"], ["one", "two"])
        self.assertIn("# Alpha", body)
        self.assertEqual(vault.extract_links(body), ["Folder/Beta"])

    def test_inline_list(self):
        metadata, _ = vault.parse_frontmatter("---\ntags: [alpha, beta]\naliases: []\n---\n# X")
        self.assertEqual(metadata["tags"], ["alpha", "beta"])
        self.assertEqual(metadata["aliases"], [])

    def test_inline_list_with_quoted_comma(self):
        metadata, _ = vault.parse_frontmatter('---\naliases: ["Smith, John", Plain]\n---\n# X')
        self.assertEqual(metadata["aliases"], ["Smith, John", "Plain"])

    def test_nested_map_and_block_scalar(self):
        metadata, _ = vault.parse_frontmatter(
            "---\nsource:\n  author: Ada\n  year: 1843\nsummary: |\n  first line\n  second line\nid: x\n---\n# X"
        )
        self.assertEqual(metadata["source"], {"author": "Ada", "year": "1843"})
        self.assertEqual(metadata["summary"], "first line second line")
        self.assertEqual(metadata["id"], "x")

    def test_blank_scalar_and_value_containing_colon(self):
        metadata, _ = vault.parse_frontmatter('---\nid:\nurl: https://example.com/a:b\n---\n# X')
        self.assertEqual(metadata["id"], "")
        self.assertEqual(metadata["url"], "https://example.com/a:b")

    def test_no_frontmatter_is_left_alone(self):
        metadata, body = vault.parse_frontmatter("# Just a heading\n")
        self.assertEqual(metadata, {})
        self.assertEqual(body, "# Just a heading\n")

    def test_unterminated_frontmatter_is_not_parsed(self):
        metadata, body = vault.parse_frontmatter("---\nid: x\n# no closing fence\n")
        self.assertEqual(metadata, {})
        self.assertIn("id: x", body)


class ExtractionTests(unittest.TestCase):
    def test_links_ignore_code(self):
        self.assertEqual(
            vault.extract_links("Ignore `[[Missing]]`, keep [[Real]]."), ["Real"]
        )
        self.assertEqual(vault.extract_links("```\n[[Fenced]]\n```\n[[Kept]]"), ["Kept"])

    def test_links_strip_heading_and_extension(self):
        self.assertEqual(vault.extract_links("[[Folder/Note.md#Section|Alias]]"), ["Folder/Note"])

    def test_links_skip_urls(self):
        self.assertEqual(vault.extract_links("[[https://example.com]] [[Note]]"), ["Note"])

    def test_tasks_skip_fenced_blocks(self):
        body = "- [ ] open one\n\n```\n- [ ] not a task\n```\n\n- [x] done one\n"
        tasks = vault.extract_tasks(body)
        self.assertEqual([task["text"] for task in tasks], ["open one", "done one"])
        self.assertEqual([task["done"] for task in tasks], [False, True])

    def test_tags_normalise_hash_and_string_form(self):
        self.assertEqual(vault.note_tags({"tags": ["#a", "b"]}), ["a", "b"])
        self.assertEqual(vault.note_tags({"tags": "a b"}), ["a", "b"])
        self.assertEqual(vault.note_tags({}), [])


class MutationTests(unittest.TestCase):
    def test_bump_updated_rewrites_only_that_line(self):
        text = "---\nid: x\nupdated: 2020-01-01\ntags:\n  - keep\n---\n\nBody with updated: 2020-01-01\n"
        result, changed = vault.bump_updated(text, "2026-09-01")
        self.assertTrue(changed)
        self.assertIn("updated: 2026-09-01\n", result)
        self.assertIn("Body with updated: 2020-01-01", result)
        self.assertIn("  - keep", result)

    def test_bump_updated_is_idempotent(self):
        text = "---\nid: x\nupdated: 2026-09-01\n---\n\nBody\n"
        once, changed_once = vault.bump_updated(text, "2026-09-01")
        self.assertFalse(changed_once)
        self.assertEqual(once, text)

    def test_bump_updated_preserves_crlf(self):
        text = "---\r\nid: x\r\nupdated: 2020-01-01\r\n---\r\n\r\nBody\r\n"
        result, changed = vault.bump_updated(text, "2026-09-01")
        self.assertTrue(changed)
        self.assertIn("updated: 2026-09-01\r\n", result)

    def test_bump_updated_without_frontmatter(self):
        result, changed = vault.bump_updated("# Plain\n", "2026-09-01")
        self.assertFalse(changed)
        self.assertEqual(result, "# Plain\n")

    def test_set_frontmatter_expands_list_and_drops_old_values(self):
        text = "---\nid:\ntags:\n  - stale\n  - older\nstatus: draft\n---\n\n# Body\n"
        result = vault.set_frontmatter(text, {"id": "new-id", "tags": ["a", "b"], "status": "active"})
        self.assertIn("id: new-id", result)
        self.assertIn("  - a\n  - b", result)
        self.assertNotIn("stale", result)
        self.assertIn("status: active", result)
        self.assertIn("# Body", result)

    def test_set_frontmatter_appends_missing_keys(self):
        result = vault.set_frontmatter("---\nid: x\n---\n\n# B\n", {"type": "concept"})
        self.assertIn("type: concept", result)
        metadata, _ = vault.parse_frontmatter(result)
        self.assertEqual(metadata["type"], "concept")

    def test_render_template_substitutes_title_and_dates(self):
        rendered = vault.render_template(
            "# {{title}}\ncreated: {{date:YYYY-MM-DD}}\nyear: {{date:YYYY}}\nplain: {{date}}",
            "My Note",
            date(2026, 9, 1),
        )
        self.assertIn("# My Note", rendered)
        self.assertIn("created: 2026-09-01", rendered)
        self.assertIn("year: 2026", rendered)
        self.assertIn("plain: 2026-09-01", rendered)

    def test_format_moment_iso_week_and_literals(self):
        value = date(2026, 9, 1)
        self.assertEqual(vault.format_moment(value, "GGGG-[W]WW"), "2026-W36")
        self.assertEqual(vault.format_moment(value, "YYYY-MM-DD"), "2026-09-01")
        self.assertEqual(vault.format_moment(value, "[Week] W"), "Week 36")
        self.assertEqual(vault.format_moment(value, "YYYY"), "2026")
        self.assertEqual(vault.format_moment(value, "MMM D"), "Sep 1")

    def test_weekly_template_renders_without_leftover_tokens(self):
        rendered = vault.render_template(
            "# Week {{date:GGGG-[W]WW}}\nid: weekly-{{date:GGGG-[W]WW}}",
            "2026-W36",
            date(2026, 9, 1),
        )
        self.assertIn("# Week 2026-W36", rendered)
        self.assertIn("id: weekly-2026-W36", rendered)
        self.assertNotIn("GGGG", rendered)
        self.assertNotIn("[W]", rendered)

    def test_slugify(self):
        self.assertEqual(vault.slugify("Spaced Repetition"), "spaced-repetition")
        self.assertEqual(vault.slugify("Übergrößen & Co."), "uebergroessen-co")
        self.assertEqual(vault.slugify("Straße"), "strasse")
        self.assertEqual(vault.slugify("Müller"), "mueller")
        self.assertEqual(vault.slugify("???"), "note")

    def test_auto_stamp_exclusions(self):
        self.assertTrue(vault.is_auto_stamp_target("40-knowledge/concepts/A.md"))
        self.assertTrue(vault.is_auto_stamp_target("10-projects/B.md"))
        self.assertFalse(vault.is_auto_stamp_target("30-resources/sources/raw/Article.md"))
        self.assertFalse(vault.is_auto_stamp_target("50-journal/daily/2026-09-01.md"))
        self.assertFalse(vault.is_auto_stamp_target("90-system/Link Policy.md"))
        self.assertFalse(vault.is_auto_stamp_target("99-attachments/x.md"))
        self.assertFalse(vault.is_auto_stamp_target("CLAUDE.md"))
        self.assertFalse(vault.is_auto_stamp_target("40-knowledge/image.png"))


class VaultFixture(unittest.TestCase):
    """Builds a miniature but structurally valid vault in a temp directory."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.addCleanup(self._temp.cleanup)
        for folder in (
            "00-inbox", "10-projects", "40-knowledge/concepts", "60-decisions",
            "90-system/templates", "90-system/indexes",
        ):
            (self.root / folder).mkdir(parents=True, exist_ok=True)

        self.write("Home.md", note_text("home", "moc", "Home", "[[40-knowledge/concepts/MOC - Concepts]]"))
        self.write(
            "00-inbox/MOC - Inbox.md",
            note_text("moc-inbox", "moc", "Inbox", "## Captures\n\n<!-- vault:links -->\n\n[[Home]]"),
        )
        self.write(
            "40-knowledge/concepts/MOC - Concepts.md",
            note_text("moc-concepts", "moc", "Concepts",
                      "## Concepts\n\n<!-- vault:links -->\n\n[[Home]]"),
        )
        self.write(
            "40-knowledge/concepts/Retrieval.md",
            note_text("retrieval", "concept", "Retrieval",
                      "Retrieval narrows context.\n\n[[40-knowledge/concepts/MOC - Concepts]]"),
        )
        self.write(
            "10-projects/Build Search.md",
            note_text("build-search", "project", "Build Search",
                      "A project about retrieval ranking.\n\n- [ ] ship it\n\n[[Home]]"),
        )
        self.write(
            "90-system/templates/Concept Template.md",
            '---\nid:\ntype: concept\nstatus: draft\ncreated: "{{date:YYYY-MM-DD}}"\n'
            'updated: "{{date:YYYY-MM-DD}}"\naliases: []\ntags: []\n---\n\n# {{title}}\n\n'
            "Parent: [[40-knowledge/concepts/MOC - Concepts|Concepts]]\n\n## Claim\n",
        )
        self.write(
            "90-system/templates/Note Template.md",
            '---\nid:\ntype: note\nstatus: draft\ncreated: "{{date:YYYY-MM-DD}}"\n'
            'updated: "{{date:YYYY-MM-DD}}"\naliases: []\ntags: []\n---\n\n# {{title}}\n\n'
            "## Connections\n\n- Parent MOC:\n- Related:\n",
        )

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class CacheTests(VaultFixture):
    def test_sync_is_incremental(self):
        cache = vault.VaultCache(self.root, self.root / "cache.sqlite3")
        first = cache.sync()
        self.assertEqual(first["reparsed"], first["total"])
        self.assertEqual(cache.sync()["reparsed"], 0)

        target = self.root / "40-knowledge/concepts/Retrieval.md"
        target.write_text(target.read_text(encoding="utf-8") + "\nMore text.\n", encoding="utf-8")
        self.assertEqual(cache.sync()["reparsed"], 1)

        target.unlink()
        result = cache.sync()
        self.assertEqual(result["removed"], 1)
        self.assertNotIn("40-knowledge/concepts/Retrieval.md", [n.path for n in cache.notes()])
        cache.close()

    def test_schema_change_rebuilds(self):
        path = self.root / "cache.sqlite3"
        cache = vault.VaultCache(self.root, path)
        cache.sync()
        cache.close()
        original = vault.SCHEMA_VERSION
        try:
            vault.SCHEMA_VERSION = original + 1
            rebuilt = vault.VaultCache(self.root, path)
            self.assertEqual(rebuilt.sync()["reparsed"], rebuilt.sync()["total"] - 0 or 0)
            self.assertGreater(len(rebuilt.notes()), 0)
            rebuilt.close()
        finally:
            vault.SCHEMA_VERSION = original

    def test_notes_omit_bodies_until_hydrated(self):
        cache = vault.VaultCache(self.root, self.root / "cache.sqlite3")
        cache.sync()
        note = next(n for n in cache.notes() if n.path.endswith("Retrieval.md"))
        self.assertEqual(note.body, "")
        vault.hydrate_bodies(self.root, [note])
        self.assertIn("Retrieval narrows context", note.body)
        cache.close()


class RankingTests(VaultFixture):
    def rank(self, query, **kwargs):
        cache = vault.VaultCache(self.root, self.root / "cache.sqlite3")
        cache.sync()
        try:
            return vault.rank(cache, query, vault.QueryOptions(**kwargs))
        finally:
            cache.close()

    def test_title_match_outranks_body_match(self):
        ranked = self.rank("retrieval")
        self.assertEqual(ranked[0][1].path, "40-knowledge/concepts/Retrieval.md")

    def test_type_filter(self):
        ranked = self.rank("retrieval", types=("project",))
        self.assertEqual([note.path for _, note in ranked], ["10-projects/Build Search.md"])

    def test_prefix_expansion_finds_longer_term(self):
        self.assertTrue(any(note.path.endswith("Retrieval.md") for _, note in self.rank("retriev")))

    def test_fuzzy_tolerates_a_typo(self):
        self.assertFalse(self.rank("retreival"))
        self.assertTrue(any(n.path.endswith("Retrieval.md") for _, n in self.rank("retreival", fuzzy=True)))

    def test_empty_query_returns_nothing(self):
        self.assertEqual(self.rank("   "), [])

    def test_templates_excluded_by_default(self):
        self.assertFalse(any("/templates/" in n.path for _, n in self.rank("claim")))
        self.assertTrue(any("/templates/" in n.path for _, n in self.rank("claim", include_templates=True)))


class RetrievalEvaluationTests(VaultFixture):
    def write_cases(self, rows):
        return self.write(
            "90-system/evals/retrieval-cases.jsonl",
            "".join(json.dumps(row) + "\n" for row in rows),
        )

    def test_evaluates_production_ranker_and_categories(self):
        self.write_cases([
            {
                "id": "find-retrieval",
                "query": "retrieval",
                "expected": "40-knowledge/concepts/Retrieval.md",
                "category": "known-item",
            },
            {
                "id": "find-project",
                "query": "build search",
                "expected": ["10-projects/Build Search.md"],
                "type": "project",
                "tags": [],
            },
        ])
        code, payload = run(
            vault.command_eval_retrieval,
            self.root,
            "90-system/evals/retrieval-cases.jsonl",
            (1, 3, 5),
            False,
            None,
            None,
            True,
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["engine"], "lexical-bm25f")
        self.assertEqual(payload["metrics"]["case_count"], 2)
        self.assertEqual(payload["metrics"]["recall_at_k"]["1"], 1.0)
        self.assertEqual(payload["metrics"]["mrr"], 1.0)
        self.assertEqual(payload["categories"]["known-item"]["case_count"], 1)
        self.assertNotIn("query", payload["results"][0])
        self.assertFalse(payload["semantic_gate"]["trial_justified"])
        self.assertIn("insufficient_representative_cases", payload["semantic_gate"]["reasons"])

    def test_multiple_expected_notes_use_macro_recall(self):
        self.write_cases([{
            "query": "retrieval",
            "expected": [
                "40-knowledge/concepts/Retrieval.md",
                "10-projects/Build Search.md",
            ],
        }])
        cases, errors, _ = vault.load_retrieval_cases(
            self.root, "90-system/evals/retrieval-cases.jsonl"
        )
        self.assertEqual(errors, [])
        cache = vault.VaultCache(self.root, self.root / "eval.sqlite3")
        cache.sync()
        try:
            results, metrics, _ = vault.evaluate_retrieval(cache, cases, (1, 3), False)
        finally:
            cache.close()
        self.assertEqual(results[0]["recall_at_k"]["1"], 0.5)
        self.assertEqual(metrics["recall_at_k"]["3"], 1.0)

    def test_report_is_written_inside_vault(self):
        self.write_cases([{
            "query": "retrieval",
            "expected": "40-knowledge/concepts/Retrieval.md",
        }])
        code, payload = run(
            vault.command_eval_retrieval,
            self.root,
            "90-system/evals/retrieval-cases.jsonl",
            (1,),
            False,
            "90-system/evals/retrieval-report.json",
            1.0,
            True,
        )
        self.assertEqual(code, 0)
        self.assertTrue(payload["threshold"]["passed"])
        report = json.loads(
            (self.root / "90-system/evals/retrieval-report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["metrics"]["mrr"], 1.0)
        self.assertIn("semantic_gate", report)
        self.assertTrue(report["threshold"]["passed"])

    def test_report_cannot_overwrite_an_arbitrary_vault_note(self):
        self.write_cases([{
            "query": "retrieval",
            "expected": "40-knowledge/concepts/Retrieval.md",
        }])
        home = self.root / "Home.md"
        before = home.read_text(encoding="utf-8")
        code, payload = run(
            vault.command_eval_retrieval,
            self.root,
            "90-system/evals/retrieval-cases.jsonl",
            (5,),
            False,
            "Home.md",
            None,
            True,
        )
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "report_path_not_allowed")
        self.assertEqual(home.read_text(encoding="utf-8"), before)

    def test_bad_cases_fail_without_running(self):
        self.write_cases([
            {"id": "bad", "query": "", "expected": "Missing.md"},
            {"id": "escape", "query": "x", "expected": "../outside.md"},
        ])
        code, payload = run(
            vault.command_eval_retrieval,
            self.root,
            "90-system/evals/retrieval-cases.jsonl",
            (1,),
            False,
            None,
            None,
            True,
        )
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "invalid_retrieval_cases")
        self.assertEqual(len(payload["details"]), 2)

    def test_threshold_can_fail_ci(self):
        self.write_cases([{
            "query": "unmatched vocabulary",
            "expected": "40-knowledge/concepts/Retrieval.md",
        }])
        code, payload = run(
            vault.command_eval_retrieval,
            self.root,
            "90-system/evals/retrieval-cases.jsonl",
            (5,),
            False,
            None,
            0.5,
            True,
        )
        self.assertEqual(code, 1)
        self.assertFalse(payload["threshold"]["passed"])

    def test_k_list_validates_positive_integers(self):
        self.assertEqual(vault.k_list("5,1,5"), (1, 5))
        with self.assertRaises(Exception):
            vault.k_list("0,3")

    def test_semantic_trial_gate_needs_enough_cases_and_a_measured_gap(self):
        justified = vault.semantic_trial_gate(
            {"case_count": 20, "recall_at_k": {"5": 0.84}, "mrr": 0.7},
            {"known-item": {"case_count": 20, "recall_at_k": {"5": 0.84}, "mrr": 0.7}},
            (1, 5),
        )
        self.assertTrue(justified["trial_justified"])
        self.assertFalse(justified["semantic_retrieval_enabled"])

        strong_lexical = vault.semantic_trial_gate(
            {"case_count": 20, "recall_at_k": {"5": 0.9}, "mrr": 0.8}, {}, (5,)
        )
        self.assertFalse(strong_lexical["trial_justified"])
        self.assertIn("lexical_recall_gate_not_breached", strong_lexical["reasons"])

    def test_semantic_trial_gate_can_find_a_material_weak_category(self):
        gate = vault.semantic_trial_gate(
            {"case_count": 25, "recall_at_k": {"5": 0.92}, "mrr": 0.8},
            {"multilingual": {"case_count": 5, "recall_at_k": {"5": 0.6}, "mrr": 0.4}},
            (1, 3, 5),
        )
        self.assertTrue(gate["trial_justified"])
        self.assertEqual(gate["weak_categories"], ["multilingual"])


class GraphTests(VaultFixture):
    def test_resolution_and_adjacency(self):
        notes = vault.scan_notes(self.root)
        adjacency, unresolved = vault.graph(notes)
        self.assertEqual(unresolved, [])
        self.assertIn("Home.md", adjacency["40-knowledge/concepts/MOC - Concepts.md"])

    def test_unresolved_link_is_reported(self):
        self.write("00-inbox/Loose.md", note_text("loose", "note", "Loose", "[[Nowhere]]"))
        _, unresolved = vault.graph(vault.scan_notes(self.root))
        self.assertEqual(unresolved, [{"source": "00-inbox/Loose.md", "target": "Nowhere"}])

    def test_ambiguous_stem_does_not_resolve(self):
        notes = vault.scan_notes(self.root)
        by_path, by_stem = vault.note_maps(notes)
        self.assertIsNotNone(vault.resolve_target("Home", by_path, by_stem))
        self.assertIsNone(vault.resolve_target("Definitely Missing", by_path, by_stem))

    def test_existing_attachment_embed_is_resolved(self):
        attachment = self.root / "99-attachments" / "photo.png"
        attachment.parent.mkdir(parents=True, exist_ok=True)
        attachment.write_bytes(b"not-a-real-png")
        self.write(
            "00-inbox/With Attachment.md",
            note_text(
                "with-attachment",
                "note",
                "With Attachment",
                "![[99-attachments/photo.png]]\n\n[[00-inbox/MOC - Inbox]]",
            ),
        )
        _, unresolved = vault.graph(vault.scan_notes(self.root), vault.asset_maps(self.root))
        self.assertEqual(unresolved, [])

    def test_missing_attachment_embed_is_reported(self):
        self.write(
            "00-inbox/Missing Attachment.md",
            note_text(
                "missing-attachment",
                "note",
                "Missing Attachment",
                "![[99-attachments/missing.png]]\n\n[[00-inbox/MOC - Inbox]]",
            ),
        )
        _, unresolved = vault.graph(vault.scan_notes(self.root), vault.asset_maps(self.root))
        self.assertEqual(
            unresolved,
            [{"source": "00-inbox/Missing Attachment.md", "target": "99-attachments/missing.png"}],
        )


class CheckTests(VaultFixture):
    def check(self, **kwargs):
        options = {"compact": True, "strict": False, "quiet": False,
                   "stale_days": vault.DEFAULT_STALE_DAYS, "max_tags": vault.DEFAULT_MAX_TAGS}
        options.update(kwargs)
        return run(vault.command_check, self.root, **options)

    def test_clean_vault_passes(self):
        code, payload = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(payload["summary"]["errors"], 0)

    def test_unresolved_link_is_an_error(self):
        self.write("00-inbox/Loose.md", note_text("loose", "note", "Loose", "[[Nowhere]]"))
        code, payload = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(len(payload["errors"]["unresolved_links"]), 1)

    def test_duplicate_id_is_an_error(self):
        self.write("00-inbox/Copy.md", note_text("retrieval", "note", "Copy", "[[Home]]"))
        code, payload = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(len(payload["errors"]["duplicate_ids"]), 1)

    def test_placement_violation_is_a_warning_not_an_error(self):
        self.write(
            "40-knowledge/concepts/Stray.md",
            note_text("stray", "decision", "Stray", "[[40-knowledge/concepts/MOC - Concepts]]"),
        )
        code, payload = self.check()
        self.assertEqual(code, 0, "a placement warning must not fail the check")
        self.assertEqual(payload["warnings"]["placement"][0]["expected_folder"], "60-decisions")
        self.assertEqual(self.check(strict=True)[0], 1, "--strict must fail on warnings")

    def test_missing_moc_link_is_reported(self):
        self.write("40-knowledge/concepts/Lonely.md",
                   note_text("lonely", "concept", "Lonely", "[[40-knowledge/concepts/Retrieval]]"))
        _, payload = self.check()
        self.assertEqual(
            [entry["path"] for entry in payload["warnings"]["moc_coverage"]],
            ["40-knowledge/concepts/Lonely.md"],
        )

    def test_moc_link_satisfies_coverage(self):
        self.write("40-knowledge/concepts/Connected.md",
                   note_text("connected", "concept", "Connected", "[[40-knowledge/concepts/MOC - Concepts]]"))
        _, payload = self.check()
        self.assertEqual(payload["warnings"]["moc_coverage"], [])

    def test_stale_note_is_reported(self):
        self.write("40-knowledge/concepts/Old.md",
                   note_text("old", "concept", "Old", "[[40-knowledge/concepts/MOC - Concepts]]")
                   .replace(f"updated: {TODAY}", "updated: 2020-01-01"))
        _, payload = self.check()
        self.assertEqual([e["path"] for e in payload["warnings"]["stale"]], ["40-knowledge/concepts/Old.md"])

    def test_missing_required_key_is_reported(self):
        self.write("40-knowledge/concepts/NoStatus.md",
                   "---\nid: nostatus\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\n"
                   "\n# NoStatus\n\n[[40-knowledge/concepts/MOC - Concepts]]\n")
        _, payload = self.check()
        self.assertIn("status", payload["warnings"]["metadata_issues"][0]["missing"])

    def test_quiet_omits_warning_detail(self):
        _, payload = self.check(quiet=True)
        self.assertIn("summary", payload)
        self.assertNotIn("warnings", payload)


class FreshnessTests(VaultFixture):
    def check(self):
        return run(
            vault.command_check, self.root, compact=True, strict=False, quiet=False,
            stale_days=vault.DEFAULT_STALE_DAYS, max_tags=vault.DEFAULT_MAX_TAGS,
        )

    def test_pointer_requires_truth_source_and_verification_date(self):
        self.write(
            "40-knowledge/concepts/Live State.md",
            note_text(
                "live-state", "concept", "Live State",
                "[[40-knowledge/concepts/MOC - Concepts]]",
                extra="freshness: pointer\ntruth_source:\nlast_verified:\n",
            ),
        )
        _, payload = self.check()
        issues = {item["issue"] for item in payload["warnings"]["freshness"]}
        self.assertEqual(issues, {"pointer_missing_truth_source", "pointer_missing_last_verified"})

    def test_expired_pointer_and_invalid_fact_lifetime_are_reported(self):
        self.write(
            "40-knowledge/concepts/Live State.md",
            note_text(
                "live-state", "concept", "Live State",
                "[[40-knowledge/concepts/MOC - Concepts]]",
                extra=(
                    "freshness: pointer\ntruth_source: https://example.com/live\n"
                    "last_verified: 2020-01-01\nfreshness_window_days: 7\n"
                    "valid_from: 2026-02-01\nvalid_until: 2026-01-01\n"
                ),
            ),
        )
        _, payload = self.check()
        issues = {item["issue"] for item in payload["warnings"]["freshness"]}
        self.assertIn("verification_expired", issues)
        self.assertIn("valid_until_before_valid_from", issues)

    def test_current_pointer_and_dated_snapshot_pass(self):
        self.write(
            "40-knowledge/concepts/Live State.md",
            note_text(
                "live-state", "concept", "Live State",
                "[[40-knowledge/concepts/MOC - Concepts]]",
                extra=(
                    f"freshness: pointer\ntruth_source: https://example.com/live\n"
                    f"last_verified: {TODAY}\n"
                ),
            ),
        )
        self.write(
            "40-knowledge/concepts/Snapshot.md",
            note_text(
                "snapshot", "concept", "Snapshot",
                "[[40-knowledge/concepts/MOC - Concepts]]",
                extra=f"freshness: snapshot\nobserved: {TODAY}\n",
            ),
        )
        _, payload = self.check()
        self.assertEqual(payload["warnings"]["freshness"], [])


class TypedRelationTests(VaultFixture):
    def relation_note(self, filename, note_id, title, extra):
        return self.write(
            f"40-knowledge/concepts/{filename}.md",
            note_text(
                note_id, "concept", title,
                "[[40-knowledge/concepts/MOC - Concepts]]",
                extra=extra,
            ),
        )

    def findings(self):
        return vault.typed_relation_findings(vault.scan_notes(self.root))

    def test_valid_inverse_pair_passes(self):
        self.relation_note(
            "A", "a", "A", 'supports: ["[[40-knowledge/concepts/B]]"]\n'
        )
        self.relation_note(
            "B", "b", "B", 'supported_by: ["[[40-knowledge/concepts/A]]"]\n'
        )
        errors, inverses = self.findings()
        self.assertEqual(errors, [])
        self.assertEqual(inverses, [])

    def test_missing_inverse_is_warning_quality_finding(self):
        self.relation_note(
            "A", "a", "A", 'depends_on: ["[[40-knowledge/concepts/B]]"]\n'
        )
        self.relation_note("B", "b", "B", "")
        errors, inverses = self.findings()
        self.assertEqual(errors, [])
        self.assertEqual(inverses[0]["missing_inverse"], "required_by")

    def test_dangling_self_and_supersession_cycle_are_errors(self):
        self.relation_note(
            "A", "a", "A",
            'supersedes: ["[[40-knowledge/concepts/B]]"]\n'
            'contradicts: ["[[40-knowledge/concepts/A]]"]\n'
            'supports: ["[[40-knowledge/concepts/Missing]]"]\n',
        )
        self.relation_note(
            "B", "b", "B", 'supersedes: ["[[40-knowledge/concepts/A]]"]\n'
        )
        errors, _ = self.findings()
        issues = {item["issue"] for item in errors}
        self.assertEqual(issues, {"dangling_target", "self_relation", "supersession_cycle"})


class NewNoteTests(VaultFixture):
    def create(self, **kwargs):
        options = {"note_type": "concept", "title": "Spaced Repetition", "folder": None,
                   "tags": [], "status": None, "link_moc": True, "dry_run": False, "compact": True}
        options.update(kwargs)
        return run(vault.command_new, self.root, **options)

    def test_creates_note_with_stamped_frontmatter(self):
        code, payload = self.create(tags=["learning"])
        self.assertEqual(code, 0)
        created = self.root / payload["path"]
        self.assertTrue(created.exists())
        metadata, body = vault.parse_frontmatter(created.read_text(encoding="utf-8"))
        self.assertEqual(metadata["id"], "spaced-repetition")
        self.assertEqual(metadata["type"], "concept")
        self.assertEqual(metadata["created"], TODAY)
        self.assertEqual(metadata["tags"], ["learning"])
        self.assertIn("# Spaced Repetition", body)
        self.assertNotIn("{{", created.read_text(encoding="utf-8"))

    def test_links_the_parent_moc(self):
        _, payload = self.create()
        self.assertTrue(payload["moc_updated"])
        moc = (self.root / "40-knowledge/concepts/MOC - Concepts.md").read_text(encoding="utf-8")
        self.assertIn("- [[40-knowledge/concepts/Spaced Repetition|Spaced Repetition]]", moc)

    def test_created_note_passes_check(self):
        self.create()
        code, _ = run(
            vault.command_check, self.root, compact=True, strict=False, quiet=True,
            stale_days=vault.DEFAULT_STALE_DAYS, max_tags=vault.DEFAULT_MAX_TAGS,
        )
        self.assertEqual(code, 0)

    def test_refuses_to_overwrite(self):
        self.create()
        code, payload = self.create()
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "already_exists")

    def test_dry_run_writes_nothing(self):
        code, payload = self.create(dry_run=True)
        self.assertEqual(code, 0)
        self.assertFalse((self.root / payload["path"]).exists())
        self.assertIn("# Spaced Repetition", payload["content"])

    def test_moc_requires_an_explicit_folder(self):
        code, payload = self.create(note_type="moc", title="Some Map")
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "folder_required")

    def test_explicit_folder_is_honoured(self):
        code, payload = self.create(folder="00-inbox")
        self.assertEqual(code, 0)
        self.assertEqual(payload["path"], "00-inbox/Spaced Repetition.md")

    def test_default_inbox_note_links_out_to_its_moc(self):
        code, payload = self.create(note_type="note", title="Quick Capture")
        self.assertEqual(code, 0)
        created = (self.root / payload["path"]).read_text(encoding="utf-8")
        self.assertIn("[[00-inbox/MOC - Inbox|Inbox]]", created)
        check_code, check_payload = run(
            vault.command_check, self.root, compact=True, strict=False, quiet=False,
            stale_days=vault.DEFAULT_STALE_DAYS, max_tags=vault.DEFAULT_MAX_TAGS,
        )
        self.assertEqual(check_code, 0)
        self.assertNotIn(
            payload["path"],
            [entry["path"] for entry in check_payload["warnings"]["moc_coverage"]],
        )

    def test_folder_traversal_is_refused_without_writing(self):
        outside_name = f"{self.root.name}-escape"
        outside = self.root.parent / outside_name
        code, payload = self.create(folder=f"../{outside_name}")
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "outside_vault")
        self.assertFalse((outside / "Spaced Repetition.md").exists())

    def test_missing_template_is_reported(self):
        code, payload = self.create(note_type="person", title="Ada")
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "template_missing")

    def test_moc_insertion_is_idempotent(self):
        moc = self.root / "40-knowledge/concepts/MOC - Concepts.md"
        line = "- [[40-knowledge/concepts/X|X]]"
        self.assertTrue(vault.insert_into_moc(moc, line))
        self.assertTrue(vault.insert_into_moc(moc, line))
        self.assertEqual(moc.read_text(encoding="utf-8").count(line), 1)

    def test_moc_without_anchor_is_left_alone(self):
        moc = self.write("10-projects/MOC - Projects.md", note_text("moc-p", "moc", "Projects", "[[Home]]"))
        self.assertFalse(vault.insert_into_moc(moc, "- [[10-projects/Y|Y]]"))


class TouchTests(VaultFixture):
    # The fixture stamps notes with today's date, and `bump_updated` is idempotent, so the
    # test stamp must be a date that can never equal today. A fixed past date keeps the
    # assertion clock-independent.
    STAMP = "2020-01-01"

    def touch(self, path, **kwargs):
        options = {"stamp": self.STAMP, "only_durable": False, "compact": True}
        options.update(kwargs)
        return run(vault.command_touch, self.root, path, **options)

    def test_stamps_a_durable_note(self):
        code, payload = self.touch("40-knowledge/concepts/Retrieval.md")
        self.assertEqual(code, 0)
        self.assertTrue(payload["changed"])
        metadata, _ = vault.parse_frontmatter(
            (self.root / "40-knowledge/concepts/Retrieval.md").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["updated"], self.STAMP)

    def test_only_durable_skips_system_paths(self):
        self.write("90-system/Note.md", note_text("sys", "system", "Sys", "[[Home]]"))
        _, payload = self.touch("90-system/Note.md", only_durable=True)
        self.assertFalse(payload["changed"])
        self.assertEqual(payload["reason"], "excluded_from_auto_stamp")

    def test_missing_file_reports_error(self):
        code, payload = self.touch("40-knowledge/concepts/Nope.md")
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "note_not_found")

    def test_path_outside_vault_is_refused(self):
        with tempfile.TemporaryDirectory() as outside:
            stray = Path(outside) / "Stray.md"
            stray.write_text("---\nupdated: 2020-01-01\n---\n", encoding="utf-8")
            code, payload = self.touch(str(stray))
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "outside_vault")


class RawSourceTests(VaultFixture):
    def setUp(self):
        super().setUp()
        (self.root / "30-resources/sources/raw").mkdir(parents=True, exist_ok=True)
        self.write(
            "30-resources/sources/raw/MOC - Raw Sources.md",
            note_text("moc-raw", "moc", "Raw Sources", "<!-- vault:links -->\n\n[[Home]]"),
        )

    def raw_text(self, payload="External source text.", status="draft", digest=""):
        return note_text(
            "raw-example",
            "raw-source",
            "Raw Example",
            "[[30-resources/sources/raw/MOC - Raw Sources]]\n\n"
            f"{vault.RAW_SOURCE_BEGIN}\n{payload}\n{vault.RAW_SOURCE_END}",
            status=status,
            extra=f"content_sha256: {digest}\nsealed:\n",
        )

    def seal(self, path="30-resources/sources/raw/Raw Example.md", verify=False):
        return run(vault.command_source_seal, self.root, path, verify, True)

    def test_payload_hash_is_newline_portable(self):
        lf = f"{vault.RAW_SOURCE_BEGIN}\nA\nB\n{vault.RAW_SOURCE_END}"
        crlf = lf.replace("\n", "\r\n")
        self.assertEqual(vault.raw_source_payload(lf), "A\nB")
        self.assertEqual(vault.raw_source_payload(crlf), "A\nB")

    def test_seal_records_hash_and_verify_passes(self):
        path = self.write("30-resources/sources/raw/Raw Example.md", self.raw_text())
        code, payload = self.seal()
        self.assertEqual(code, 0)
        self.assertTrue(payload["sealed"])
        metadata, _ = vault.parse_frontmatter(path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "immutable")
        self.assertEqual(len(metadata["content_sha256"]), 64)
        verify_code, verify_payload = self.seal(verify=True)
        self.assertEqual(verify_code, 0)
        self.assertEqual(verify_payload["state"], "verified")

    def test_sealed_payload_change_is_an_error_and_cannot_be_resealed(self):
        path = self.write("30-resources/sources/raw/Raw Example.md", self.raw_text())
        self.seal()
        changed = path.read_text(encoding="utf-8").replace(
            "External source text.", "Changed source text."
        )
        path.write_text(changed, encoding="utf-8")
        reseal_code, reseal_payload = self.seal()
        self.assertEqual(reseal_code, 1)
        self.assertEqual(reseal_payload["error"], "sealed_source_cannot_be_resealed")
        check_code, check_payload = run(
            vault.command_check, self.root, compact=True, strict=False, quiet=False,
            stale_days=vault.DEFAULT_STALE_DAYS, max_tags=vault.DEFAULT_MAX_TAGS,
        )
        self.assertEqual(check_code, 1)
        self.assertEqual(
            check_payload["errors"]["raw_source_integrity"][0]["issue"],
            "payload_changed_after_seal",
        )

    def test_draft_is_warning_and_source_outside_folder_is_refused(self):
        self.write("30-resources/sources/raw/Raw Example.md", self.raw_text())
        _, check_payload = run(
            vault.command_check, self.root, compact=True, strict=False, quiet=False,
            stale_days=vault.DEFAULT_STALE_DAYS, max_tags=vault.DEFAULT_MAX_TAGS,
        )
        self.assertEqual(
            check_payload["warnings"]["raw_source_drafts"][0]["path"],
            "30-resources/sources/raw/Raw Example.md",
        )
        self.write("00-inbox/Raw Example.md", self.raw_text())
        code, payload = self.seal("00-inbox/Raw Example.md")
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "not_in_raw_source_folder")


class SafeMergeTests(VaultFixture):
    def write_merged_body(self, body=None):
        return self.write(
            "90-system/indexes/.merge-drafts/retrieval.md",
            body or (
                "# Retrieval\n\nConsolidated retrieval guidance.\n\n"
                "[[40-knowledge/concepts/MOC - Concepts]]\n\n[[Home]]\n"
            ),
        )

    def preview(self):
        return run(
            vault.command_merge,
            self.root,
            "40-knowledge/concepts/Retrieval.md",
            "10-projects/Build Search.md",
            "90-system/indexes/.merge-drafts/retrieval.md",
            False,
            None,
            False,
            True,
        )

    def test_dry_run_is_non_mutating_and_hashes_exact_inputs(self):
        self.write_merged_body()
        canonical = self.root / "40-knowledge/concepts/Retrieval.md"
        retired = self.root / "10-projects/Build Search.md"
        before = (canonical.read_text(encoding="utf-8"), retired.read_text(encoding="utf-8"))
        code, payload = self.preview()
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertRegex(payload["plan_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(payload["changes"]["retired_deleted"])
        self.assertEqual(
            before,
            (canonical.read_text(encoding="utf-8"), retired.read_text(encoding="utf-8")),
        )

    def test_apply_requires_preview_hash_then_leaves_valid_redirect(self):
        self.write_merged_body()
        code, preview = self.preview()
        self.assertEqual(code, 0)
        code, missing = run(
            vault.command_merge,
            self.root,
            "40-knowledge/concepts/Retrieval.md",
            "10-projects/Build Search.md",
            "90-system/indexes/.merge-drafts/retrieval.md",
            True,
            None,
            False,
            True,
        )
        self.assertEqual(code, 2)
        self.assertEqual(missing["error"], "plan_confirmation_required")

        code, applied = run(
            vault.command_merge,
            self.root,
            "40-knowledge/concepts/Retrieval.md",
            "10-projects/Build Search.md",
            "90-system/indexes/.merge-drafts/retrieval.md",
            True,
            preview["plan_sha256"],
            False,
            True,
        )
        self.assertEqual(code, 0)
        self.assertTrue(applied["applied"])
        canonical = (self.root / "40-knowledge/concepts/Retrieval.md").read_text(encoding="utf-8")
        retired = (self.root / "10-projects/Build Search.md").read_text(encoding="utf-8")
        canonical_metadata, canonical_body = vault.parse_frontmatter(canonical)
        retired_metadata, _ = vault.parse_frontmatter(retired)
        self.assertIn("Build Search", canonical_metadata["aliases"])
        self.assertIn("10-projects/Build Search.md", canonical_metadata["merged_from"])
        self.assertIn("Consolidated retrieval guidance", canonical_body)
        self.assertEqual(retired_metadata["type"], "redirect")
        self.assertEqual(retired_metadata["status"], "superseded")
        self.assertIn("[[40-knowledge/concepts/Retrieval|Retrieval]]", retired)
        self.assertFalse((self.root / "10-projects/Build Search.md").is_symlink())

        code, health = run(vault.command_check, self.root, True, False, True, 180, 60)
        self.assertEqual(code, 0, health)
        self.assertEqual(health["summary"]["redirect_integrity"], 0)

    def test_changed_input_invalidates_plan(self):
        draft = self.write_merged_body()
        _, preview = self.preview()
        draft.write_text("# Retrieval\n\nChanged after preview.\n", encoding="utf-8")
        code, payload = run(
            vault.command_merge,
            self.root,
            "40-knowledge/concepts/Retrieval.md",
            "10-projects/Build Search.md",
            "90-system/indexes/.merge-drafts/retrieval.md",
            True,
            preview["plan_sha256"],
            True,
            True,
        )
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"], "plan_changed")

    def test_warnings_need_separate_acceptance(self):
        self.write(
            "10-projects/Build Search.md",
            note_text(
                "build-search", "project", "Build Search",
                "Project material. [[Home]] [[60-decisions/Uncopied Decision]]",
                extra="owner: Retired Owner\n",
            ),
        )
        self.write_merged_body("# Retrieval\n\nConsolidated.\n\n[[Home]]\n")
        _, preview = self.preview()
        self.assertTrue(preview["warnings_require_acceptance"])
        self.assertEqual(preview["metadata_conflicts"][0]["key"], "owner")
        self.assertIn("60-decisions/Uncopied Decision", preview["links_at_risk"])
        code, payload = run(
            vault.command_merge,
            self.root,
            "40-knowledge/concepts/Retrieval.md",
            "10-projects/Build Search.md",
            "90-system/indexes/.merge-drafts/retrieval.md",
            True,
            preview["plan_sha256"],
            False,
            True,
        )
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"], "merge_warnings_not_accepted")

    def test_rejects_wrong_title_and_system_notes(self):
        self.write_merged_body("# Different identity\n")
        code, payload = self.preview()
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "merged_body_title_mismatch")

        code, payload = run(
            vault.command_merge,
            self.root,
            "Home.md",
            "10-projects/Build Search.md",
            "90-system/indexes/.merge-drafts/retrieval.md",
            False,
            None,
            False,
            True,
        )
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "note_not_mergeable")

    def test_checker_rejects_redirect_chains(self):
        self.write(
            "00-inbox/Redirect One.md",
            note_text(
                "redirect-one", "redirect", "Redirect One", "[[00-inbox/Redirect Two]]",
                status="superseded", extra="redirect_to: '[[00-inbox/Redirect Two]]'\n",
            ),
        )
        self.write(
            "00-inbox/Redirect Two.md",
            note_text(
                "redirect-two", "redirect", "Redirect Two", "[[40-knowledge/concepts/Retrieval]]",
                status="superseded", extra="redirect_to: '[[40-knowledge/concepts/Retrieval]]'\n",
            ),
        )
        findings = vault.redirect_findings(vault.scan_notes(self.root))
        self.assertTrue(any(item["issue"] == "redirect_chain" for item in findings))

    def test_redirect_title_may_match_its_canonical_note(self):
        self.write(
            "00-inbox/Old Retrieval.md",
            note_text(
                "old-retrieval", "redirect", "Retrieval",
                "[[40-knowledge/concepts/Retrieval]]", status="superseded",
                extra="redirect_to: '[[40-knowledge/concepts/Retrieval]]'\n",
            ),
        )
        code, payload = run(vault.command_check, self.root, True, False, True, 180, 60)
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["summary"]["duplicate_titles"], 0)

    def test_merge_refuses_to_create_a_redirect_chain(self):
        self.write(
            "00-inbox/Old Build Search.md",
            note_text(
                "old-build-search", "redirect", "Old Build Search",
                "[[10-projects/Build Search]]", status="superseded",
                extra="redirect_to: '[[10-projects/Build Search]]'\n",
            ),
        )
        self.write_merged_body()
        code, payload = self.preview()
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "retired_note_has_inbound_redirects")
        self.assertEqual(payload["redirects"], ["00-inbox/Old Build Search.md"])


class ReportingTests(VaultFixture):
    def test_tasks_lists_open_items(self):
        code, payload = run(vault.command_tasks, self.root, None, "open", True)
        self.assertEqual(code, 0)
        self.assertEqual([task["text"] for task in payload["tasks"]], ["ship it"])

    def test_tasks_path_prefix_filters(self):
        _, payload = run(vault.command_tasks, self.root, "40-knowledge", "open", True)
        self.assertEqual(payload["tasks"], [])

    def test_tags_counts_are_reported(self):
        self.write("40-knowledge/concepts/Tagged.md",
                   note_text("tagged", "concept", "Tagged", "[[40-knowledge/concepts/MOC - Concepts]]",
                             extra="tags:\n  - alpha\n  - beta\n"))
        _, payload = run(vault.command_tags, self.root, 1, True)
        self.assertEqual({entry["tag"] for entry in payload["tags"]}, {"alpha", "beta"})
        self.assertEqual(sorted(payload["singletons"]), ["alpha", "beta"])

    def test_stale_uses_the_day_threshold(self):
        _, payload = run(vault.command_stale, self.root, 3650, True)
        self.assertEqual(payload["count"], 0)

    def test_index_writes_both_artifacts(self):
        code, payload = run(vault.command_index, self.root, True)
        self.assertEqual(code, 0)
        self.assertGreater(payload["indexed"], 0)
        self.assertTrue((self.root / vault.GENERATED_JSON).exists())
        self.assertTrue((self.root / vault.GENERATED_MARKDOWN).exists())
        data = json.loads((self.root / vault.GENERATED_JSON).read_text(encoding="utf-8"))
        entry = next(n for n in data["notes"] if n["path"].endswith("Retrieval.md"))
        self.assertIn("40-knowledge/concepts/MOC - Concepts.md", entry["outbound"])

    def test_related_traverses_neighbours(self):
        code, payload = run(vault.command_related, self.root, "40-knowledge/concepts/Retrieval.md", 1, True)
        self.assertEqual(code, 0)
        self.assertIn("40-knowledge/concepts/MOC - Concepts.md", [n["path"] for n in payload["neighbors"]])

    def test_related_reports_a_missing_note(self):
        code, payload = run(vault.command_related, self.root, "Nope.md", 1, True)
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"], "note_not_found")


class PackTests(VaultFixture):
    def test_pack_respects_the_budget(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = vault.command_pack(self.root, "retrieval", vault.QueryOptions(limit=5), 200)
        output = buffer.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("# Context pack: retrieval", output)
        self.assertIn("Retrieval", output)
        self.assertLessEqual(len(output), 200 * vault.CHARS_PER_TOKEN)

    def test_pack_hard_ceiling_includes_header_and_footer(self):
        budget = 120
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = vault.command_pack(self.root, "retrieval", vault.QueryOptions(limit=5), budget)
        self.assertEqual(code, 0)
        self.assertLessEqual(len(buffer.getvalue()), budget * vault.CHARS_PER_TOKEN)

    def test_pack_hard_ceiling_survives_windows_crlf_expansion(self):
        budget = 120
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = vault.command_pack(self.root, "retrieval", vault.QueryOptions(limit=5), budget)
        self.assertEqual(code, 0)
        windows_rendered = buffer.getvalue().replace("\n", "\r\n")
        self.assertLessEqual(len(windows_rendered), budget * vault.CHARS_PER_TOKEN)


class SkillPointerTests(VaultFixture):
    def canonical(self, name="vault-maintenance", description="Do vault things."):
        self.write(f"90-system/skills/{name}/SKILL.md",
                   f"---\nname: {name}\ndescription: {description}\n---\n\n# Skill\n")

    def pointer(self, adapter, name="vault-maintenance", target=None, declared=None,
                description="Do vault things."):
        target = target or f"../../../90-system/skills/{name}/SKILL.md"
        self.write(f".{adapter}/skills/{name}/SKILL.md",
                   f"---\nname: {declared or name}\ndescription: {description}\n---\n\n"
                   f"Read `{target}` completely, then follow it.\n")

    def test_valid_pointer_passes(self):
        self.canonical()
        self.pointer("claude")
        self.assertEqual(vault.check_skill_pointers(self.root), [])

    def test_missing_target_is_reported(self):
        self.pointer("claude", target="../../../90-system/skills/ghost/SKILL.md")
        findings = vault.check_skill_pointers(self.root)
        self.assertEqual(findings[0]["issue"], "missing_target")

    def test_pointer_without_reference_is_reported(self):
        self.canonical()
        self.write(".claude/skills/vault-maintenance/SKILL.md",
                   "---\nname: vault-maintenance\ndescription: x\n---\n\nNo reference here.\n")
        self.assertEqual(vault.check_skill_pointers(self.root)[0]["issue"], "no_canonical_reference")

    def test_name_mismatch_is_reported(self):
        self.canonical()
        self.pointer("agents", declared="something-else")
        issues = {finding["issue"] for finding in vault.check_skill_pointers(self.root)}
        self.assertIn("name_mismatch", issues)

    def test_description_mismatch_is_reported(self):
        self.canonical()
        self.pointer("agents", description="Drifted trigger description.")
        issues = {finding["issue"] for finding in vault.check_skill_pointers(self.root)}
        self.assertIn("description_mismatch", issues)

    def test_vault_root_reference_is_rejected_as_non_relative_to_adapter(self):
        self.canonical()
        self.pointer("agents", target="90-system/skills/vault-maintenance/SKILL.md")
        issues = {finding["issue"] for finding in vault.check_skill_pointers(self.root)}
        self.assertIn("unexpected_target", issues)


class PathCasingTests(unittest.TestCase):
    """Folder names are lowercase-kebab. Windows is case-insensitive, so a stray capital
    resolves fine here and only breaks on Linux -- these tests make it fail everywhere."""

    SEGMENT = re.compile(r"^[0-9a-z._-]+$")

    def assert_lowercase_path(self, value, source):
        parts = value.replace("\\", "/").strip("/").split("/")
        if "." in parts[-1]:
            parts = parts[:-1]  # Trailing filename; only directory segments are constrained.
        for segment in parts:
            self.assertRegex(segment, self.SEGMENT, f"{source}: {value!r}")

    def test_path_constants_are_lowercase(self):
        for name in ("GENERATED_MARKDOWN", "GENERATED_JSON", "CACHE_RELATIVE", "RAW_SOURCE_PREFIX"):
            self.assert_lowercase_path(getattr(vault, name), name)
        for group in ("EXEMPT_PREFIXES", "RETRIEVAL_EXCLUDED",
                      "PLACEMENT_EXEMPT_PREFIXES", "MOC_EXEMPT_PREFIXES"):
            for value in getattr(vault, group):
                self.assert_lowercase_path(value, group)
        for note_type, folder in vault.TYPE_FOLDERS.items():
            self.assert_lowercase_path(folder, f"TYPE_FOLDERS[{note_type}]")

    def test_repository_directories_are_lowercase(self):
        root = vault.vault_root()
        offenders = []
        for path in root.rglob("*"):
            if not path.is_dir():
                continue
            relative = path.relative_to(root)
            if relative.parts[0] in {".git", ".obsidian"}:
                continue
            for segment in relative.parts:
                if not self.SEGMENT.match(segment):
                    offenders.append(relative.as_posix())
                    break
        self.assertEqual(offenders, [], "directories must be lowercase-kebab")


if __name__ == "__main__":
    unittest.main()
