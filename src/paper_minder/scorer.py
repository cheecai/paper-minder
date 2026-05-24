"""LLM-based relevance scoring for arXiv papers.

Uses direct HTTP calls — no litellm dependency for the default MiniMax path.
Supports multiple backends via model prefix.

Model configuration via environment variables:
  PAPER_MINDER_MODEL     — model string (default: minimax/MiniMax-M2.7)
  PAPER_MINDER_API_KEY   — API key (falls back to MINIMAX_API_KEY)
  PAPER_MINDER_BASE_URL  — custom endpoint URL

Supported backends:
  - minimax/*   — MiniMax via api.minimaxi.com/v1/text/chatcompletion_v2 (default)
  - openai/*    — OpenAI-compatible endpoints
  - deepseek/*  — DeepSeek API
"""

import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from paper_minder.fetcher import Paper

DEFAULT_MODEL = "minimax/MiniMax-M2.7"
MINIMAX_ENDPOINT = "https://api.minimaxi.com/v1/text/chatcompletion_v2"
_last_url = ""  # debug: last attempted URL


def get_model() -> str:
    return os.environ.get("PAPER_MINDER_MODEL", DEFAULT_MODEL)


def _get_api_key(model: str = "") -> str:
    """Get API key, preferring provider-specific env vars based on model prefix."""
    key = os.environ.get("PAPER_MINDER_API_KEY", "")
    if key:
        return key
    if model.startswith("deepseek/"):
        return os.environ.get("DEEPSEEK_API_KEY", "")
    if model.startswith("openai/"):
        return os.environ.get("OPENAI_API_KEY", "")
    return os.environ.get("MINIMAX_API_KEY", "")


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


def _call_minimax(prompt: str, model: str, api_key: str) -> str:
    """Call MiniMax chat completion API directly."""
    global _last_url
    _last_url = MINIMAX_ENDPOINT
    payload = json.dumps({
        "model": model.split("/", 1)[1] if "/" in model else "MiniMax-M2.7",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 100,
        "temperature": 0.0,
    }).encode()
    req = Request(
        MINIMAX_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]


def _call_openai_compat(prompt: str, model: str, api_key: str, base_url: str) -> str:
    """Call an OpenAI-compatible endpoint."""
    global _last_url
    endpoint = base_url.rstrip("/") + "/chat/completions"
    _last_url = endpoint
    payload = json.dumps({
        "model": model.split("/", 1)[1] if "/" in model else model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 100,
        "temperature": 0.0,
    }).encode()
    req = Request(
        endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]


def score_paper(paper: Paper, model: str | None = None) -> Paper:
    """Score a paper using LLM. Modifies paper in-place and returns it."""
    model = model or get_model()
    api_key = _get_api_key(model)
    base_url = os.environ.get("PAPER_MINDER_BASE_URL", "")
    prompt = SCORING_PROMPT.format(title=paper.title, abstract=paper.abstract[:2000])

    try:
        if model.startswith("minimax/"):
            text = _call_minimax(prompt, model, api_key)
        elif base_url:
            text = _call_openai_compat(prompt, model, api_key, base_url)
        elif model.startswith("openai/"):
            text = _call_openai_compat(prompt, model, api_key, "https://api.openai.com/v1")
        elif model.startswith("deepseek/"):
            text = _call_openai_compat(prompt, model, api_key, "https://api.deepseek.com/v1")
        else:
            # Generic OpenAI-compatible
            text = _call_openai_compat(prompt, model, api_key, base_url or "https://api.openai.com/v1")

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
        print(f"[DEBUG] URL: {_last_url}", file=sys.stderr)
        paper.score = 0
        paper.relevance_reason = "scoring error"

    return paper


def score_papers(papers: list[Paper], model: str | None = None) -> list[Paper]:
    for paper in papers:
        score_paper(paper, model=model)
    return papers
