from paper_minder.fetcher import Paper
from paper_minder.digest import format_digest


def test_format_digest_empty():
    result = format_digest([], "2024-01-15")
    assert "No relevant papers found" in result
    assert "2024-01-15" in result


def test_format_digest_with_papers():
    papers = [
        Paper(
            arxiv_id="id1",
            title="Hot Paper on LOB Dynamics",
            abstract="We model limit order book dynamics at tick level.",
            authors=["A. Smith", "B. Jones"],
            categories=["q-fin.TR"],
            published="2024-01-15",
            updated="2024-01-15",
            score=5,
            relevance_reason="Directly models LOB at tick level",
        ),
        Paper(
            arxiv_id="id2",
            title="Okay Paper on Volatility",
            abstract="We forecast volatility at daily frequency.",
            authors=["C. Lee"],
            categories=["q-fin.ST"],
            published="2024-01-14",
            updated="2024-01-14",
            score=3,
            relevance_reason="Volatility forecasting, daily scale only",
        ),
        Paper(
            arxiv_id="id3",
            title="Relevant Paper on Market Impact",
            abstract="We study market impact of large orders.",
            authors=["D. Wang"],
            categories=["q-fin.TR"],
            published="2024-01-15",
            updated="2024-01-15",
            score=4,
            relevance_reason="Market impact modeling with intraday data",
        ),
    ]
    result = format_digest(papers, "2024-01-15")

    assert "Highly Relevant" in result
    assert "Relevant" in result
    assert "Worth Noting" in result
    assert "Hot Paper" in result
    assert "Okay Paper" in result
    assert "LOBs" in result or "limit order book" in result.lower()
    assert "[Hot Paper on LOB Dynamics](https://arxiv.org/abs/id1)" in result
    assert "A. Smith, B. Jones" in result


def test_format_digest_all_tiers():
    """Verify all three tiers appear correctly."""
    papers = [
        Paper("id1", "Five", "abs", ["A"], ["cat"], "2024-01-01", "2024-01-01", score=5),
        Paper("id2", "Four", "abs", ["B"], ["cat"], "2024-01-01", "2024-01-01", score=4),
        Paper("id3", "Three", "abs", ["C"], ["cat"], "2024-01-01", "2024-01-01", score=3),
    ]
    result = format_digest(papers)
    # Tier order matters: 5 before 4 before 3
    idx5 = result.index("Five")
    idx4 = result.index("Four")
    idx3 = result.index("Three")
    assert idx5 < idx4 < idx3


def test_format_digest_authors_truncation():
    """Long author lists should be truncated."""
    paper = Paper(
        "id1", "Title", "abstract",
        authors=["A", "B", "C", "D", "E"],
        categories=["q-fin.TR"],
        published="2024-01-01", updated="2024-01-01",
        score=4,
    )
    result = format_digest([paper])
    assert "A, B, C et al." in result
    assert "D" not in result.split("et al.")[0]
