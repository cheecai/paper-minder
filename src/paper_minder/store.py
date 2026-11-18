"""SQLite storage layer for paper-minder."""

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

from paper_minder.fetcher import Paper

DEFAULT_DB = Path.home() / ".paper-minder" / "papers.db"
PAPERS_DIR = Path.home() / "hermes" / "hft" / "papers"

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id TEXT UNIQUE NOT NULL,
    title TEXT,
    abstract TEXT,
    authors TEXT,           -- JSON array
    categories TEXT,         -- JSON array
    published TEXT,          -- YYYY-MM-DD
    updated TEXT,            -- YYYY-MM-DD
    score INTEGER DEFAULT 0,
    relevance_reason TEXT DEFAULT '',
    pdf_url TEXT DEFAULT '',
    local_path TEXT DEFAULT '',
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_arxiv_id ON papers(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_score ON papers(score);
CREATE INDEX IF NOT EXISTS idx_published ON papers(published);

-- Every arXiv id the monitor has ever seen, with the LOCAL date it was
-- first sighted. The digest's "new this run" set is derived from this
-- table rather than from a live DB snapshot, so a same-day retry (needed
-- when arXiv rate-limits a category) still reports the day's arrivals
-- instead of zeroing them out.
CREATE TABLE IF NOT EXISTS arrivals (
    arxiv_id TEXT PRIMARY KEY,
    first_seen_date TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_arrivals_date ON arrivals(first_seen_date);

-- Key/value store for monitor bookkeeping (migration cutover markers, etc).
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns that may be missing from older schemas."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(papers)")}
    migrations = [
        ("pdf_url", "TEXT DEFAULT ''"),
        ("local_path", "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in migrations:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE papers ADD COLUMN {col_name} {col_def}")
    conn.commit()


def get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open the database, creating it and the schema if needed.

    Pass ":memory:" for an ephemeral database (tests).
    """
    if db_path is not None and str(db_path) == ":memory:":
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        conn.commit()
        _migrate(conn)
        return conn

    path = db_path or DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate(conn)
    return conn


def upsert_paper(
    conn: sqlite3.Connection, paper: Paper, first_seen_date: Optional[str] = None
) -> bool:
    """Insert or update a paper. Returns True if new, False if updated.

    New papers are also written to the arrivals log with `first_seen_date`
    (default: today, local). Recording the arrival at INSERT time is what
    makes the digest's "new" count survive a same-day retry: a retry sees
    the paper already in the papers table, but its arrival row still
    carries the date it was genuinely first sighted.
    """
    existing = conn.execute(
        "SELECT id FROM papers WHERE arxiv_id = ?", (paper.arxiv_id,)
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE papers
               SET title=?, abstract=?, authors=?, categories=?,
                   published=?, updated=?, score=?, relevance_reason=?,
                   pdf_url=?,
                   local_path=COALESCE(NULLIF(?, ''), local_path),
                   fetched_at=datetime('now')
               WHERE arxiv_id=?""",
            (
                paper.title,
                paper.abstract,
                json.dumps(paper.authors),
                json.dumps(paper.categories),
                paper.published,
                paper.updated,
                paper.score,
                paper.relevance_reason,
                paper.pdf_url,
                paper.local_path,
                paper.arxiv_id,
            ),
        )
        conn.commit()
        return False
    else:
        conn.execute(
            """INSERT INTO papers
               (arxiv_id, title, abstract, authors, categories,
                published, updated, score, relevance_reason, pdf_url, local_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                paper.arxiv_id,
                paper.title,
                paper.abstract,
                json.dumps(paper.authors),
                json.dumps(paper.categories),
                paper.published,
                paper.updated,
                paper.score,
                paper.relevance_reason,
                paper.pdf_url,
                paper.local_path,
            ),
        )
        record_arrivals(
            conn, [paper.arxiv_id], first_seen_date or date.today().isoformat()
        )
        conn.commit()
        return True


def mark_downloaded(
    conn: sqlite3.Connection, arxiv_id: str, local_path: str, pdf_url: str
) -> None:
    """Record that a paper's PDF has been downloaded."""
    conn.execute(
        "UPDATE papers SET local_path=?, pdf_url=? WHERE arxiv_id=?",
        (local_path, pdf_url, arxiv_id),
    )
    conn.commit()


def record_arrivals(
    conn: sqlite3.Connection, arxiv_ids: list[str], first_seen_date: str
) -> int:
    """Record arxiv ids sighted for the first time.

    Idempotent: an id already in the table keeps its original date, so a
    same-day re-run does not re-date it and does not lose it from the
    "new this run" set. Returns the number of newly recorded ids.
    """
    new_count = 0
    for arxiv_id in arxiv_ids:
        cur = conn.execute(
            "INSERT OR IGNORE INTO arrivals (arxiv_id, first_seen_date) "
            "VALUES (?, ?)",
            (arxiv_id, first_seen_date),
        )
        if cur.rowcount:
            new_count += 1
    conn.commit()
    return new_count


def get_arrivals(conn: sqlite3.Connection, first_seen_date: str) -> set[str]:
    """Arxiv ids first sighted on the given local date."""
    rows = conn.execute(
        "SELECT arxiv_id FROM arrivals WHERE first_seen_date = ?",
        (first_seen_date,),
    ).fetchall()
    return {r[0] for r in rows}


def get_meta(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    """Read a value from the meta key/value table."""
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Write a value to the meta key/value table."""
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()


def seed_arrivals(
    conn: sqlite3.Connection,
    baseline_id: int,
    legacy_date: str,
    today: str,
) -> tuple[int, int]:
    """Backfill the arrivals log for a database that predates it.

    Papers with `id <= baseline_id` existed before the monitor tracked
    arrivals, so their true arrival date is unknowable — they get
    `legacy_date` and are never reported as new. Papers with a higher id
    were inserted after the baseline and are dated `today`.

    Returns (legacy_count, recent_count).
    """
    legacy = conn.execute(
        "SELECT arxiv_id FROM papers WHERE id <= ? AND arxiv_id NOT IN "
        "(SELECT arxiv_id FROM arrivals)",
        (baseline_id,),
    ).fetchall()
    recent = conn.execute(
        "SELECT arxiv_id FROM papers WHERE id > ? AND arxiv_id NOT IN "
        "(SELECT arxiv_id FROM arrivals)",
        (baseline_id,),
    ).fetchall()
    conn.executemany(
        "INSERT OR IGNORE INTO arrivals (arxiv_id, first_seen_date) VALUES (?, ?)",
        [(r[0], legacy_date) for r in legacy],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO arrivals (arxiv_id, first_seen_date) VALUES (?, ?)",
        [(r[0], today) for r in recent],
    )
    conn.commit()
    return len(legacy), len(recent)


def get_papers_needing_download(
    conn: sqlite3.Connection,
    min_score: int = 4,
    days: int = 7,
) -> list[dict]:
    """Get recent high-score papers whose PDF hasn't been downloaded yet."""
    rows = conn.execute(
        """SELECT * FROM papers
           WHERE score >= ?
             AND published >= date('now', ?)
             AND (local_path IS NULL OR local_path = '')
           ORDER BY score DESC, published DESC""",
        (min_score, f"-{days} days"),
    ).fetchall()
    return [dict(r) for r in rows]


def get_recent_papers(
    conn: sqlite3.Connection,
    min_score: int = 4,
    days: int = 7,
) -> list[dict]:
    """Get recent papers above a score threshold."""
    rows = conn.execute(
        """SELECT * FROM papers
           WHERE score >= ? AND published >= date('now', ?)
           ORDER BY score DESC, published DESC""",
        (min_score, f"-{days} days"),
    ).fetchall()
    return [dict(r) for r in rows]
