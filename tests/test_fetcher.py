import pytest
from paper_minder.fetcher import _extract_arxiv_id, _parse_entry, Paper


class FakeEntry:
    """Minimal feedparser entry-like object for unit testing."""
    def __init__(self):
        self.id = "http://arxiv.org/abs/2412.20138v2"
        self.title = "A Test Paper"
        self.summary = "This is a test abstract."
        self.authors = []
        self.tags = []
        self.published = "2024-12-15T00:00:00Z"
        self.updated = "2024-12-16T00:00:00Z"


class FakeAuthor:
    def __init__(self, name):
        self.name = name


class FakeTag:
    def __init__(self, term):
        self.term = term


def test_extract_arxiv_id():
    entry = FakeEntry()
    assert _extract_arxiv_id(entry) == "2412.20138"


def test_extract_arxiv_id_no_version():
    entry = FakeEntry()
    entry.id = "http://arxiv.org/abs/2412.20138"
    # When no 'v' in the string
    result = _extract_arxiv_id(entry)
    assert result == "2412.20138"


def test_parse_entry_basic():
    entry = FakeEntry()
    paper = _parse_entry(entry)
    assert paper.arxiv_id == "2412.20138"
    assert paper.title == "A Test Paper"
    assert paper.abstract == "This is a test abstract."
    assert paper.published == "2024-12-15"
    assert paper.updated == "2024-12-16"
    assert paper.authors == []
    assert paper.categories == []
    assert paper.score == 0
    assert paper.relevance_reason == ""


def test_parse_entry_with_authors():
    entry = FakeEntry()
    entry.authors = [FakeAuthor("Alice"), FakeAuthor("Bob")]
    paper = _parse_entry(entry)
    assert paper.authors == ["Alice", "Bob"]


def test_parse_entry_with_categories():
    entry = FakeEntry()
    entry.tags = [FakeTag("q-fin.TR"), FakeTag("q-fin.ST")]
    paper = _parse_entry(entry)
    assert paper.categories == ["q-fin.TR", "q-fin.ST"]


def test_parse_entry_multiline_title():
    entry = FakeEntry()
    entry.title = "A\nVery\nLong\nTitle"
    paper = _parse_entry(entry)
    assert "\n" not in paper.title
    assert paper.title == "A Very Long Title"


def test_parse_entry_multiline_abstract():
    entry = FakeEntry()
    entry.summary = "Line one.\nLine two.\nLine three."
    paper = _parse_entry(entry)
    assert "\n" not in paper.abstract
