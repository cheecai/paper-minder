"""Tests for the persistent arrivals log.

The digest's "new" count used to be derived from a live DB snapshot of ids
seen before the run. That breaks on same-day retries: the first attempt
already inserted the new papers, so every retry reported 0 new papers and
dropped the "🆕 New This Run" section from the digest.

The arrivals log is persistent and written at INSERT time, so a retry still
sees today's arrivals.
"""

import pytest

from paper_minder.fetcher import Paper
from paper_minder.store import (
    get_arrivals,
    get_db,
    get_meta,
    record_arrivals,
    seed_arrivals,
    set_meta,
    upsert_paper,
)


def _paper(pid, score=4):
    return Paper(
        pid, f"Title {pid}", "Abstract", ["A"], ["q-fin.TR"],
        "2024-01-15", "2024-01-15", score=score,
        relevance_reason="reason",
    )


def test_record_arrivals_is_idempotent():
    conn = get_db(":memory:")
    assert record_arrivals(conn, ["a", "b"], "2024-01-15") == 2
    # A same-day retry re-reports the same ids — no duplicates, and the
    # original date is preserved.
    assert record_arrivals(conn, ["a", "b"], "2024-01-15") == 0
    assert get_arrivals(conn, "2024-01-15") == {"a", "b"}


def test_arrival_date_survives_a_later_run():
    conn = get_db(":memory:")
    record_arrivals(conn, ["a"], "2024-01-15")
    # A next-day run sees the same id again — it keeps its original date,
    # so it does not show up as new tomorrow.
    record_arrivals(conn, ["a"], "2024-01-16")
    assert get_arrivals(conn, "2024-01-15") == {"a"}
    assert get_arrivals(conn, "2024-01-16") == set()


def test_upsert_records_arrival_date_at_insert_time():
    conn = get_db(":memory:")
    upsert_paper(conn, _paper("fresh"), first_seen_date="2024-01-15")
    assert get_arrivals(conn, "2024-01-15") == {"fresh"}


def test_upsert_update_does_not_re_date_arrival():
    conn = get_db(":memory:")
    upsert_paper(conn, _paper("fresh"), first_seen_date="2024-01-15")
    # Re-storing on a later day must not move the arrival date.
    upsert_paper(conn, _paper("fresh"), first_seen_date="2024-01-16")
    assert get_arrivals(conn, "2024-01-15") == {"fresh"}
    assert get_arrivals(conn, "2024-01-16") == set()


def test_seed_arrivals_marks_old_papers_legacy():
    conn = get_db(":memory:")
    upsert_paper(conn, _paper("old"))
    conn.execute("DELETE FROM arrivals")
    conn.commit()
    old_id = conn.execute("SELECT MAX(id) FROM papers").fetchone()[0]

    # The baseline is the newest id that predates the log: everything at
    # or below it is legacy, everything above it arrived today.
    legacy, recent = seed_arrivals(conn, old_id, "unknown", "2024-01-15")
    assert legacy == 1
    assert recent == 0
    # Legacy papers are never reported as new.
    assert get_arrivals(conn, "2024-01-15") == set()


def test_seed_arrivals_dates_papers_above_cutover_as_today():
    conn = get_db(":memory:")
    upsert_paper(conn, _paper("old"))
    old_id = conn.execute("SELECT MAX(id) FROM papers").fetchone()[0]
    upsert_paper(conn, _paper("today"))
    conn.execute("DELETE FROM arrivals")
    conn.commit()

    legacy, recent = seed_arrivals(conn, old_id, "unknown", "2024-01-15")
    assert legacy == 1
    assert recent == 1
    assert get_arrivals(conn, "2024-01-15") == {"today"}


def test_meta_roundtrip():
    conn = get_db(":memory:")
    assert get_meta(conn, "missing") is None
    assert get_meta(conn, "missing", "fallback") == "fallback"
    set_meta(conn, "key", "value")
    assert get_meta(conn, "key") == "value"
    set_meta(conn, "key", "other")
    assert get_meta(conn, "key") == "other"


def test_retry_after_partial_fetch_still_reports_new_papers():
    """The end-to-end scenario that broke: a retry must not lose 'new'."""
    conn = get_db(":memory:")
    # First attempt (partial fetch) inserts and logs the new paper.
    upsert_paper(conn, _paper("new_arrival"), first_seen_date="2024-01-15")
    # Second attempt sees it already in the DB — but the arrivals log
    # still knows it arrived today.
    assert get_arrivals(conn, "2024-01-15") == {"new_arrival"}
