"""SQLite storage layer for paper-minder."""

import json
import sqlite3
from pathlib import Path
from typing import Optional

from paper_minder.fetcher import Paper

DEFAULT_DB = Path.home() / ".paper-minder" / "papers.db"

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
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_arxiv_id ON papers(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_score ON papers(score);
CREATE INDEX IF NOT EXISTS idx_published ON papers(published);
"""


def get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open the database, creating it and the schema if needed."""
    path = db_path or DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
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
                paper.arxiv_id,
            ),
        )
        conn.commit()
        return False
    else:
        conn.execute(
            """INSERT INTO papers
               (arxiv_id, title, abstract, authors, categories,
                published, updated, score, relevance_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            ),
        )
        conn.commit()
        return True


def get_recent_papers(
    conn: sqlite3.Connection,
    min_score: int = 3,
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
