#!/usr/bin/env python3
"""Deterministic indexing, retrieval, graph traversal, authoring, and linting for this vault.

Standard library only. The Markdown files are always the source of truth; the SQLite
cache under ``90-system/indexes`` is disposable and can be rebuilt at any time.

Retrieval design
----------------
Queries run against an inverted index (``postings``) rather than a full corpus scan, and
rank with BM25F: per-field term-frequency normalisation followed by a single saturation
step. Parsing is incremental -- a file is re-read only when its mtime or size changes --
so repeated commands cost a ``stat`` per note instead of a read plus a tokenise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA_VERSION = 4

WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
WORD_RE = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
TASK_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.*?)\s*$")
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
INLINE_LIST_RE = re.compile(r"^\[(.*)\]$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ANCHOR = "vault:links"
RAW_SOURCE_PREFIX = "30-resources/sources/raw/"
RAW_SOURCE_BEGIN = "<!-- raw-source:begin -->"
RAW_SOURCE_END = "<!-- raw-source:end -->"
RAW_SOURCE_HASH_KEY = "content_sha256"

FRESHNESS_MODES = {"timeless", "snapshot", "pointer"}
DEFAULT_FRESHNESS_DAYS = 30
RELATION_INVERSES = {
    "supersedes": "superseded_by",
    "superseded_by": "supersedes",
    "depends_on": "required_by",
    "required_by": "depends_on",
    "supports": "supported_by",
    "supported_by": "supports",
    "contradicts": "contradicts",
}
RELATION_FIELDS = tuple(RELATION_INVERSES)

EXCLUDED_DIRS = {".agents", ".claude", ".git", ".obsidian", "__pycache__", ".trash"}
REQUIRED_KEYS = ("id", "type", "status", "created", "updated")
ROOT_EXEMPT = {"AGENTS.md", "CLAUDE.md"}
EXEMPT_PREFIXES = ("90-system/templates/", "90-system/skills/", "90-system/indexes/")
RETRIEVAL_EXCLUDED = ("90-system/templates/", "90-system/skills/_template/", "90-system/indexes/")

GENERATED_MARKDOWN = "90-system/indexes/Vault Index.md"
GENERATED_JSON = "90-system/indexes/vault-index.json"
CACHE_RELATIVE = "90-system/indexes/.vault-cache.sqlite3"
RETRIEVAL_CASES_RELATIVE = "90-system/evals/retrieval-cases.jsonl"
RETRIEVAL_REPORT_RELATIVE = "90-system/evals/retrieval-report.json"
RETRIEVAL_EVAL_SCHEMA_VERSION = 1

KNOWN_TYPES = (
    "moc", "project", "area", "resource", "source", "raw-source", "concept", "person",
    "organization", "journal", "review", "decision", "note", "system",
)

# Folder each note type belongs in. `check placement` verifies membership; `new` uses it
# to choose a destination. Types absent from this map are unconstrained.
TYPE_FOLDERS = {
    "project": "10-projects",
    "area": "20-areas",
    "resource": "30-resources",
    "source": "30-resources/sources",
    "raw-source": "30-resources/sources/raw",
    "concept": "40-knowledge/concepts",
    "person": "40-knowledge/people",
    "organization": "40-knowledge/organizations",
    "journal": "50-journal/daily",
    "review": "50-journal/weekly",
    "decision": "60-decisions",
    "system": "90-system",
    "note": "00-inbox",
}

# Types whose placement is advisory rather than enforced: `note` is the catch-all capture
# type and legitimately lives anywhere, and `moc` sits inside the folder it indexes.
PLACEMENT_UNCONSTRAINED = {"moc", "note"}

# Folders whose contents are exempt from placement and MOC-coverage checks.
PLACEMENT_EXEMPT_PREFIXES = ("00-inbox/", "80-archive/", "90-system/", "99-attachments/")
MOC_EXEMPT_PREFIXES = ("80-archive/", "90-system/", "99-attachments/")

TYPE_TEMPLATES = {
    "note": "Note Template.md",
    "project": "Project Template.md",
    "area": "Area Template.md",
    "resource": "Resource Template.md",
    "source": "Source Template.md",
    "raw-source": "Raw Source Template.md",
    "concept": "Concept Template.md",
    "person": "Person Template.md",
    "organization": "Organization Template.md",
    "decision": "Decision Template.md",
    "journal": "Daily Note Template.md",
    "review": "Weekly Review Template.md",
    "moc": "MOC Template.md",
}

# BM25F parameters. Field weights preserve the previous ranking intent (title strongest,
# frontmatter next, body baseline); k1 controls saturation and b controls length
# normalisation. Tuned for short atomic notes.
FIELD_WEIGHTS = {"title": 8.0, "meta": 3.0, "body": 1.0}
BM25_K1 = 1.2
BM25_B = 0.75
PHRASE_TITLE_BONUS = 12.0
PHRASE_BODY_BONUS = 4.0
PHRASE_CANDIDATES = 50
DEFAULT_EXCERPT_CHARS = 320
COMPACT_EXCERPT_CHARS = 160
CHARS_PER_TOKEN = 4  # Deliberately rough; `pack` reports the exact character count too.

ERROR_KEYS = (
    "unresolved_links", "duplicate_ids", "duplicate_titles", "skill_pointers",
    "raw_source_integrity", "typed_relation_integrity",
)
WARNING_KEYS = (
    "metadata_issues", "placement", "moc_coverage", "orphans", "stale",
    "tag_vocabulary", "raw_source_drafts", "freshness", "typed_relation_inverses",
)

DEFAULT_STALE_DAYS = 180
DEFAULT_MAX_TAGS = 60

# German spellings-out, applied before Unicode decomposition when building an id.
TRANSLITERATIONS = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


@dataclass
class Note:
    path: str
    title: str
    metadata: dict[str, Any]
    body: str
    links: list[str]
    headings: list[str]
    tasks: list[dict[str, Any]]
    word_count: int
    sha256: str
    mtime_ns: int = 0
    size: int = 0
    terms: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    lengths: tuple[int, int, int] = (0, 0, 0)

    @property
    def stem(self) -> str:
        return Path(self.path).stem


def vault_root() -> Path:
    return Path(__file__).resolve().parents[2]


def tokenize(text: str) -> list[str]:
    return [token.casefold() for token in WORD_RE.findall(text)]


def parse_scalar(value: str) -> Any:
    """Parse a YAML scalar subset: quoted strings, inline lists, booleans, plain text."""
    value = value.strip()
    if not value:
        return ""
    inline = INLINE_LIST_RE.match(value)
    if inline:
        inner = inline.group(1).strip()
        if not inner:
            return []
        return [parse_scalar(item) for item in split_inline_list(inner)]
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "~"}:
        return ""
    if (value.startswith('"') and value.endswith('"') and len(value) > 1) or (
        value.startswith("'") and value.endswith("'") and len(value) > 1
    ):
        return value[1:-1]
    return value


def split_inline_list(inner: str) -> list[str]:
    """Split ``a, "b, c", d`` on commas that sit outside quotes."""
    items: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in inner:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            current.append(char)
            continue
        if char == ",":
            items.append("".join(current))
            current = []
            continue
        current.append(char)
    items.append("".join(current))
    return [item for item in (part.strip() for part in items) if item]


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse the YAML subset Obsidian writes.

    Supports scalars, block lists, inline lists, one level of nested mapping, and block
    scalars (``|`` / ``>``, captured as a joined string). Deeper nesting is skipped rather
    than guessed at, so a mis-parse degrades to a missing key instead of a wrong value.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return {}, text

    block = lines[1:end]
    metadata: dict[str, Any] = {}
    index = 0
    while index < len(block):
        line = block[index]
        stripped = line.strip()
        index += 1
        if not stripped or stripped.startswith("#") or stripped.startswith("- "):
            continue
        if (len(line) - len(line.lstrip(" "))) > 0 or ":" not in line:
            continue  # An orphaned child line; its parent already consumed what it needed.

        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        value = raw_value.strip()

        if value not in {"", "|", ">", "|-", ">-", "|+", ">+"}:
            metadata[key] = parse_scalar(raw_value)
            continue

        # The value continues on the indented lines that follow.
        children: list[str] = []
        while index < len(block):
            child = block[index]
            if child.strip() and (len(child) - len(child.lstrip(" "))) == 0:
                break
            children.append(child)
            index += 1

        if value:  # Block scalar: join the indented lines into one string.
            metadata[key] = " ".join(child.strip() for child in children if child.strip())
            continue

        collected_list: list[Any] = []
        collected_map: dict[str, Any] = {}
        for child in children:
            child_stripped = child.strip()
            if not child_stripped or child_stripped.startswith("#"):
                continue
            if child_stripped.startswith("- "):
                collected_list.append(parse_scalar(child_stripped[2:]))
            elif ":" in child_stripped:
                child_key, child_value = child_stripped.split(":", 1)
                collected_map[child_key.strip()] = parse_scalar(child_value)
        if collected_list:
            metadata[key] = collected_list
        elif collected_map:
            metadata[key] = collected_map
        else:
            metadata[key] = ""

    return metadata, "\n".join(lines[end + 1:])


def extract_title(body: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def strip_code(text: str) -> str:
    text = re.sub(r"\x60{3}.*?\x60{3}", "", text, flags=re.DOTALL)
    return re.sub(r"\x60[^\x60\n]*\x60", "", text)


def extract_links(text: str) -> list[str]:
    links: list[str] = []
    for match in WIKILINK_RE.finditer(strip_code(text)):
        target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        if target and not target.startswith(("http://", "https://")):
            if target.casefold().endswith(".md"):
                target = target[:-3]
            links.append(target.replace("\\", "/").lstrip("/"))
    return links


def extract_tasks(body: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    in_fence = False
    for number, line in enumerate(body.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = TASK_RE.match(line)
        if match and match.group(2):
            tasks.append({"line": number, "done": match.group(1).lower() == "x", "text": match.group(2)})
    return tasks


def note_tags(metadata: dict[str, Any]) -> list[str]:
    raw = metadata.get("tags", [])
    if isinstance(raw, str):
        raw = [part for part in re.split(r"[,\s]+", raw) if part]
    if not isinstance(raw, list):
        return []
    return [str(item).strip().lstrip("#") for item in raw if str(item).strip()]


def metadata_text(metadata: dict[str, Any]) -> str:
    values: list[str] = []
    for value in metadata.values():
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif isinstance(value, dict):
            values.extend(f"{key} {item}" for key, item in value.items())
        else:
            values.append(str(value))
    return " ".join(values)


def build_note(path: Path, relative: str, raw: str, mtime_ns: int, size: int) -> Note:
    metadata, body = parse_frontmatter(raw)
    title = extract_title(body, path.stem)
    title_tokens = Counter(tokenize(title))
    meta_tokens = Counter(tokenize(metadata_text(metadata)))
    body_tokens = Counter(tokenize(body))
    vocabulary = set(title_tokens) | set(meta_tokens) | set(body_tokens)
    terms = {
        term: (title_tokens.get(term, 0), meta_tokens.get(term, 0), body_tokens.get(term, 0))
        for term in vocabulary
    }
    return Note(
        path=relative,
        title=title,
        metadata=metadata,
        body=body,
        links=extract_links(raw),
        headings=[match.group(2).strip() for match in HEADING_RE.finditer(body)],
        tasks=extract_tasks(body),
        word_count=sum(body_tokens.values()),
        sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        mtime_ns=mtime_ns,
        size=size,
        terms=terms,
        lengths=(sum(title_tokens.values()), sum(meta_tokens.values()), sum(body_tokens.values())),
    )


def iter_markdown(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.md"), key=lambda item: item.as_posix().casefold()):
        relative = path.relative_to(root)
        if any(part.startswith(".") or part in EXCLUDED_DIRS for part in relative.parts[:-1]):
            continue
        yield path


def asset_maps(root: Path) -> tuple[set[str], dict[str, list[str]]]:
    """Index non-Markdown vault files for attachment-aware wikilink validation.

    Obsidian can link or embed images, PDFs, Bases, and other files. They are not Note
    objects and therefore do not participate in note adjacency, but an existing asset must
    still satisfy link validation. Hidden runtime state is deliberately excluded.
    """
    by_path: set[str] = set()
    by_name: dict[str, list[str]] = defaultdict(list)
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file() or path.suffix.casefold() == ".md":
            continue
        relative_path = path.relative_to(root)
        if any(part.startswith(".") or part in EXCLUDED_DIRS for part in relative_path.parts):
            continue
        relative = relative_path.as_posix()
        by_path.add(relative.casefold())
        by_name[path.name.casefold()].append(relative)
    return by_path, by_name


def read_note(root: Path, path: Path) -> Note:
    stat = path.stat()
    raw = path.read_text(encoding="utf-8-sig")
    return build_note(path, path.relative_to(root).as_posix(), raw, stat.st_mtime_ns, stat.st_size)


def scan_notes(root: Path) -> list[Note]:
    """Read and parse every note without touching the cache. Used by tests and rebuilds."""
    return [read_note(root, path) for path in iter_markdown(root)]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def trigrams(term: str) -> set[str]:
    padded = f"  {term} "
    return {padded[index:index + 3] for index in range(len(padded) - 2)}


class VaultCache:
    """Incremental SQLite store: parsed notes plus an inverted index over their terms.

    Only files whose ``(mtime_ns, size)`` changed are re-read, so a warm run costs one
    ``stat`` per note. Query time is proportional to the matched posting lists rather
    than to the size of the vault.
    """

    def __init__(self, root: Path, path: Path | None = None) -> None:
        self.root = root
        self.path = path or (root / CACHE_RELATIVE)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        version = None
        try:
            row = self.connection.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            version = int(row["value"]) if row else None
        except sqlite3.DatabaseError:
            version = None
        if version != SCHEMA_VERSION:
            for table in ("postings", "trigrams", "docs", "meta"):
                self.connection.execute(f"DROP TABLE IF EXISTS {table}")
            self.connection.executescript(
                """
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE docs (
                    path TEXT PRIMARY KEY,
                    mtime_ns INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    title TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    headings TEXT NOT NULL,
                    links TEXT NOT NULL,
                    tasks TEXT NOT NULL,
                    word_count INTEGER NOT NULL,
                    len_title INTEGER NOT NULL,
                    len_meta INTEGER NOT NULL,
                    len_body INTEGER NOT NULL
                );
                CREATE TABLE postings (
                    term TEXT NOT NULL,
                    path TEXT NOT NULL,
                    tf_title INTEGER NOT NULL,
                    tf_meta INTEGER NOT NULL,
                    tf_body INTEGER NOT NULL,
                    PRIMARY KEY (term, path)
                ) WITHOUT ROWID;
                CREATE INDEX postings_path ON postings(path);
                CREATE TABLE trigrams (
                    tri TEXT NOT NULL,
                    term TEXT NOT NULL,
                    PRIMARY KEY (tri, term)
                ) WITHOUT ROWID;
                """
            )
            self.connection.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),)
            )
            self.connection.commit()

    def sync(self) -> dict[str, int]:
        """Bring the cache in line with the filesystem. Returns per-action counts."""
        on_disk: dict[str, tuple[Path, int, int]] = {}
        for path in iter_markdown(self.root):
            stat = path.stat()
            on_disk[path.relative_to(self.root).as_posix()] = (path, stat.st_mtime_ns, stat.st_size)

        cached = {
            row["path"]: (row["mtime_ns"], row["size"])
            for row in self.connection.execute("SELECT path, mtime_ns, size FROM docs")
        }
        removed = sorted(set(cached) - set(on_disk))
        changed = [
            relative for relative, (_, mtime_ns, size) in on_disk.items()
            if cached.get(relative) != (mtime_ns, size)
        ]

        for relative in removed:
            self._delete(relative)
        for relative in sorted(changed):
            path, mtime_ns, size = on_disk[relative]
            raw = path.read_text(encoding="utf-8-sig")
            self._upsert(build_note(path, relative, raw, mtime_ns, size))

        if removed or changed:
            self.connection.execute(
                "DELETE FROM trigrams WHERE term NOT IN (SELECT term FROM postings)"
            )
            self.connection.commit()
        return {"total": len(on_disk), "reparsed": len(changed), "removed": len(removed)}

    def _delete(self, relative: str) -> None:
        self.connection.execute("DELETE FROM postings WHERE path = ?", (relative,))
        self.connection.execute("DELETE FROM docs WHERE path = ?", (relative,))

    def _upsert(self, note: Note) -> None:
        self._delete(note.path)
        self.connection.execute(
            """
            INSERT INTO docs (path, mtime_ns, size, sha256, title, metadata, headings, links,
                              tasks, word_count, len_title, len_meta, len_body)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note.path, note.mtime_ns, note.size, note.sha256, note.title,
                json.dumps(note.metadata, ensure_ascii=False),
                json.dumps(note.headings, ensure_ascii=False),
                json.dumps(note.links, ensure_ascii=False),
                json.dumps(note.tasks, ensure_ascii=False),
                note.word_count, *note.lengths,
            ),
        )
        self.connection.executemany(
            "INSERT INTO postings (term, path, tf_title, tf_meta, tf_body) VALUES (?, ?, ?, ?, ?)",
            [(term, note.path, *counts) for term, counts in note.terms.items()],
        )
        self.connection.executemany(
            "INSERT OR IGNORE INTO trigrams (tri, term) VALUES (?, ?)",
            [(tri, term) for term in note.terms for tri in trigrams(term)],
        )

    def notes(self, paths: Iterable[str] | None = None) -> list[Note]:
        """Load every note, or only the given paths when a query narrowed the field.

        Bodies are excluded: they are the bulk of the cache and only the handful of notes
        a query actually returns ever need them. Use `hydrate_bodies` for those.
        """
        if paths is None:
            rows: Iterable[sqlite3.Row] = self.connection.execute(
                """
                SELECT path, sha256, title, metadata, headings, links, tasks,
                       word_count, len_title, len_meta, len_body, mtime_ns, size
                FROM docs ORDER BY path COLLATE NOCASE
                """
            )
        else:
            wanted = list(paths)
            if not wanted:
                return []
            placeholders = ",".join("?" * len(wanted))
            rows = self.connection.execute(
                f"""
                SELECT path, sha256, title, metadata, headings, links, tasks,
                       word_count, len_title, len_meta, len_body, mtime_ns, size
                FROM docs WHERE path IN ({placeholders}) ORDER BY path COLLATE NOCASE
                """,
                tuple(wanted),
            )
        return [
            Note(
                path=row["path"],
                title=row["title"],
                metadata=json.loads(row["metadata"]),
                body="",  # Hydrated on demand; see hydrate_bodies.
                links=json.loads(row["links"]),
                headings=json.loads(row["headings"]),
                tasks=json.loads(row["tasks"]),
                word_count=row["word_count"],
                sha256=row["sha256"],
                mtime_ns=row["mtime_ns"],
                size=row["size"],
                lengths=(row["len_title"], row["len_meta"], row["len_body"]),
            )
            for row in rows
        ]

    def corpus_stats(self) -> tuple[int, tuple[float, float, float]]:
        row = self.connection.execute(
            "SELECT COUNT(*) AS n, AVG(len_title) AS t, AVG(len_meta) AS m, AVG(len_body) AS b FROM docs"
        ).fetchone()
        count = row["n"] or 0
        return count, (row["t"] or 1.0, row["m"] or 1.0, row["b"] or 1.0)

    def postings(self, term: str) -> list[sqlite3.Row]:
        """Posting list joined with the field lengths BM25F needs for normalisation."""
        return list(
            self.connection.execute(
                """
                SELECT p.path, p.tf_title, p.tf_meta, p.tf_body,
                       d.len_title, d.len_meta, d.len_body
                FROM postings p JOIN docs d ON d.path = p.path
                WHERE p.term = ?
                """,
                (term,),
            )
        )

    def document_frequency(self, term: str) -> int:
        return self.connection.execute(
            "SELECT COUNT(*) FROM postings WHERE term = ?", (term,)
        ).fetchone()[0]

    def expand_prefix(self, prefix: str, limit: int = 24) -> list[str]:
        """Range scan on the postings primary key -- the SQL equivalent of a bisect."""
        upper = prefix[:-1] + chr(ord(prefix[-1]) + 1) if prefix else prefix
        rows = self.connection.execute(
            "SELECT DISTINCT term FROM postings WHERE term >= ? AND term < ? LIMIT ?",
            (prefix, upper, limit),
        )
        return [row["term"] for row in rows]

    def expand_fuzzy(self, term: str, limit: int = 3, cutoff: float = 0.78) -> list[str]:
        """Trigram-indexed candidate lookup, then exact similarity on the shortlist.

        The trigram probe replaces a full vocabulary scan: only terms sharing at least
        one trigram are considered, which is a small fraction of the vocabulary.
        """
        query_trigrams = trigrams(term)
        if not query_trigrams:
            return []
        placeholders = ",".join("?" * len(query_trigrams))
        rows = self.connection.execute(
            f"SELECT term, COUNT(*) AS hits FROM trigrams WHERE tri IN ({placeholders}) "
            "GROUP BY term ORDER BY hits DESC LIMIT 200",
            tuple(query_trigrams),
        )
        scored: list[tuple[float, str]] = []
        for row in rows:
            candidate = row["term"]
            if candidate == term or abs(len(candidate) - len(term)) > 3:
                continue
            ratio = SequenceMatcher(None, term, candidate).ratio()
            if ratio >= cutoff:
                scored.append((ratio, candidate))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [candidate for _, candidate in scored[:limit]]

    def stats(self) -> dict[str, Any]:
        counts = {
            "notes": self.connection.execute("SELECT COUNT(*) FROM docs").fetchone()[0],
            "terms": self.connection.execute("SELECT COUNT(DISTINCT term) FROM postings").fetchone()[0],
            "postings": self.connection.execute("SELECT COUNT(*) FROM postings").fetchone()[0],
            "trigrams": self.connection.execute("SELECT COUNT(*) FROM trigrams").fetchone()[0],
        }
        counts["cache_bytes"] = self.path.stat().st_size if self.path.exists() else 0
        counts["schema_version"] = SCHEMA_VERSION
        return counts

    def close(self) -> None:
        self.connection.close()


