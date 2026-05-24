"""LLM-based relevance scoring for arXiv papers.

Model configuration:
  1. PAPER_MINDER_MODEL env var (e.g. "minimax/MiniMax-M2.7")
  2. Falls back to DEFAULT_MODEL if not set
  3. Set MINIMAX_API_KEY (or provider-specific key) in environment

Provider examples:
  - MiniMax:   minimax/MiniMax-M2.7
  - DeepSeek:  deepseek/deepseek-chat
  - OpenAI:    gpt-4o
  - Anthropic: claude-sonnet-4-20250514
"""

import os
import litellm

from paper_minder.fetcher import Paper

DEFAULT_MODEL = "minimax/MiniMax-M2.7"


def get_model() -> str:
    """Return the configured scoring model."""
    return os.environ.get("PAPER_MINDER_MODEL", DEFAULT_MODEL)


SCORING_PROMPT = """You are a research assistant specialized in quantitative finance, HFT, and market microstructure.

Score this paper's relevance to HFT and microstructure research on a scale of 1-5:

1 = Not relevant (macro econ, corporate finance, behavioral, etc.)
2 = Marginally relevant (vaguely about markets but wrong scope or timescale)
3 = Possibly relevant (covers liquidity, volatility, short-term prediction at daily+ scale)
4 = Likely relevant (order flow, LOB, market impact, intraday dynamics, execution algorithms)
5 = Directly applicable (microstructure, tick data, HFT signals, limit order book modeling)

Also rate 4-5 for: real-time prediction, order book imbalance, trade classification,
bid-ask spread dynamics, market making, latency arbitrage, queue position, price impact models.

Title: {title}
Abstract: {abstract}

Respond with ONLY two lines:
SCORE: <1-5>
REASON: <one sentence why this is relevant or not>"""


def score_paper(paper: Paper, model: str | None = None) -> Paper:
    """Score a paper using LLM. Modifies paper in-place and returns it.

    Args:
        paper: Paper to score.
        model: LLM model string. Falls back to get_model() if None.
    """
    model = model or get_model()
    prompt = SCORING_PROMPT.format(
        title=paper.title,
        abstract=paper.abstract[:2000],
    )

    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.0,
        )
        text = response.choices[0].message.content.strip()

        score = 1
        reason = ""
        for line in text.split("\n"):
            if line.upper().startswith("SCORE:"):
                try:
                    score = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.upper().startswith("REASON:"):
                reason = line.split(":", 1)[1].strip()

        paper.score = max(1, min(5, score))
        paper.relevance_reason = reason
    except Exception as e:
        print(f"[WARN] LLM scoring failed for {paper.arxiv_id}: {e}")
        paper.score = 0
        paper.relevance_reason = "scoring error"

    return paper


def score_papers(
    papers: list[Paper],
    model: str | None = None,
) -> list[Paper]:
    """Score a list of papers in-place. Returns the same list."""
    for paper in papers:
        score_paper(paper, model=model)
    return papers
