"""arXiv API fetcher for paper-minder."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import feedparser
import requests

ARXIV_API = "https://export.arxiv.org/api/query"

# arXiv occasionally stalls on a cold connection; a single timeout used to
# silently drop an entire category from the run. Retry with backoff.
FETCH_TIMEOUT = 60
FETCH_RETRIES = 3
FETCH_BACKOFF = 5.0

CATEGORIES = [
    "q-fin.TR",   # Trading and Market Microstructure
    "q-fin.ST",   # Statistical Finance
    "q-fin.CP",   # Computational Finance
    "q-fin.MF",   # Mathematical Finance
    "q-fin.PM",   # Portfolio Management
]


@dataclass
class Paper:
    arxiv_id: str
    title: str
    abstract: str
    authors: list[str]
    categories: list[str]
    published: str   # YYYY-MM-DD
    updated: str     # YYYY-MM-DD
    score: int = 0
    relevance_reason: str = ""
    local_path: str = ""   # path to downloaded PDF, if any

    @property
    def pdf_url(self) -> str:
        return f"https://arxiv.org/pdf/{self.arxiv_id}.pdf"

    @property
    def abs_url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"


def _extract_arxiv_id(entry) -> str:
    """Extract clean arXiv ID from the entry id URL."""
    id_url = entry.id
    base = id_url.split("/abs/")[-1]
    if "v" in base:
        base = base[: base.rindex("v")]
    return base


def _parse_entry(entry) -> Paper:
    """Parse a single feedparser entry into a Paper."""
    def _fmt_authors():
        try:
            return [a.name for a in entry.authors]
        except (AttributeError, TypeError):
            return []

    def _fmt_categories():
        try:
            return [t.term for t in entry.tags]
        except (AttributeError, TypeError):
            return []

    def _fmt_date(date_str: str) -> str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return date_str[:10] if date_str else ""

    return Paper(
        arxiv_id=_extract_arxiv_id(entry),
        title=entry.title.strip().replace("\n", " "),
        abstract=entry.summary.strip().replace("\n", " "),
        authors=_fmt_authors(),
        categories=_fmt_categories(),
        published=_fmt_date(entry.published),
        updated=_fmt_date(entry.updated),
    )


def fetch_category(category: str, max_results: int = 200) -> list[Paper]:
    """Fetch recent papers from a single arXiv category, with retries."""
    params = {
        "search_query": f"cat:{category}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }
    last_err = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            resp = requests.get(
                ARXIV_API, params=params, timeout=FETCH_TIMEOUT
            )
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
            papers = [_parse_entry(e) for e in feed.entries]
            if not papers:
                raise ValueError("empty feed")
            return papers
        except Exception as e:  # noqa: BLE001 - retry any transport/parse error
            last_err = e
            if attempt < FETCH_RETRIES:
                wait = FETCH_BACKOFF * attempt
                print(
                    f"[WARN] {category} attempt {attempt}/{FETCH_RETRIES} "
                    f"failed ({e}); retrying in {wait:.0f}s"
                )
                time.sleep(wait)
    raise RuntimeError(f"{category}: {last_err}")


def fetch_all(
    categories: Optional[list[str]] = None,
    max_results: int = 200,
    delay: float = 3.0,
) -> list[Paper]:
    """Fetch papers from all configured categories with rate-limit delay."""
    cats = categories or CATEGORIES
    all_papers: list[Paper] = []
    for cat in cats:
        try:
            papers = fetch_category(cat, max_results=max_results)
            all_papers.extend(papers)
        except Exception as e:
            print(f"[WARN] Failed to fetch {cat}: {e}")
        time.sleep(delay)
    return all_papers