def open_cache(root: Path, rebuild: bool = False) -> VaultCache:
    cache_path = root / CACHE_RELATIVE
    if rebuild:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(cache_path) + suffix)
            if candidate.exists():
                candidate.unlink()
    cache = VaultCache(root, cache_path)
    cache.sync()
    return cache


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def hydrate_bodies(root: Path, notes: Iterable[Note]) -> None:
    """Read note bodies from disk for the few notes that need them (excerpts, packing)."""
    for note in notes:
        if note.body:
            continue
        path = root / note.path
        if path.is_file():
            _, note.body = parse_frontmatter(path.read_text(encoding="utf-8-sig"))


def note_maps(notes: list[Note]) -> tuple[dict[str, Note], dict[str, list[Note]]]:
    by_path = {note.path.removesuffix(".md").casefold(): note for note in notes}
    by_stem: dict[str, list[Note]] = defaultdict(list)
    for note in notes:
        by_stem[note.stem.casefold()].append(note)
    return by_path, by_stem


def resolve_target(target: str, by_path: dict[str, Note], by_stem: dict[str, list[Note]]) -> Note | None:
    normalized = target.removesuffix(".md").replace("\\", "/").strip("/").casefold()
    if normalized in by_path:
        return by_path[normalized]
    candidates = by_stem.get(Path(normalized).name, [])
    return candidates[0] if len(candidates) == 1 else None


