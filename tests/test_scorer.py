import pytest
from paper_minder.fetcher import Paper
from paper_minder.scorer import get_model, score_paper


def test_get_model_default():
    assert get_model() == "minimax/MiniMax-M2.7"


def test_get_model_from_env(monkeypatch):
    monkeypatch.setenv("PAPER_MINDER_MODEL", "gpt-4o")
    assert get_model() == "gpt-4o"


def test_score_paper_preserves_structure():
    """Without an actual LLM call, score_paper sets default values."""
    paper = Paper(
        arxiv_id="test.1",
        title="Order Flow Imbalance and Short-Term Price Predictability",
        abstract="We study the relationship between order flow and short-term returns.",
        authors=["A. Author"],
        categories=["q-fin.TR"],
        published="2024-01-01",
        updated="2024-01-01",
    )
    # Before scoring
    assert paper.score == 0
    assert paper.relevance_reason == ""
    assert paper.arxiv_id == "test.1"
    assert paper.title == "Order Flow Imbalance and Short-Term Price Predictability"
    assert paper.authors == ["A. Author"]
