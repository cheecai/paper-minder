from paper_minder.fetcher import Paper
from paper_minder.digest import format_digest


def test_format_digest_empty():
    result = format_digest([], "2024-01-15")
    assert "No relevant papers found" in result
    assert "2024-01-15" in result


def test_format_digest_with_new_papers():
    papers = [
        Paper("id1", "Hot Paper", "Abstract 1", ["A. Smith", "B. Jones"], ["q-fin.TR"],
              "2024-01-15", "2024-01-15", score=5, relevance_reason="key"),
        Paper("id2", "Ok Paper", "Abstract 2", ["C. Lee"], ["q-fin.ST"],
              "2024-01-14", "2024-01-14", score=3, relevance_reason="maybe"),
    ]
    result = format_digest(papers, "2024-01-15", new_ids={"id1"})

    assert "Highly Relevant" in result
    assert "Worth Noting" in result
    assert "Hot Paper" in result
    assert "Ok Paper" in result
    assert "New This Run" in result
    assert "🆕 New: 1" in result


def test_format_digest_no_new_papers():
    papers = [
        Paper("id1", "Old Paper", "Abs", ["A"], ["cat"],
              "2024-01-01", "2024-01-01", score=4, relevance_reason="old"),
    ]
    result = format_digest(papers, new_ids=set())
    assert "New This Run" not in result


def test_format_digest_all_tiers():
    papers = [
        Paper("id1", "Five", "abs", ["A"], ["cat"], "2024-01-01", "2024-01-01", score=5),
        Paper("id2", "Four", "abs", ["B"], ["cat"], "2024-01-01", "2024-01-01", score=4),
        Paper("id3", "Three", "abs", ["C"], ["cat"], "2024-01-01", "2024-01-01", score=3),
    ]
    result = format_digest(papers)
    idx5 = result.index("Five")
    idx4 = result.index("Four")
    idx3 = result.index("Three")
    assert idx5 < idx4 < idx3


def test_format_digest_authors_truncation():
    paper = Paper("id1", "Title", "abstract",
                  authors=["A", "B", "C", "D", "E"],
                  categories=["q-fin.TR"],
                  published="2024-01-01", updated="2024-01-01", score=4)
    result = format_digest([paper])
    assert "A, B, C et al." in result