def resolve_asset_target(
    target: str, asset_by_path: set[str], asset_by_name: dict[str, list[str]]
) -> str | None:
    """Resolve an attachment by vault-root path or by an unambiguous filename."""
    normalized = target.replace("\\", "/").strip("/").casefold()
    if normalized in asset_by_path:
        return normalized
    candidates = asset_by_name.get(Path(normalized).name, [])
    return candidates[0] if len(candidates) == 1 else None


def graph(
    notes: list[Note],
    assets: tuple[set[str], dict[str, list[str]]] | None = None,
) -> tuple[dict[str, set[str]], list[dict[str, str]]]:
    by_path, by_stem = note_maps(notes)
    asset_by_path, asset_by_name = assets or (set(), {})
    adjacency: dict[str, set[str]] = {note.path: set() for note in notes}
    unresolved: list[dict[str, str]] = []
    for note in notes:
        for target in note.links:
            resolved = resolve_target(target, by_path, by_stem)
            if not resolved:
                if resolve_asset_target(target, asset_by_path, asset_by_name):
                    continue
                unresolved.append({"source": note.path, "target": target})
                continue
            adjacency[note.path].add(resolved.path)
            adjacency[resolved.path].add(note.path)
    return adjacency, unresolved


def outbound_links(
    note: Note,
    by_path: dict[str, Note],
    by_stem: dict[str, list[Note]],
    assets: tuple[set[str], dict[str, list[str]]] | None = None,
) -> tuple[list[str], list[str]]:
    asset_by_path, asset_by_name = assets or (set(), {})
    resolved_paths: list[str] = []
    unresolved: list[str] = []
    for target in note.links:
        resolved = resolve_target(target, by_path, by_stem)
        if resolved:
            resolved_paths.append(resolved.path)
        elif not resolve_asset_target(target, asset_by_path, asset_by_name):
            unresolved.append(target)
    return sorted(set(resolved_paths), key=str.casefold), sorted(set(unresolved), key=str.casefold)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def emit(payload: Any, compact: bool) -> None:
    if compact:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def slugify(value: str) -> str:
    # Transliterate before decomposing: NFKD maps "ö" to "o" but drops "ß" entirely,
    # which would turn "Größen" into "groen".
    for source, replacement in TRANSLITERATIONS.items():
        value = value.replace(source, replacement)
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug or "note"


def resolve_vault_path(root: Path, requested: str | Path) -> tuple[Path, str] | None:
    """Resolve a path and prove that its final location remains inside the vault root.

    Resolving before mutation rejects parent traversal and follows any existing symlink or
    junction, so an apparently internal folder cannot redirect a write outside the vault.
    """
    candidate = Path(requested)
    path = candidate if candidate.is_absolute() else root / candidate
    try:
        root_resolved = root.resolve()
        resolved = path.resolve()
        relative = resolved.relative_to(root_resolved).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved, relative


def parse_date(value: Any) -> date | None:
    text = str(value).strip().strip("\"'")
    if not DATE_RE.match(text):
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def raw_source_payload(text: str) -> str | None:
    """Return the normalized payload between the two raw-source sentinels.

    The sentinels make the immutable boundary explicit: metadata and derived-note links
    may evolve without changing the captured source. Duplicate, missing, or reversed
    sentinels are rejected instead of guessing which region is authoritative.
    """
    if text.count(RAW_SOURCE_BEGIN) != 1 or text.count(RAW_SOURCE_END) != 1:
        return None
    start = text.index(RAW_SOURCE_BEGIN) + len(RAW_SOURCE_BEGIN)
    end = text.index(RAW_SOURCE_END)
    if start >= end:
        return None
    payload = text[start:end]
    if payload.startswith("\r\n"):
        payload = payload[2:]
    elif payload.startswith(("\n", "\r")):
        payload = payload[1:]
    if payload.endswith("\r\n"):
        payload = payload[:-2]
    elif payload.endswith(("\n", "\r")):
        payload = payload[:-1]
    return payload.replace("\r\n", "\n").replace("\r", "\n")


def raw_source_digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def raw_source_finding(root: Path, note: Note) -> dict[str, str] | None:
    """Validate one sealed raw source without mutating it."""
    path = root / note.path
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return {"path": note.path, "issue": "unreadable"}
    payload = raw_source_payload(text)
    if payload is None:
        return {"path": note.path, "issue": "invalid_or_missing_payload_boundary"}
    recorded = str(note.metadata.get(RAW_SOURCE_HASH_KEY, "")).strip()
    if not recorded:
        return {"path": note.path, "issue": "missing_content_sha256"}
    actual = raw_source_digest(payload)
    if recorded != actual:
        return {
            "path": note.path,
            "issue": "payload_changed_after_seal",
            "recorded": recorded,
            "actual": actual,
        }
    return None


