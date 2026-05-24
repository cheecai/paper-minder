"""CLI entry point for paper-minder."""

import argparse
import sys
from pathlib import Path

from paper_minder.fetcher import fetch_all, CATEGORIES
from paper_minder.scorer import score_paper, get_model
from paper_minder.store import get_db, upsert_paper
from paper_minder.digest import format_digest


def main():
    parser = argparse.ArgumentParser(
        description="arXiv HFT paper monitor — fetch, score, store, digest"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and score but do not store to database",
    )
    parser.add_argument(
        "--min-score", type=int, default=3,
        help="Minimum score for digest and storage (default: 3)",
    )
    parser.add_argument(
        "--categories", nargs="*",
        help="Specific arXiv categories (default: q-fin.TR/ST/CP/MF/PM)",
    )
    parser.add_argument(
        "--max-results", type=int, default=100,
        help="Max papers per category (default: 100)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="LLM model string (default: PAPER_MINDER_MODEL env or deepseek/deepseek-chat)",
    )
    parser.add_argument(
        "--no-score", action="store_true",
        help="Skip LLM scoring (fetch + store only, existing scores preserved)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Save digest to file (e.g. ~/hermes/hft/quant/digest.md)",
    )
    args = parser.parse_args()

    model = args.model or get_model()
    cats = args.categories or CATEGORIES

    # ── Fetch ──────────────────────────────────────────────────────
    print(f"📡 Fetching from: {', '.join(cats)}", file=sys.stderr)
    papers = fetch_all(cats, max_results=args.max_results)
    print(f"📥 Fetched {len(papers)} papers total", file=sys.stderr)

    # Deduplicate by arxiv_id within this run
    seen = set()
    unique = []
    for p in papers:
        if p.arxiv_id not in seen:
            seen.add(p.arxiv_id)
            unique.append(p)
    print(f"📋 {len(unique)} unique papers", file=sys.stderr)

    # ── Score ──────────────────────────────────────────────────────
    # Load existing scores from DB to avoid re-scoring
    existing_scores = {}
    if not args.dry_run:
        conn = get_db()
        rows = conn.execute(
            "SELECT arxiv_id, score, relevance_reason FROM papers WHERE score > 0"
        ).fetchall()
        existing_scores = {r["arxiv_id"]: (r["score"], r["relevance_reason"]) for r in rows}
        conn.close()

    to_score = [p for p in unique if p.arxiv_id not in existing_scores]
    already_scored = [p for p in unique if p.arxiv_id in existing_scores]
    for p in already_scored:
        p.score, p.relevance_reason = existing_scores[p.arxiv_id]

    if not args.no_score and to_score:
        print(f"🤖 Scoring {len(to_score)} new papers with {model}... ({len(already_scored)} cached)", file=sys.stderr)
        for i, paper in enumerate(to_score):
            score_paper(paper, model=model)
            if (i + 1) % 10 == 0:
                print(f"   Scored {i+1}/{len(to_score)}...", file=sys.stderr)
        print(f"   Done: {len(to_score)} papers scored", file=sys.stderr)
    elif not to_score:
        print(f"✅ All {len(unique)} papers already scored — using cached scores", file=sys.stderr)

    scored = [p for p in unique if p.score >= args.min_score]
    scored.sort(key=lambda p: p.score, reverse=True)
    print(f"⭐ {len(scored)} papers scored ≥{args.min_score}", file=sys.stderr)

    # ── Store ──────────────────────────────────────────────────────
    if not args.dry_run:
        conn = get_db()
        new_count = 0
        for paper in scored:
            if upsert_paper(conn, paper):
                new_count += 1
        conn.close()
        print(
            f"💾 Stored: {new_count} new, {len(scored) - new_count} updated",
            file=sys.stderr,
        )
    else:
        print("🧪 Dry run — nothing stored", file=sys.stderr)

    # ── Digest ─────────────────────────────────────────────────────
    new_ids = {p.arxiv_id for p in to_score if p.score >= args.min_score}
    digest = format_digest(scored, new_ids=new_ids)
    print(digest)

    if args.output:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(digest)
        print(f"📄 Digest saved to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
