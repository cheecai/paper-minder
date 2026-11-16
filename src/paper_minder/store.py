"""SQLite storage layer for paper-minder."""

import json
import sqlite3
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
    """Open the database, creating it and the schema if needed."""
    path = db_path or DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate(conn)
    return conn


def upsert_paper(conn: sqlite3.Connection, paper: Paper) -> bool:
    """Insert or update a paper. Returns True if new, False if updated."""
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