def metadata_values(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def parse_positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def freshness_findings(note: Note, today: date) -> list[dict[str, Any]]:
    """Validate explicit freshness metadata; never guess volatility from prose."""
    mode = str(note.metadata.get("freshness", "")).strip()
    if not mode:
        return []
    findings: list[dict[str, Any]] = []
    if mode not in FRESHNESS_MODES:
        return [{"path": note.path, "issue": "unknown_mode", "value": mode}]

    if mode == "snapshot":
        observed = parse_date(note.metadata.get("observed", ""))
        if observed is None:
            findings.append({"path": note.path, "issue": "snapshot_missing_observed_date"})
    elif mode == "pointer":
        if not str(note.metadata.get("truth_source", "")).strip():
            findings.append({"path": note.path, "issue": "pointer_missing_truth_source"})
        verified = parse_date(note.metadata.get("last_verified", ""))
        if verified is None:
            findings.append({"path": note.path, "issue": "pointer_missing_last_verified"})
        else:
            window = parse_positive_int(
                note.metadata.get("freshness_window_days", ""), DEFAULT_FRESHNESS_DAYS
            )
            age = (today - verified).days
            if age > window:
                findings.append(
                    {
                        "path": note.path,
                        "issue": "verification_expired",
                        "last_verified": verified.isoformat(),
                        "age_days": age,
                        "window_days": window,
                    }
                )

    valid_from_raw = str(note.metadata.get("valid_from", "")).strip()
    valid_until_raw = str(note.metadata.get("valid_until", "")).strip()
    valid_from = parse_date(valid_from_raw) if valid_from_raw else None
    valid_until = parse_date(valid_until_raw) if valid_until_raw not in {"", "present"} else None
    if valid_from_raw and valid_from is None:
        findings.append({"path": note.path, "issue": "invalid_valid_from"})
    if valid_until_raw not in {"", "present"} and valid_until is None:
        findings.append({"path": note.path, "issue": "invalid_valid_until"})
    if valid_from and valid_until and valid_until < valid_from:
        findings.append({"path": note.path, "issue": "valid_until_before_valid_from"})
    return findings


def supersession_cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    """Return unique directed cycles in the supersedes graph."""
    state: dict[str, int] = {}
    stack: list[str] = []
    positions: dict[str, int] = {}
    cycles: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        positions[node] = len(stack)
        stack.append(node)
        for target in sorted(edges.get(node, set()), key=str.casefold):
            if state.get(target, 0) == 0:
                visit(target)
            elif state.get(target) == 1:
                cycle = stack[positions[target]:]
                if cycle:
                    rotations = [tuple(cycle[index:] + cycle[:index]) for index in range(len(cycle))]
                    cycles.add(min(rotations))
        stack.pop()
        positions.pop(node, None)
        state[node] = 2

    for node in sorted(edges, key=str.casefold):
        if state.get(node, 0) == 0:
            visit(node)
    return [list(cycle) for cycle in sorted(cycles)]


def typed_relation_findings(
    notes: list[Note],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate flat typed-link fields and report missing inverse declarations."""
    by_path, by_stem = note_maps(notes)
    errors: list[dict[str, Any]] = []
    relations: set[tuple[str, str, str]] = set()
    supersedes: dict[str, set[str]] = defaultdict(set)

    for note in notes:
        for relation in RELATION_FIELDS:
            for raw_target in metadata_values(note.metadata.get(relation)):
                targets = extract_links(raw_target)
                if len(targets) != 1:
                    errors.append(
                        {
                            "path": note.path,
                            "relation": relation,
                            "target": raw_target,
                            "issue": "target_must_be_one_wikilink",
                        }
                    )
                    continue
                resolved = resolve_target(targets[0], by_path, by_stem)
                if resolved is None:
                    errors.append(
                        {
                            "path": note.path,
                            "relation": relation,
                            "target": targets[0],
                            "issue": "dangling_target",
                        }
                    )
                    continue
                if resolved.path == note.path:
                    errors.append(
                        {
                            "path": note.path,
                            "relation": relation,
                            "target": resolved.path,
                            "issue": "self_relation",
                        }
                    )
                    continue
                relations.add((note.path, relation, resolved.path))
                if relation == "supersedes":
                    supersedes[note.path].add(resolved.path)

    for cycle in supersession_cycles(supersedes):
        errors.append({"issue": "supersession_cycle", "paths": cycle})

    missing_inverses = []
    for source, relation, target in sorted(relations):
        inverse = RELATION_INVERSES[relation]
        if (target, inverse, source) not in relations:
            missing_inverses.append(
                {
                    "path": source,
                    "relation": relation,
                    "target": target,
                    "missing_inverse": inverse,
                }
            )
    return errors, missing_inverses


def retrieval_filtered(notes: list[Note], include_templates: bool) -> list[Note]:
    if include_templates:
        return notes
    return [note for note in notes if not note.path.startswith(RETRIEVAL_EXCLUDED)]


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------


def command_index(root: Path, compact: bool) -> int:
    cache = open_cache(root)
    notes = cache.notes()
    by_path, by_stem = note_maps(notes)  # Built once; previously rebuilt per note.
    assets = asset_maps(root)
    records = []
    for note in notes:
        resolved, unresolved = outbound_links(note, by_path, by_stem, assets)
        records.append(
            {
                "path": note.path,
                "title": note.title,
                "id": note.metadata.get("id", ""),
                "type": note.metadata.get("type", ""),
                "status": note.metadata.get("status", ""),
                "updated": note.metadata.get("updated", ""),
                "aliases": note.metadata.get("aliases", []),
                "tags": note_tags(note.metadata),
                "relations": {
                    relation: metadata_values(note.metadata.get(relation))
                    for relation in RELATION_FIELDS
                    if metadata_values(note.metadata.get(relation))
                },
                "word_count": note.word_count,
                "headings": note.headings,
                "outbound": resolved,
                "unresolved": unresolved,
                "sha256": note.sha256,
            }
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_on": date.today().isoformat(),
        "note_count": len(notes),
        "notes": records,
    }
    output_dir = root / "90-system" / "indexes"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "vault-index.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    counts = Counter(str(note.metadata.get("type", "untyped") or "untyped") for note in notes)
    today = date.today().isoformat()
    lines = [
        "---",
        "id: vault-index",
        "type: system",
        "status: generated",
        f"created: {today}",
        f"updated: {today}",
        "tags:",
        "  - system/generated",
        "---",
        "",
        "# Vault Index",
        "",
        "Generated by [[90-system/automation/MOC - Automation|Automation]]. Do not edit by hand.",
        "",
        f"- Notes indexed: {len(notes)}",
        "- Types: " + ", ".join(f"{name}={count}" for name, count in sorted(counts.items())),
        "",
        "## Paths",
        "",
    ]
    lines.extend(f"- {note.path} — {note.title}" for note in notes)
    (output_dir / "Vault Index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    cache.close()
    emit({"indexed": len(notes), "json": GENERATED_JSON, "markdown": GENERATED_MARKDOWN}, compact)
    return 0


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


def schema_exempt(note: Note) -> bool:
    return note.path in ROOT_EXEMPT or note.path.startswith(EXEMPT_PREFIXES)


def check_skill_pointers(root: Path) -> list[dict[str, str]]:
    """Runtime adapters under .claude/ and .agents/ must point at a real canonical skill.

    Skill bodies live in one place only ("90-system/skills"); these stubs are the sole
    permitted duplication, so their target and identity are verified instead.
    """
    findings: list[dict[str, str]] = []
    for adapter_root in (root / ".claude" / "skills", root / ".agents" / "skills"):
        if not adapter_root.is_dir():
            continue
        for stub in sorted(adapter_root.glob("*/SKILL.md")):
            relative = stub.relative_to(root).as_posix()
            raw = stub.read_text(encoding="utf-8-sig")
            metadata, body = parse_frontmatter(raw)
            targets = re.findall(
                r"`([^`\r\n]*90-system/skills/[^`\r\n]+/SKILL\.md)`", body
            )
            if not targets:
                findings.append({"pointer": relative, "issue": "no_canonical_reference"})
                continue
            if len(targets) != 1:
                findings.append({"pointer": relative, "issue": "multiple_canonical_references"})
                continue
            target = targets[0].replace("\\", "/")
            if Path(target).is_absolute() or re.match(r"^[A-Za-z]:", target):
                findings.append(
                    {"pointer": relative, "issue": "nonportable_reference", "target": target}
                )
                continue
            canonical = (stub.parent / Path(target)).resolve()
            try:
                canonical_relative = canonical.relative_to(root.resolve()).as_posix()
            except ValueError:
                findings.append({"pointer": relative, "issue": "outside_vault", "target": target})
                continue
            if not canonical_relative.startswith("90-system/skills/"):
                findings.append(
                    {"pointer": relative, "issue": "unexpected_target", "target": canonical_relative}
                )
                continue
            if not canonical.is_file():
                findings.append(
                    {"pointer": relative, "issue": "missing_target", "target": canonical_relative}
                )
                continue
            canonical_metadata, _ = parse_frontmatter(canonical.read_text(encoding="utf-8-sig"))
            if str(metadata.get("name", "")).strip() != str(canonical_metadata.get("name", "")).strip():
                findings.append(
                    {"pointer": relative, "issue": "name_mismatch", "target": canonical_relative}
                )
            if str(metadata.get("description", "")).strip() != str(
                canonical_metadata.get("description", "")
            ).strip():
                findings.append(
                    {
                        "pointer": relative,
                        "issue": "description_mismatch",
                        "target": canonical_relative,
                    }
                )
            if stub.parent.name != str(canonical_metadata.get("name", "")).strip():
                findings.append(
                    {
                        "pointer": relative,
                        "issue": "directory_name_mismatch",
                        "target": canonical_relative,
                    }
                )
    return findings


def command_check(root: Path, compact: bool, strict: bool, quiet: bool,
                  stale_days: int, max_tags: int) -> int:
    cache = open_cache(root)
    notes = cache.notes()
    cache.close()
    by_path, by_stem = note_maps(notes)
    assets = asset_maps(root)
    adjacency, unresolved = graph(notes, assets)
    notes_by_path = {note.path: note for note in notes}
    today = date.today()

    ids: dict[str, list[str]] = defaultdict(list)
    titles: dict[str, list[str]] = defaultdict(list)
    metadata_missing: list[dict[str, Any]] = []
    placement: list[dict[str, str]] = []
    moc_coverage: list[dict[str, str]] = []
    stale: list[dict[str, Any]] = []
    tag_counter: Counter[str] = Counter()
    raw_source_integrity: list[dict[str, str]] = []
    raw_source_drafts: list[dict[str, str]] = []
    freshness: list[dict[str, Any]] = []

    for note in notes:
        note_id = str(note.metadata.get("id", "")).strip()
        if note_id:
            ids[note_id.casefold()].append(note.path)
        titles[note.title.casefold()].append(note.path)
        for tag in note_tags(note.metadata):
            tag_counter[tag] += 1

        if schema_exempt(note):
            continue

        missing = [key for key in REQUIRED_KEYS if not str(note.metadata.get(key, "")).strip()]
        if missing:
            metadata_missing.append({"path": note.path, "missing": missing})

        note_type = str(note.metadata.get("type", "")).strip()
        if note_type and note_type not in KNOWN_TYPES:
            metadata_missing.append({"path": note.path, "unknown_type": note_type})

        if note_type == "raw-source":
            status = str(note.metadata.get("status", "")).strip()
            if status != "immutable":
                raw_source_drafts.append({"path": note.path, "status": status or "missing"})
            else:
                finding = raw_source_finding(root, note)
                if finding:
                    raw_source_integrity.append(finding)

        freshness.extend(freshness_findings(note, today))

        # Placement: the schema maps each type to a home folder.
        if (
            note_type in TYPE_FOLDERS
            and note_type not in PLACEMENT_UNCONSTRAINED
            and not note.path.startswith(PLACEMENT_EXEMPT_PREFIXES)
        ):
            expected = TYPE_FOLDERS[note_type]
            if not note.path.startswith(expected + "/"):
                placement.append({"path": note.path, "type": note_type, "expected_folder": expected})

        # MOC coverage: Link Policy requires every durable note to link up to a MOC.
        if (
            note_type not in {"moc", "system", ""}
            and not note.path.startswith(MOC_EXEMPT_PREFIXES)
        ):
            resolved, _ = outbound_links(note, by_path, by_stem, assets)
            linked_types = {
                str(notes_by_path[target].metadata.get("type", "")).strip()
                for target in resolved
                if target in notes_by_path
            }
            if "moc" not in linked_types:
                moc_coverage.append({"path": note.path, "type": note_type})

        # Staleness: only active notes, measured on `updated`.
        if str(note.metadata.get("status", "")).strip() == "active":
            updated = parse_date(note.metadata.get("updated", ""))
            if updated and (today - updated).days > stale_days:
                stale.append({"path": note.path, "updated": updated.isoformat(), "days": (today - updated).days})

    duplicate_ids = [{"id": key, "paths": paths} for key, paths in sorted(ids.items()) if len(paths) > 1]
    duplicate_titles = []
    for key, paths in sorted(titles.items()):
        relevant = [
            path for path in paths
            if path not in ROOT_EXEMPT and not path.startswith("90-system/templates/")
        ]
        if len(relevant) > 1:
            duplicate_titles.append({"title": key, "paths": relevant})

    orphans = sorted(
        path for path, neighbors in adjacency.items()
        if not neighbors and path != "Home.md" and "/_template/" not in path
    )

    # Sprawl is the failure mode worth flagging. Single-use tags are normal in a young
    # vault, so they are reported by `tags` rather than warned about here.
    tag_vocabulary: dict[str, Any] = {}
    if len(tag_counter) > max_tags:
        tag_vocabulary = {
            "distinct": len(tag_counter),
            "limit": max_tags,
            "singletons": sorted(tag for tag, count in tag_counter.items() if count == 1),
        }

    typed_relation_integrity, typed_relation_inverses = typed_relation_findings(notes)
    findings: dict[str, Any] = {
        "unresolved_links": unresolved,
        "duplicate_ids": duplicate_ids,
        "duplicate_titles": duplicate_titles,
        "skill_pointers": check_skill_pointers(root),
        "raw_source_integrity": raw_source_integrity,
        "typed_relation_integrity": typed_relation_integrity,
        "metadata_issues": metadata_missing,
        "placement": placement,
        "moc_coverage": moc_coverage,
        "orphans": orphans,
        "stale": stale,
        "tag_vocabulary": tag_vocabulary,
        "raw_source_drafts": raw_source_drafts,
        "freshness": freshness,
        "typed_relation_inverses": typed_relation_inverses,
    }

    error_count = sum(len(findings[key]) for key in ERROR_KEYS)
    warning_count = sum(len(findings[key]) if isinstance(findings[key], list) else 1
                        for key in WARNING_KEYS if findings[key])
    summary = {
        "notes": len(notes),
        "errors": error_count,
        "warnings": warning_count,
        "stale_days": stale_days,
        "strict": strict,
    }
    summary.update({key: (len(findings[key]) if isinstance(findings[key], list) else int(bool(findings[key])))
                    for key in ERROR_KEYS + WARNING_KEYS})

    if quiet:
        payload: dict[str, Any] = {"summary": summary}
        if error_count:
            payload["errors"] = {key: findings[key] for key in ERROR_KEYS if findings[key]}
    else:
        payload = {
            "summary": summary,
            "errors": {key: findings[key] for key in ERROR_KEYS},
            "warnings": {key: findings[key] for key in WARNING_KEYS},
        }
    emit(payload, compact)
    if error_count:
        return 1
    return 1 if strict and warning_count else 0


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------


def best_excerpt(body: str, terms: set[str], limit: int = 320) -> str:
    paragraphs = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n\s*\n", body)]
    fence = chr(96) * 3
    paragraphs = [part for part in paragraphs if part and not part.startswith(("#", "<!--", fence))]
    if not paragraphs:
        return ""
    best = max(paragraphs, key=lambda part: sum(tokenize(part).count(term) for term in terms))
    return best if len(best) <= limit else best[: limit - 3].rstrip() + "..."


@dataclass
class QueryOptions:
    limit: int = 8
    include_templates: bool = False
    types: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    since: date | None = None
    fuzzy: bool = False
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS


def rank(cache: VaultCache, query: str, options: QueryOptions) -> list[tuple[float, Note]]:
    """BM25F over the inverted index.

    Per-field term frequencies are length-normalised and combined first, then saturated
    once -- the standard BM25F formulation, which behaves correctly when a vault mixes
    one-line stubs with long reference notes.
    """
    terms = tokenize(query)
    if not terms:
        return []
    total, (avg_title, avg_meta, avg_body) = cache.corpus_stats()
    if not total:
        return []

    expanded: list[tuple[str, float]] = []
    for term in terms:
        expanded.append((term, 1.0))
        if not cache.postings(term):
            for variant in cache.expand_prefix(term) if len(term) >= 3 else []:
                expanded.append((variant, 0.6))
            if options.fuzzy:
                for variant in cache.expand_fuzzy(term):
                    expanded.append((variant, 0.5))

    scores: dict[str, float] = defaultdict(float)
    seen_terms: set[str] = set()
    for term, weight in expanded:
        if term in seen_terms:
            continue
        seen_terms.add(term)
        rows = cache.postings(term)
        if not rows:
            continue
        idf = math.log(1 + (total - len(rows) + 0.5) / (len(rows) + 0.5))
        for row in rows:
            weighted = 0.0
            for tf, length, average, key in (
                (row["tf_title"], row["len_title"], avg_title, "title"),
                (row["tf_meta"], row["len_meta"], avg_meta, "meta"),
                (row["tf_body"], row["len_body"], avg_body, "body"),
            ):
                if not tf:
                    continue
                # Normalise each field by its own length against that field's average,
                # then combine; saturation is applied once to the combined value.
                normalizer = 1 - BM25_B + BM25_B * (length / max(average, 1.0))
                weighted += FIELD_WEIGHTS[key] * tf / max(normalizer, 1e-9)
            if weighted:
                scores[row["path"]] += weight * idf * weighted * (BM25_K1 + 1) / (weighted + BM25_K1)

    if not scores:
        return []

    # Bodies are fetched only for the documents the index actually matched.
    notes_by_path = {note.path: note for note in cache.notes(scores.keys())}
    phrase = query.casefold().strip()
    candidates: list[tuple[float, Note]] = []
    for path, score in scores.items():
        note = notes_by_path.get(path)
        if note is None:
            continue
        if not options.include_templates and note.path.startswith(RETRIEVAL_EXCLUDED):
            continue
        if options.types and str(note.metadata.get("type", "")).strip() not in options.types:
            continue
        if options.tags:
            note_tag_set = {tag.casefold() for tag in note_tags(note.metadata)}
            if not any(tag.casefold() in note_tag_set for tag in options.tags):
                continue
        if options.since:
            updated = parse_date(note.metadata.get("updated", ""))
            if updated is None or updated < options.since:
                continue
        candidates.append((score, note))

    candidates.sort(key=lambda item: (-item[0], item[1].path.casefold()))
    shortlist = candidates[:PHRASE_CANDIDATES]
    if phrase:
        hydrate_bodies(cache.root, (note for _, note in shortlist))
        for index, (score, note) in enumerate(shortlist):
            if phrase in note.title.casefold():
                candidates[index] = (score + PHRASE_TITLE_BONUS, note)
            elif phrase in note.body.casefold():
                candidates[index] = (score + PHRASE_BODY_BONUS, note)
        candidates.sort(key=lambda item: (-item[0], item[1].path.casefold()))
    winners = candidates[: options.limit]
    hydrate_bodies(cache.root, (note for _, note in winners))
    return winners


def command_query(root: Path, query: str, options: QueryOptions, compact: bool) -> int:
    cache = open_cache(root)
    ranked = rank(cache, query, options)
    cache.close()
    terms = set(tokenize(query))
    results = [
        {
            "path": note.path,
            "title": note.title,
            "type": note.metadata.get("type", ""),
            "updated": note.metadata.get("updated", ""),
            "score": round(score, 4),
            "excerpt": best_excerpt(note.body, terms, options.excerpt_chars),
            "links": note.links[:8],
        }
        for score, note in ranked
    ]
    emit({"query": query, "result_count": len(results), "results": results}, compact)
    return 0


# ---------------------------------------------------------------------------
# retrieval evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    query: str
    expected: tuple[str, ...]
    types: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    category: str = "default"


def string_tuple(value: Any) -> tuple[str, ...] | None:
    """Normalise a string or JSON string array without silently coercing other types."""
    if isinstance(value, str):
        values = (value.strip(),)
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        values = tuple(item.strip() for item in value)
    else:
        return None
    return tuple(item for item in values if item)


def load_retrieval_cases(root: Path, requested: str) -> tuple[list[RetrievalCase], list[dict[str, Any]], str | None]:
    """Load private JSONL judgments, validating all referenced notes inside the vault."""
    resolved = resolve_vault_path(root, requested)
    if resolved is None:
        return [], [{"error": "outside_vault", "requested": requested}], None
    path, relative = resolved
    if not path.is_file():
        return [], [{"error": "cases_not_found", "path": relative}], relative

    cases: list[RetrievalCase] = []
    errors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            item = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            errors.append({"line": line_number, "error": "invalid_json", "detail": exc.msg})
            continue
        if not isinstance(item, dict):
            errors.append({"line": line_number, "error": "case_must_be_object"})
            continue

        query = item.get("query")
        expected_values = string_tuple(item.get("expected"))
        types = string_tuple(item.get("type", []))
        tags = string_tuple(item.get("tags", []))
        case_id = str(item.get("id", f"line-{line_number}")).strip()
        category = str(item.get("category", "default")).strip() or "default"
        if not isinstance(query, str) or not query.strip():
            errors.append({"line": line_number, "error": "query_required"})
            continue
        if not expected_values:
            errors.append({"line": line_number, "error": "expected_required"})
            continue
        if types is None or tags is None:
            errors.append({"line": line_number, "error": "filters_must_be_strings"})
            continue
        if not case_id or case_id in seen_ids:
            errors.append({"line": line_number, "error": "case_id_missing_or_duplicate", "id": case_id})
            continue

        expected_paths: list[str] = []
        invalid_expected = False
        for expected in expected_values:
            expected_resolved = resolve_vault_path(root, expected)
            if expected_resolved is None:
                errors.append({"line": line_number, "error": "expected_outside_vault", "expected": expected})
                invalid_expected = True
                continue
            expected_path, expected_relative = expected_resolved
            if not expected_path.is_file() or expected_path.suffix.casefold() != ".md":
                errors.append({"line": line_number, "error": "expected_note_not_found", "expected": expected_relative})
                invalid_expected = True
                continue
            if expected_relative.startswith(RETRIEVAL_EXCLUDED):
                errors.append({"line": line_number, "error": "expected_note_excluded", "expected": expected_relative})
                invalid_expected = True
                continue
            expected_paths.append(expected_relative)
        if invalid_expected:
            continue

        seen_ids.add(case_id)
        cases.append(RetrievalCase(
            case_id=case_id,
            query=query.strip(),
            expected=tuple(dict.fromkeys(expected_paths)),
            types=types,
            tags=tags,
            category=category,
        ))
    if not cases and not errors:
        errors.append({"error": "no_cases", "path": relative})
    return cases, errors, relative


def retrieval_metrics(case_results: list[dict[str, Any]], k_values: tuple[int, ...]) -> dict[str, Any]:
    """Calculate macro recall@k and MRR from already-ranked case results."""
    count = len(case_results)
    recall_at_k = {
        str(k): round(sum(result["recall_at_k"][str(k)] for result in case_results) / count, 6)
        if count else 0.0
        for k in k_values
    }
    reciprocal_ranks = [
        1.0 / result["first_relevant_rank"] if result["first_relevant_rank"] else 0.0
        for result in case_results
    ]
    return {
        "case_count": count,
        "recall_at_k": recall_at_k,
        "mrr": round(sum(reciprocal_ranks) / count, 6) if count else 0.0,
    }


def evaluate_retrieval(
    cache: VaultCache,
    cases: list[RetrievalCase],
    k_values: tuple[int, ...],
    fuzzy: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Evaluate the production lexical ranker; no parallel scoring implementation."""
    case_results: list[dict[str, Any]] = []
    max_k = max(k_values)
    for case in cases:
        ranked = rank(cache, case.query, QueryOptions(
            limit=max_k,
            types=case.types,
            tags=case.tags,
            fuzzy=fuzzy,
            excerpt_chars=0,
        ))
        paths = [note.path for _, note in ranked]
        expected = set(case.expected)
        relevant_ranks = [index for index, path in enumerate(paths, start=1) if path in expected]
        recall = {
            str(k): round(sum(path in expected for path in paths[:k]) / len(expected), 6)
            for k in k_values
        }
        case_results.append({
            "id": case.case_id,
            "category": case.category,
            "expected": list(case.expected),
            "first_relevant_rank": min(relevant_ranks) if relevant_ranks else None,
            "recall_at_k": recall,
            "top_paths": paths,
        })

    overall = retrieval_metrics(case_results, k_values)
    by_category: dict[str, Any] = {}
    for category in sorted({case.category for case in cases}, key=str.casefold):
        members = [result for result in case_results if result["category"] == category]
        by_category[category] = retrieval_metrics(members, k_values)
    return case_results, overall, by_category


def command_eval_retrieval(
    root: Path,
    requested_cases: str,
    k_values: tuple[int, ...],
    fuzzy: bool,
    report_path: str | None,
    fail_below_recall: float | None,
    compact: bool,
) -> int:
    cases, errors, cases_relative = load_retrieval_cases(root, requested_cases)
    if errors:
        emit({"error": "invalid_retrieval_cases", "cases": cases_relative, "details": errors}, compact)
        return 2
    if fail_below_recall is not None and not 0.0 <= fail_below_recall <= 1.0:
        emit({"error": "invalid_recall_threshold", "value": fail_below_recall}, compact)
        return 2

    cache = open_cache(root)
    try:
        case_results, metrics, categories = evaluate_retrieval(cache, cases, k_values, fuzzy)
    finally:
        cache.close()
    payload: dict[str, Any] = {
        "schema_version": RETRIEVAL_EVAL_SCHEMA_VERSION,
        "engine": "lexical-bm25f",
        "generated_on": date.today().isoformat(),
        "cases": cases_relative,
        "k": list(k_values),
        "fuzzy": fuzzy,
        "metrics": metrics,
        "categories": categories,
        "results": case_results,
    }

    if report_path:
        report_resolved = resolve_vault_path(root, report_path)
        if report_resolved is None:
            emit({"error": "report_outside_vault", "requested": report_path}, compact)
            return 2
        destination, report_relative = report_resolved
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        payload["report"] = report_relative

    evaluated_k = max(k_values)
    passed = fail_below_recall is None or metrics["recall_at_k"][str(evaluated_k)] >= fail_below_recall
    payload["threshold"] = {
        "k": evaluated_k,
        "minimum_recall": fail_below_recall,
        "passed": passed,
    }
    emit(payload, compact)
    return 0 if passed else 1


# ---------------------------------------------------------------------------
# pack
# ---------------------------------------------------------------------------


def render_pack_output(
    query: str, chunks: list[str], included: list[str], budget_tokens: int
) -> str:
    """Render a pack including the accounting footer used by the hard size check."""
    content = "\n".join([f"# Context pack: {query}", "", *chunks]).rstrip()
    footer = (
        f"<!-- pack: {len(included)} notes, {len(content)} content chars, "
        f"~{math.ceil(len(content) / CHARS_PER_TOKEN)} content tokens, "
        f"budget {budget_tokens} -->"
    )
    return f"{content}\n\n{footer}\n"


def portable_output_chars(text: str) -> int:
    """Count characters using CRLF, the larger common cross-platform line ending."""
    return len(text) + text.count("\n")


def truncate_for_pack(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def command_pack(root: Path, query: str, options: QueryOptions, budget_tokens: int) -> int:
    """Assemble one Markdown bundle under a conservative four-characters/token ceiling."""
    cache = open_cache(root)
    ranked = rank(cache, query, options)
    cache.close()
    budget_tokens = max(budget_tokens, 1)
    budget_chars = budget_tokens * CHARS_PER_TOKEN
    chunks: list[str] = []
    included: list[str] = []

    empty_output = render_pack_output(query, chunks, included, budget_tokens)
    if portable_output_chars(empty_output) > budget_chars:
        # An extremely small budget cannot hold even the header and accounting footer.
        sys.stdout.write(f"# Context pack: {query}\n"[:budget_chars])
        return 0

    available = budget_chars - portable_output_chars(empty_output)
    per_note = available // max(len(ranked), 1)
    for score, note in ranked:
        prefix = (
            f"## {note.title}\n"
            f"`{note.path}` · type={note.metadata.get('type', '')} · score={score:.2f}\n\n"
        )
        body = note.body.strip()
        body_limit = min(len(body), per_note)
        while body_limit >= 0:
            chunk = prefix + truncate_for_pack(body, body_limit)
            candidate = render_pack_output(
                query, [*chunks, chunk], [*included, note.path], budget_tokens
            )
            overflow = portable_output_chars(candidate) - budget_chars
            if overflow <= 0:
                chunks.append(chunk)
                included.append(note.path)
                break
            if body_limit == 0:
                break
            body_limit = max(0, body_limit - overflow)
        else:  # pragma: no cover - the loop always exits through break.
            break
        if not included or included[-1] != note.path:
            break

    output = render_pack_output(query, chunks, included, budget_tokens)
    if portable_output_chars(output) > budget_chars:  # Defensive invariant.
        raise RuntimeError("pack budget invariant violated")
    sys.stdout.write(output)
    return 0


# ---------------------------------------------------------------------------
# related
# ---------------------------------------------------------------------------


def command_related(root: Path, requested: str, depth: int, compact: bool) -> int:
    cache = open_cache(root)
    notes = cache.notes()
    cache.close()
    by_path, by_stem = note_maps(notes)
    target = resolve_target(requested, by_path, by_stem)
    if not target:
        emit({"error": "note_not_found", "requested": requested}, compact)
        return 2
    adjacency, _ = graph(notes, asset_maps(root))
    notes_by_path = {note.path: note for note in notes}
    queue = deque([(target.path, 0)])
    seen = {target.path}
    results: list[dict[str, Any]] = []
    while queue:
        path, distance = queue.popleft()
        if distance > 0:
            note = notes_by_path[path]
            results.append(
                {"depth": distance, "path": path, "title": note.title, "type": note.metadata.get("type", "")}
            )
        if distance == depth:
            continue
        for neighbor in sorted(adjacency[path], key=str.casefold):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, distance + 1))
    emit({"root": target.path, "depth": depth, "neighbors": results}, compact)
    return 0


# ---------------------------------------------------------------------------
# tasks / tags / stale
# ---------------------------------------------------------------------------


def command_tasks(root: Path, prefix: str | None, state: str, compact: bool) -> int:
    cache = open_cache(root)
    notes = cache.notes()
    cache.close()
    results = []
    for note in notes:
        if note.path.startswith(RETRIEVAL_EXCLUDED):
            continue
        if prefix and not note.path.startswith(prefix):
            continue
        for task in note.tasks:
            if state == "open" and task["done"]:
                continue
            if state == "done" and not task["done"]:
                continue
            results.append(
                {"path": note.path, "line": task["line"], "done": task["done"], "text": task["text"]}
            )
    emit({"state": state, "count": len(results), "tasks": results}, compact)
    return 0


def command_tags(root: Path, min_count: int, compact: bool) -> int:
    cache = open_cache(root)
    notes = cache.notes()
    cache.close()
    counter: Counter[str] = Counter()
    for note in notes:
        counter.update(note_tags(note.metadata))
    entries = [
        {"tag": tag, "count": count}
        for tag, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if count >= min_count
    ]
    emit(
        {
            "distinct": len(counter),
            "total_uses": sum(counter.values()),
            "singletons": sorted(tag for tag, count in counter.items() if count == 1),
            "tags": entries,
        },
        compact,
    )
    return 0


def command_stale(root: Path, days: int, compact: bool) -> int:
    cache = open_cache(root)
    notes = cache.notes()
    cache.close()
    today = date.today()
    threshold = today - timedelta(days=days)
    results = []
    for note in notes:
        if schema_exempt(note):
            continue
        updated = parse_date(note.metadata.get("updated", ""))
        if updated is None:
            results.append({"path": note.path, "updated": "", "days": None, "reason": "unparsable"})
        elif updated < threshold:
            results.append(
                {
                    "path": note.path,
                    "updated": updated.isoformat(),
                    "days": (today - updated).days,
                    "status": note.metadata.get("status", ""),
                }
            )
    results.sort(key=lambda item: (item["days"] is None, -(item["days"] or 0), item["path"]))
    emit({"days": days, "count": len(results), "notes": results}, compact)
    return 0


# ---------------------------------------------------------------------------
# touch
# ---------------------------------------------------------------------------


def bump_updated(text: str, stamp: str) -> tuple[str, bool]:
    """Rewrite the `updated:` line inside frontmatter, leaving every other byte alone."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text, False
    for index in range(1, len(lines)):
        stripped = lines[index].strip()
        if stripped == "---":
            break
        if stripped.startswith("updated:"):
            ending = "\r\n" if lines[index].endswith("\r\n") else ("\n" if lines[index].endswith("\n") else "")
            replacement = f"updated: {stamp}{ending}"
            if lines[index] == replacement:
                return text, False
            lines[index] = replacement
            return "".join(lines), True
    return text, False


def is_auto_stamp_target(relative: str) -> bool:
    """Journal entries are already dated, and System/Attachments hold generated or binary
    material, so the edit hook leaves both alone."""
    if not relative.endswith(".md"):
        return False
    if relative in ROOT_EXEMPT:
        return False
    return not relative.startswith(
        ("30-resources/sources/raw/", "50-journal/", "90-system/", "99-attachments/")
    )


def command_touch(root: Path, requested: str, stamp: str | None, only_durable: bool, compact: bool) -> int:
    resolved = resolve_vault_path(root, requested)
    if resolved is None:
        emit({"error": "outside_vault", "requested": requested}, compact)
        return 2
    path, relative = resolved
    if not path.is_file():
        emit({"error": "note_not_found", "requested": requested}, compact)
        return 2
    if only_durable and not is_auto_stamp_target(relative):
        emit({"path": relative, "changed": False, "reason": "excluded_from_auto_stamp"}, compact)
        return 0
    text = path.read_text(encoding="utf-8-sig")
    updated_text, changed = bump_updated(text, stamp or date.today().isoformat())
    if changed:
        path.write_text(updated_text, encoding="utf-8", newline="")
    emit(
        {"path": relative, "changed": changed, "updated": stamp or date.today().isoformat()},
        compact,
    )
    return 0


# ---------------------------------------------------------------------------
# immutable raw sources
# ---------------------------------------------------------------------------


def command_source_seal(root: Path, requested: str, verify_only: bool, compact: bool) -> int:
    resolved = resolve_vault_path(root, requested)
    if resolved is None:
        emit({"error": "outside_vault", "requested": requested}, compact)
        return 2
    path, relative = resolved
    if not path.is_file():
        emit({"error": "source_not_found", "requested": requested}, compact)
        return 2
    if not relative.startswith(RAW_SOURCE_PREFIX):
        emit({"error": "not_in_raw_source_folder", "path": relative}, compact)
        return 2

    text = path.read_text(encoding="utf-8-sig")
    metadata, _ = parse_frontmatter(text)
    if str(metadata.get("type", "")).strip() != "raw-source":
        emit({"error": "not_a_raw_source", "path": relative}, compact)
        return 2
    payload = raw_source_payload(text)
    if payload is None:
        emit({"error": "invalid_or_missing_payload_boundary", "path": relative}, compact)
        return 2
    if not payload.strip():
        emit({"error": "empty_raw_source_payload", "path": relative}, compact)
        return 2

    digest = raw_source_digest(payload)
    recorded = str(metadata.get(RAW_SOURCE_HASH_KEY, "")).strip()
    status = str(metadata.get("status", "")).strip()
    if verify_only:
        state = "verified" if status == "immutable" and recorded == digest else (
            "modified" if recorded else "unsealed"
        )
        emit(
            {
                "path": relative,
                "state": state,
                "status": status,
                "recorded": recorded,
                "actual": digest,
            },
            compact,
        )
        return 0 if state == "verified" else 1

    if status == "immutable" or recorded:
        if status == "immutable" and recorded == digest:
            emit({"path": relative, "sealed": False, "state": "already_verified"}, compact)
            return 0
        emit(
            {
                "error": "sealed_source_cannot_be_resealed",
                "path": relative,
                "hint": "Restore the captured payload or create a new superseding raw source.",
            },
            compact,
        )
        return 1

    today = date.today().isoformat()
    sealed = set_frontmatter(
        text,
        {
            "status": "immutable",
            "updated": today,
            "sealed": today,
            RAW_SOURCE_HASH_KEY: digest,
        },
    )
    path.write_text(sealed if sealed.endswith("\n") else sealed + "\n", encoding="utf-8")
    emit({"path": relative, "sealed": True, RAW_SOURCE_HASH_KEY: digest}, compact)
    return 0


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------


def format_moment(value: date, fmt: str) -> str:
    """Render a moment.js format string, which is what Obsidian's templates use.

    Handles `[literal]` escapes and the ISO week tokens (`GGGG`, `WW`) that strftime has
    no equivalent for -- `GGGG-[W]WW` must produce `2026-W36`, not the literal token.
    Unrecognised characters pass through, as they do in moment.
    """
    iso_year, iso_week, _ = value.isocalendar()
    tokens = (
        ("YYYY", f"{value.year:04d}"), ("GGGG", f"{iso_year:04d}"),
        ("MMMM", value.strftime("%B")), ("dddd", value.strftime("%A")),
        ("MMM", value.strftime("%b")), ("ddd", value.strftime("%a")),
        ("YY", f"{value.year % 100:02d}"), ("GG", f"{iso_year % 100:02d}"),
        ("MM", f"{value.month:02d}"), ("DD", f"{value.day:02d}"),
        ("WW", f"{iso_week:02d}"), ("HH", "00"), ("mm", "00"), ("ss", "00"),
        ("M", str(value.month)), ("D", str(value.day)), ("W", str(iso_week)),
    )
    out: list[str] = []
    index = 0
    while index < len(fmt):
        if fmt[index] == "[":
            close = fmt.find("]", index)
            if close != -1:
                out.append(fmt[index + 1:close])
                index = close + 1
                continue
        for token, replacement in tokens:
            if fmt.startswith(token, index):
                out.append(replacement)
                index += len(token)
                break
        else:
            out.append(fmt[index])
            index += 1
    return "".join(out)


def render_template(text: str, title: str, today: date) -> str:
    def substitute(match: re.Match[str]) -> str:
        fmt = match.group(1)
        return format_moment(today, fmt) if fmt else today.isoformat()

    text = re.sub(r"\{\{date(?::([^}]+))?\}\}", substitute, text)
    return text.replace("{{title}}", title)


def set_frontmatter(text: str, values: dict[str, Any]) -> str:
    """Set keys inside an existing frontmatter block, preserving order and unknown keys."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return text
    def render(key: str, value: Any) -> list[str]:
        if isinstance(value, list):
            if not value:
                return [f"{key}: []"]
            return [f"{key}:"] + [f"  - {item}" for item in value]
        return [f"{key}: {value}"]

    remaining = dict(values)
    rebuilt: list[str] = [lines[0]]
    index = 1
    while index < end:
        line = lines[index]
        stripped = line.strip()
        index += 1
        key = stripped.split(":", 1)[0].strip() if ":" in stripped and not stripped.startswith("- ") else None
        if key is None or key not in remaining:
            rebuilt.append(line)
            continue
        rebuilt.extend(render(key, remaining.pop(key)))
        # Drop the replaced key's own continuation lines so old values don't survive.
        while index < end and (not lines[index].strip() or lines[index].startswith((" ", "\t"))):
            index += 1
    for key, value in remaining.items():
        rebuilt.extend(render(key, value))
    rebuilt.extend(lines[end:])
    return "\n".join(rebuilt)


def find_moc(root: Path, folder: str) -> Path | None:
    directory = root / folder
    if not directory.is_dir():
        return None
    candidates = sorted(directory.glob("MOC - *.md"))
    return candidates[0] if len(candidates) == 1 else None


def insert_into_moc(moc_path: Path, link_line: str) -> bool:
    """Append the link at the end of the list that follows the `vault:links` anchor."""
    lines = moc_path.read_text(encoding="utf-8-sig").splitlines()
    anchor_index = next((index for index, line in enumerate(lines) if ANCHOR in line), None)
    if anchor_index is None:
        return False
    if any(line.strip() == link_line for line in lines):
        return True
    insert_at = anchor_index + 1
    cursor = insert_at
    while cursor < len(lines) and (lines[cursor].startswith("- ") or not lines[cursor].strip()):
        if lines[cursor].startswith("- "):
            insert_at = cursor + 1
        cursor += 1
    lines.insert(insert_at, link_line)
    moc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def ensure_parent_moc_link(text: str, root: Path, moc_path: Path) -> str:
    """Ensure the new note has an outgoing edge to the MOC that indexes it."""
    moc_relative = moc_path.resolve().relative_to(root.resolve()).as_posix()
    target = moc_relative.removesuffix(".md")
    if target in extract_links(text):
        return text
    _, moc_body = parse_frontmatter(moc_path.read_text(encoding="utf-8-sig"))
    moc_title = extract_title(moc_body, moc_path.stem)
    wikilink = f"[[{target}|{moc_title}]]"
    blank_parent = re.compile(r"^(\s*(?:-\s*)?Parent(?: MOC)?):\s*$", re.MULTILINE)
    if blank_parent.search(text):
        return blank_parent.sub(lambda match: f"{match.group(1)}: {wikilink}", text, count=1)

    lines = text.splitlines()
    heading = next((index for index, line in enumerate(lines) if line.startswith("# ")), None)
    if heading is not None:
        lines[heading + 1:heading + 1] = ["", f"Parent: {wikilink}"]
    return "\n".join(lines)


def command_new(root: Path, note_type: str, title: str, folder: str | None, tags: list[str],
                status: str | None, link_moc: bool, dry_run: bool, compact: bool) -> int:
    if note_type not in TYPE_TEMPLATES:
        emit({"error": "unknown_type", "type": note_type, "known": sorted(TYPE_TEMPLATES)}, compact)
        return 2
    if note_type == "moc" and not folder:
        # A MOC lives inside the folder it indexes, so there is no sensible default.
        emit({"error": "folder_required", "type": "moc",
              "hint": "Pass --folder with the folder this MOC indexes."}, compact)
        return 2
    template_path = root / "90-system" / "templates" / TYPE_TEMPLATES[note_type]
    if not template_path.is_file():
        emit({"error": "template_missing", "template": TYPE_TEMPLATES[note_type]}, compact)
        return 2

    destination_folder = folder or TYPE_FOLDERS.get(note_type, "00-inbox")
    resolved_folder = resolve_vault_path(root, destination_folder)
    if resolved_folder is None:
        emit({"error": "outside_vault", "folder": destination_folder}, compact)
        return 2
    destination_directory, relative_folder = resolved_folder
    if destination_directory.exists() and not destination_directory.is_dir():
        emit({"error": "invalid_folder", "folder": destination_folder}, compact)
        return 2
    filename = re.sub(r'[<>:"/\\|?*]', "-", title).strip() or slugify(title)
    destination = destination_directory / f"{filename}.md"
    relative = (
        (Path(relative_folder) / f"{filename}.md").as_posix()
        if relative_folder != "."
        else f"{filename}.md"
    )
    if destination.exists():
        emit({"error": "already_exists", "path": relative}, compact)
        return 2

    today = date.today()
    rendered = render_template(template_path.read_text(encoding="utf-8-sig"), title, today)
    values: dict[str, Any] = {
        "id": slugify(title),
        "type": note_type,
        "created": today.isoformat(),
        "updated": today.isoformat(),
    }
    if tags:
        values["tags"] = tags
    if status:
        values["status"] = status
    rendered = set_frontmatter(rendered, values)

    moc_path = find_moc(root, relative_folder) if link_moc else None
    if moc_path:
        rendered = ensure_parent_moc_link(rendered, root, moc_path)
    link_line = f"- [[{relative.removesuffix('.md')}|{title}]]"

    if dry_run:
        emit(
            {
                "dry_run": True,
                "path": relative,
                "template": TYPE_TEMPLATES[note_type],
                "moc": moc_path.relative_to(root).as_posix() if moc_path else None,
                "content": rendered,
            },
            compact,
        )
        return 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered if rendered.endswith("\n") else rendered + "\n", encoding="utf-8")
    moc_updated = insert_into_moc(moc_path, link_line) if moc_path else False
    emit(
        {
            "path": relative,
            "type": note_type,
            "id": values["id"],
            "moc": moc_path.relative_to(root).as_posix() if moc_path else None,
            "moc_updated": moc_updated,
            "next": "Fill the template sections, then run `check`.",
        },
        compact,
    )
    return 0


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------


