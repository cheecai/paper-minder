"""Tests for what the digest counts as a "new" paper.

Two long-standing bugs made the daily "🆕 New" count meaningless:

1. Papers scoring below the storage threshold were never persisted, so every
   run re-scored the same hundreds of them (wasting API calls).
2. "New" was derived from the set of papers scored this run, which after the
   fix above included every previously-unscored paper ever seen — not just
   genuinely new arrivals.

`new_ids` must be: papers in the digest whose arxiv_id was absent from the
DB before the run started.
"""

from paper_minder.digest import format_digest
from paper_minder.fetcher import Paper


def _paper(pid, score=4):
    return Paper(
        pid, f"Title {pid}", "Abstract", ["A"], ["q-fin.TR"],
        "2024-01-15", "2024-01-15", score=score,
        relevance_reason="reason",
    )


def test_digest_counts_only_never_seen_papers_as_new():
    scored = [_paper("brand_new"), _paper("already_known")]
    # "already_known" was in the DB before the run; "brand_new" was not.
    known_ids = {"already_known"}
    new_ids = {p.arxiv_id for p in scored if p.arxiv_id not in known_ids}

    digest = format_digest(scored, new_ids=new_ids)
    assert "🆕 New: 1" in digest
    assert "New This Run" in digest
    assert "Title brand_new" in digest


def test_digest_reports_zero_new_when_all_are_known():
    scored = [_paper("a"), _paper("b")]
    known_ids = {"a", "b"}
    new_ids = {p.arxiv_id for p in scored if p.arxiv_id not in known_ids}

    digest = format_digest(scored, new_ids=new_ids)
    assert "🆕 New: 0" in digest
    assert "New This Run" not in digest


def test_rescored_low_score_paper_is_not_new():
    """A paper previously scored below threshold is cached, not new."""
    previously_seen = _paper("old_low_score", score=3)
    brand_new = _paper("fresh", score=5)
    known_ids = {"old_low_score"}

    new_ids = {p.arxiv_id for p in [previously_seen, brand_new]
               if p.arxiv_id not in known_ids}
    digest = format_digest([previously_seen, brand_new], new_ids=new_ids)
    assert "🆕 New: 1" in digest
