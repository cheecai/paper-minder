# Paper Minder 📚

Daily arXiv paper monitor for HFT and market microstructure research.

## How It Works

```
arXiv API → Fetcher (feedparser) → LLM Scorer → SQLite Store → Markdown Digest
```

1. **Fetch** — Queries arXiv API for new papers in q-fin categories (TR, ST, CP, MF, PM)
2. **Score** — Each paper is scored 1–5 by LLM for HFT/microstructure relevance
3. **Store** — Papers stored in SQLite with dedup by arXiv ID
4. **Digest** — Markdown digest of papers scored ≥3, with relevance reasons

## Quick Start

```bash
pip install -e .

# Full run
python -m paper_minder

# Dry run (no DB write, see what you'd get)
python -m paper_minder --dry-run

# Only fetch (no scoring)
python -m paper_minder --no-score --max-results 5
```

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `PAPER_MINDER_MODEL` | `openai/MiniMax-M2.7` | LLM model for scoring |
| `PAPER_MINDER_BASE_URL` | `https://api.minimaxi.com/v1` | API endpoint |
| `MINIMAX_API_KEY` | (required) | MiniMax API key |
| (any litellm key) | — | For other providers (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.) |

Model is configurable via `--model` flag or `PAPER_MINDER_MODEL` env var:

```bash
# Use DeepSeek
python -m paper_minder --model deepseek/deepseek-chat

# Use OpenAI
PAPER_MINDER_MODEL=gpt-4o python -m paper_minder
```

## Scoring Criteria

| Score | Label | What It Catches |
|-------|-------|----------------|
| 5 | 🔥 Highly Relevant | Microstructure, tick data, LOB dynamics, HFT signals |
| 4 | 📌 Relevant | Order flow, market impact, intraday dynamics, execution |
| 3 | ⚡ Worth Noting | Liquidity, volatility forecasting, short-term prediction |
| 1–2 | ❌ Filtered Out | Macro, corporate finance, behavioral, daily+ scale |

## Options

```
--dry-run         Fetch + score, skip DB write
--min-score N     Minimum score for digest (default: 3)
--categories ...  Specific arXiv categories (default: all 5 q-fin)
--max-results N   Max papers per category (default: 100)
--model MODEL     LLM model string
--no-score        Skip LLM scoring (fetch only)
```

## Data

SQLite database at `~/.paper-minder/papers.db`.

## Schedule

Runs daily at 00:00 UTC (08:00 HKT) via cronjob — arXiv publishes new papers at midnight UTC.
