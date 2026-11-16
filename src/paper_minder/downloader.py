"""arXiv PDF downloader for paper-minder."""

import sys
import time
from pathlib import Path

import requests

from paper_minder.fetcher import Paper

# arXiv rate limit: be polite
ARXIV_DELAY = 3.0  # seconds between downloads
PDF_DIR_DEFAULT = Path.home() / "hermes" / "hft" / "papers"

HEADERS = {
    "User-Agent": "paper-minder/0.1 (mailto:changeme@example.com)"
}


def download_one(
    paper: Paper,
    pdf_dir: Path = PDF_DIR_DEFAULT,
    force: bool = False,
) -> str | None:
    """Download a single paper's PDF from arXiv.

    Returns the local path on success, None on failure.
    Skips if the file already exists (unless force=True).
    """
    pdf_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{paper.arxiv_id}.pdf"
    local_path = pdf_dir / filename

    if local_path.exists() and not force:
        print(f"  ⏭  {paper.arxiv_id} already downloaded", file=sys.stderr)
        return str(local_path)

    try:
        resp = requests.get(
            paper.pdf_url,
            headers=HEADERS,
            timeout=60,
            stream=True,
        )
        resp.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"  ✅ {paper.arxiv_id}.pdf", file=sys.stderr)
        return str(local_path)

    except requests.RequestException as e:
        print(f"  ❌ {paper.arxiv_id}: {e}", file=sys.stderr)
        return None


def download_papers(
    papers: list[Paper],
    pdf_dir: Path = PDF_DIR_DEFAULT,
    force: bool = False,
) -> dict[str, str]:
    """Download PDFs for a list of papers.

    Returns dict of arxiv_id -> local_path for successful downloads.
    Respects arXiv rate limits with a delay between requests.
    """
    if not papers:
        print("📭 No papers to download", file=sys.stderr)
        return {}

    print(
        f"📥 Downloading {len(papers)} PDFs to {pdf_dir}...", file=sys.stderr
    )
    results: dict[str, str] = {}

    for i, paper in enumerate(papers):
        path = download_one(paper, pdf_dir=pdf_dir, force=force)
        if path:
            results[paper.arxiv_id] = path

        # Rate limit — but not after the last one
        if i < len(papers) - 1:
            time.sleep(ARXIV_DELAY)

    success = len(results)
    failed = len(papers) - success
    print(
        f"📁 Downloaded: {success} ok, {failed} failed", file=sys.stderr
    )
    return results
