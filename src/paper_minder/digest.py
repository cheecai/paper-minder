"""Markdown digest formatter for paper-minder."""

from datetime import datetime

from paper_minder.fetcher import Paper


def format_digest(
    papers: list[Paper],
    date: str = "",
    new_ids: set[str] | None = None,
) -> str:
    """Format scored papers into a Markdown digest.

    Args:
        papers: Scored papers to include (≥ min_score).
        date: Date string for the digest header. Defaults to today.
        new_ids: Set of arxiv_id that are new this run (not cached).
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    new_set = new_ids or set()
    new_papers = [p for p in papers if p.arxiv_id in new_set]

    tier5 = [p for p in papers if p.score == 5]
    tier4 = [p for p in papers if p.score == 4]
    tier3 = [p for p in papers if p.score == 3]

    lines = [
        f"# 📚 arXiv HFT Monitor — {date}",
        "",
        f"**Total:** {len(papers)} papers "
        f"| 🆕 New: {len(new_papers)} "
        f"| 🔥 {len(tier5)} | 📌 {len(tier4)} | ⚡ {len(tier3)}",
        "",
        "---",
        "",
    ]

    # New papers section — what quant should look at first
    if new_papers:
        new5 = [p for p in new_papers if p.score >= 4]
        new3 = [p for p in new_papers if p.score == 3]
        lines.append("## 🆕 New This Run")
        lines.append("")
        for p in sorted(new5, key=lambda x: -x.score):
            lines.extend(_format_paper_compact(p))
        if new3:
            lines.append(f"_...and {len(new3)} more scored 3/5_")
            lines.append("")
        lines.append("---")
        lines.append("")

    # Full digest by tier
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
            lines.extend(_format_paper_compact(p))

    if not papers:
        lines.append("_No relevant papers found today._")

    lines.append("")
    lines.append("---")
    lines.append(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")

    return "\n".join(lines)


def _format_paper(p: Paper) -> list[str]:
    """Format a single paper entry (full)."""
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


def _format_paper_compact(p: Paper) -> list[str]:
    """Format a single paper entry (compact, title + reason only)."""
    authors = ", ".join(p.authors[:2])
    if len(p.authors) > 2:
        authors += " et al."

    lines = [
        f"- **[{p.title}](https://arxiv.org/abs/{p.arxiv_id})** [{p.score}/5]",
        f"  {authors} · {p.published}",
    ]
    if p.relevance_reason:
        lines.append(f"  💡 {p.relevance_reason}")
    lines.append("")
    return lines
