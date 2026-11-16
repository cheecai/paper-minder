"""Tests for the arXiv fetch retry logic.

A transient timeout on export.arxiv.org used to drop an entire category
from the run (q-fin.MF and q-fin.PM vanished with only a WARN printed),
so the daily digest silently lost coverage.
"""

import pytest

from paper_minder import fetcher


class _FakeResponse:
    def __init__(self, text=""):
        self.text = text

    def raise_for_status(self):
        return None


def _feed_with_one_entry():
    return (
        "<feed xmlns='http://www.w3.org/2005/Atom'>"
        "<entry>"
        "<id>http://arxiv.org/abs/2412.20138v1</id>"
        "<title>A Test Paper</title>"
        "<summary>Abstract body.</summary>"
        "<published>2024-12-15T00:00:00Z</published>"
        "<updated>2024-12-15T00:00:00Z</updated>"
        "<author><name>Alice</name></author>"
        "<category term='q-fin.TR'/>"
        "</entry>"
        "</feed>"
    )


def test_fetch_category_returns_papers(monkeypatch):
    monkeypatch.setattr(
        fetcher.requests, "get", lambda *a, **k: _FakeResponse(_feed_with_one_entry())
    )
    papers = fetcher.fetch_category("q-fin.TR", max_results=10)
    assert len(papers) == 1
    assert papers[0].arxiv_id == "2412.20138"


def test_fetch_category_retries_on_timeout(monkeypatch):
    calls = []

    def flaky_get(*args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise fetcher.requests.exceptions.ReadTimeout("read timeout=60")
        return _FakeResponse(_feed_with_one_entry())

    monkeypatch.setattr(fetcher.requests, "get", flaky_get)
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)

    papers = fetcher.fetch_category("q-fin.MF", max_results=10)
    assert len(calls) == 3
    assert len(papers) == 1


def test_fetch_category_raises_after_all_retries(monkeypatch):
    calls = []

    def always_timeout(*args, **kwargs):
        calls.append(1)
        raise fetcher.requests.exceptions.ReadTimeout("read timeout=60")

    monkeypatch.setattr(fetcher.requests, "get", always_timeout)
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError):
        fetcher.fetch_category("q-fin.PM", max_results=10)
    assert len(calls) == fetcher.FETCH_RETRIES


def test_fetch_category_treats_empty_feed_as_failure(monkeypatch):
    calls = []

    def empty_feed(*args, **kwargs):
        calls.append(1)
        return _FakeResponse("<feed xmlns='http://www.w3.org/2005/Atom'></feed>")

    monkeypatch.setattr(fetcher.requests, "get", empty_feed)
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError):
        fetcher.fetch_category("q-fin.TR", max_results=10)
    assert len(calls) == fetcher.FETCH_RETRIES


def test_fetch_all_keeps_other_categories_when_one_fails(monkeypatch):
    def selective(category, max_results=200):
        if category == "q-fin.MF":
            raise RuntimeError("q-fin.MF: boom")
        return [
            fetcher.Paper(
                arxiv_id=f"id-{category}",
                title="t",
                abstract="a",
                authors=[],
                categories=[category],
                published="2024-12-15",
                updated="2024-12-15",
            )
        ]

    monkeypatch.setattr(fetcher, "fetch_category", selective)
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)

    papers = fetcher.fetch_all(["q-fin.TR", "q-fin.MF", "q-fin.PM"])
    ids = {p.arxiv_id for p in papers}
    assert ids == {"id-q-fin.TR", "id-q-fin.PM"}
