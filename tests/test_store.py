import json
import sqlite3

from paper_minder.fetcher import Paper
from paper_minder.store import get_db, upsert_paper


def _make_conn():
    """Create an in-memory database with the paper table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arxiv_id TEXT UNIQUE NOT NULL,
            title TEXT,
            abstract TEXT,
            authors TEXT,
            categories TEXT,
            published TEXT,
            updated TEXT,
            score INTEGER DEFAULT 0,
            relevance_reason TEXT DEFAULT '',
            fetched_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def test_upsert_new_paper():
    conn = _make_conn()
    paper = Paper(
        arxiv_id="2401.00001",
        title="Test Paper",
        abstract="An abstract.",
        authors=["Alice", "Bob"],
        categories=["q-fin.TR"],
        published="2024-01-15",
        updated="2024-01-15",
        score=4,
        relevance_reason="Highly relevant to microstructure",
    )
    is_new = upsert_paper(conn, paper)
    assert is_new is True

    row = conn.execute(
        "SELECT * FROM papers WHERE arxiv_id='2401.00001'"
    ).fetchone()
    assert row["title"] == "Test Paper"
    assert row["score"] == 4
    assert row["relevance_reason"] == "Highly relevant to microstructure"
    authors = json.loads(row["authors"])
    assert authors == ["Alice", "Bob"]


def test_upsert_existing_paper_updates():
    conn = _make_conn()
    paper = Paper(
        arxiv_id="2401.00001",
        title="Old Title",
        abstract="Old abstract.",
        authors=["A"],
        categories=["q-fin.TR"],
        published="2024-01-15",
        updated="2024-01-15",
        score=3,
        relevance_reason="ok",
    )
    upsert_paper(conn, paper)

    # Same arxiv_id, different score
    paper.score = 5
    paper.relevance_reason = "much better"
    is_new = upsert_paper(conn, paper)
    assert is_new is False

    row = conn.execute(
        "SELECT * FROM papers WHERE arxiv_id='2401.00001'"
    ).fetchone()
    assert row["score"] == 5
    assert row["relevance_reason"] == "much better"


def test_upsert_multiple_papers():
    conn = _make_conn()
    p1 = Paper(
        arxiv_id="id1", title="One", abstract="a",
        authors=[], categories=[], published="2024-01-01", updated="2024-01-01",
        score=5,
    )
    p2 = Paper(
        arxiv_id="id2", title="Two", abstract="b",
        authors=[], categories=[], published="2024-01-02", updated="2024-01-02",
        score=3,
    )
    assert upsert_paper(conn, p1) is True
    assert upsert_paper(conn, p2) is True
    assert upsert_paper(conn, p1) is False  # duplicate

    count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    assert count == 2
