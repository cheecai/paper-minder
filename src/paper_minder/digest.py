"""Markdown digest formatter for paper-minder."""

from datetime import datetime

from paper_minder.fetcher import Paper


def format_digest(papers: list[Paper], date: str = "") -> str:
    """Format scored papers into a Markdown digest.

    Papers are grouped by score tier:
    - 🔥 Highly Relevant (5)
    - 📌 Relevant (4)
    - ⚡ Worth Noting (3)

    Args:
        papers: Scored papers to include (all should have score >= min_score).
        date: Date string for the digest header. Defaults to today.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    tier5 = [p for p in papers if p.score == 5]
    tier4 = [p for p in papers if p.score == 4]
    tier3 = [p for p in papers if p.score == 3]

    lines = [
        f"# 📚 arXiv HFT Monitor — {date}",
        "",
        f"**Fetched:** {len(papers)} papers "
        f"| 🔥 {len(tier5)} | 📌 {len(tier4)} | ⚡ {len(tier3)}",
        "",
        "---",
        "",
    ]

    if tier5:
        lines.append("## 🔥 Highly Relevant (5/5)")
        lines.append("")
        for p in tier5:
            lines.extend(_format_paper(p))

    if tier4:
        lines.append("## 📌 Relevant (4/5)")
        lines.append("")
        for p in tier4:
            lines.extend(_format_paper(p))

    if tier3:
        lines.append("## ⚡ Worth Noting (3/5)")
        lines.append("")
        for p in tier3:
            lines.extend(_format_paper(p))

    if not papers:
        lines.append("_No relevant papers found today._")

    lines.append("")
    lines.append("---")
    lines.append(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")

    return "\n".join(lines)


def _format_paper(p: Paper) -> list[str]:
    """Format a single paper entry."""
    authors = ", ".join(p.authors[:3])
    if len(p.authors) > 3:
        authors += " et al."
    cats = ", ".join(p.categories[:3])

    lines = [
        f"### [{p.title}](https://arxiv.org/abs/{p.arxiv_id})",
        f"**{authors}** · {cats} · {p.published}",
        "",
    ]

    abstract = p.abstract[:400]
    if len(p.abstract) > 400:
        abstract += "..."
    lines.append(f"> {abstract}")
    lines.append("")

    if p.relevance_reason:
        lines.append(f"💡 {p.relevance_reason}")
        lines.append("")

    return lines