def command_cache(root: Path, rebuild: bool, compact: bool) -> int:
    cache = open_cache(root, rebuild=rebuild)
    payload = cache.stats()
    payload["rebuilt"] = rebuild
    payload["path"] = CACHE_RELATIVE
    cache.close()
    emit(payload, compact)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def csv_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def k_list(value: str) -> tuple[int, ...]:
    try:
        values = tuple(sorted({int(part.strip()) for part in value.split(",") if part.strip()}))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("k values must be comma-separated positive integers") from exc
    if not values or any(item <= 0 for item in values):
        raise argparse.ArgumentTypeError("k values must be comma-separated positive integers")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic vault tooling.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Shared flags, attached to every subcommand so `vault.py check --compact` works.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--compact", action="store_true", help="Minified JSON output")

    def sub(name: str, help_text: str) -> argparse.ArgumentParser:
        return subparsers.add_parser(name, help=help_text, parents=[common])

    sub("index", "Build compact JSON and Markdown inventories")

    check_parser = sub("check", "Validate metadata, links, placement, and graph health")
    check_parser.add_argument("--strict", action="store_true", help="Exit nonzero on warnings too")
    check_parser.add_argument("--quiet", action="store_true", help="Summary plus errors only")
    check_parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    check_parser.add_argument("--max-tags", type=int, default=DEFAULT_MAX_TAGS)

    query_parser = sub("query", "Ranked BM25F retrieval")
    query_parser.add_argument("terms")
    query_parser.add_argument("--limit", type=int, default=8)
    query_parser.add_argument("--type", dest="types", type=csv_list, default=[])
    query_parser.add_argument("--tag", dest="tags", type=csv_list, default=[])
    query_parser.add_argument("--since", default=None, help="Only notes updated on or after YYYY-MM-DD")
    query_parser.add_argument("--fuzzy", action="store_true", help="Trigram-assisted typo tolerance")
    query_parser.add_argument("--include-templates", action="store_true")
    query_parser.add_argument("--excerpt-chars", type=int, default=None,
                              help="Excerpt length (default 320, or 160 with --compact)")

    eval_parser = sub("eval-retrieval", "Evaluate BM25F against private JSONL judgments")
    eval_parser.add_argument("--cases", default=RETRIEVAL_CASES_RELATIVE,
                             help=f"JSONL cases inside the vault (default: {RETRIEVAL_CASES_RELATIVE})")
    eval_parser.add_argument("--k", dest="k_values", type=k_list, default=(1, 3, 5, 10),
                             help="Comma-separated recall cutoffs (default: 1,3,5,10)")
    eval_parser.add_argument("--fuzzy", action="store_true", help="Evaluate typo-tolerant ranking")
    eval_parser.add_argument("--report", default=None,
                             help=f"Write a JSON report inside the vault (suggested: {RETRIEVAL_REPORT_RELATIVE})")
    eval_parser.add_argument("--fail-below-recall", type=float, default=None,
                             help="Exit 1 when recall at the largest k is below this 0..1 value")

    pack_parser = sub("pack", "Token-budgeted Markdown context bundle")
    pack_parser.add_argument("terms")
    pack_parser.add_argument("--budget-tokens", type=int, default=4000)
    pack_parser.add_argument("--limit", type=int, default=6)
    pack_parser.add_argument("--type", dest="types", type=csv_list, default=[])
    pack_parser.add_argument("--tag", dest="tags", type=csv_list, default=[])
    pack_parser.add_argument("--fuzzy", action="store_true")

    related_parser = sub("related", "Traverse resolved wikilink neighbors")
    related_parser.add_argument("path")
    related_parser.add_argument("--depth", type=int, choices=(1, 2, 3), default=1)

    tasks_parser = sub("tasks", "Extract checkbox tasks")
    tasks_parser.add_argument("--state", choices=("open", "done", "all"), default="open")
    tasks_parser.add_argument("--path-prefix", default=None)

    tags_parser = sub("tags", "Tag inventory with counts")
    tags_parser.add_argument("--min-count", type=int, default=1)

    stale_parser = sub("stale", "Notes whose `updated` has aged out")
    stale_parser.add_argument("--days", type=int, default=DEFAULT_STALE_DAYS)

    touch_parser = sub("touch", "Stamp `updated` in a note's frontmatter")
    touch_parser.add_argument("path")
    touch_parser.add_argument("--date", dest="stamp", default=None)
    touch_parser.add_argument("--only-durable", action="store_true",
                              help="No-op for Journal, System, and Attachments paths")

    source_parser = sub("source-seal", "Seal or verify an immutable raw-source payload")
    source_parser.add_argument("path")
    source_parser.add_argument("--verify", action="store_true", help="Verify without writing")

    new_parser = sub("new", "Create a note from its template and link its MOC")
    new_parser.add_argument("--type", dest="note_type", required=True, choices=sorted(TYPE_TEMPLATES))
    new_parser.add_argument("--title", required=True)
    new_parser.add_argument("--folder", default=None)
    new_parser.add_argument("--tags", type=csv_list, default=[])
    new_parser.add_argument("--status", default=None)
    new_parser.add_argument("--no-link-moc", dest="link_moc", action="store_false")
    new_parser.add_argument("--dry-run", action="store_true")

    cache_parser = sub("cache", "Inspect or rebuild the retrieval cache")
    cache_parser.add_argument("--rebuild", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    # Notes contain em dashes, middots, and non-ASCII names; the Windows console default
    # would mangle them on the way out.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    root = vault_root()
    compact = getattr(args, "compact", False)

    if args.command == "index":
        return command_index(root, compact)
    if args.command == "check":
        return command_check(root, compact, args.strict, args.quiet, args.stale_days, args.max_tags)
    if args.command == "query":
        options = QueryOptions(
            limit=max(1, args.limit),
            include_templates=args.include_templates,
            types=tuple(args.types),
            tags=tuple(args.tags),
            since=parse_date(args.since) if args.since else None,
            fuzzy=args.fuzzy,
            # --compact shortens excerpts too: they, not the JSON whitespace, are what
            # actually costs tokens in a result set.
            excerpt_chars=max(80, args.excerpt_chars if args.excerpt_chars is not None
                              else (COMPACT_EXCERPT_CHARS if compact else DEFAULT_EXCERPT_CHARS)),
        )
        return command_query(root, args.terms, options, compact)
    if args.command == "eval-retrieval":
        return command_eval_retrieval(root, args.cases, args.k_values, args.fuzzy,
                                      args.report, args.fail_below_recall, compact)
    if args.command == "pack":
        options = QueryOptions(
            limit=max(1, args.limit),
            types=tuple(args.types),
            tags=tuple(args.tags),
            fuzzy=args.fuzzy,
        )
        return command_pack(root, args.terms, options, args.budget_tokens)
    if args.command == "related":
        return command_related(root, args.path, args.depth, compact)
    if args.command == "tasks":
        return command_tasks(root, args.path_prefix, args.state, compact)
    if args.command == "tags":
        return command_tags(root, args.min_count, compact)
    if args.command == "stale":
        return command_stale(root, args.days, compact)
    if args.command == "touch":
        return command_touch(root, args.path, args.stamp, args.only_durable, compact)
    if args.command == "source-seal":
        return command_source_seal(root, args.path, args.verify, compact)
    if args.command == "new":
        return command_new(root, args.note_type, args.title, args.folder, args.tags,
                           args.status, args.link_moc, args.dry_run, compact)
    if args.command == "cache":
        return command_cache(root, args.rebuild, compact)
    return 2


if __name__ == "__main__":
    sys.exit(main())
