"""CLI entry point for paper-minder."""

import argparse
import sys
from datetime import date
from pathlib import Path

from paper_minder.fetcher import fetch_all, CATEGORIES
from paper_minder.scorer import score_paper, get_model
from paper_minder.store import (
    get_db,
    upsert_paper,
    mark_downloaded,
    record_arrivals,
    get_arrivals,
    get_meta,
    set_meta,
    seed_arrivals,
)
from paper_minder.digest import format_digest
from paper_minder.downloader import download_papers, PDF_DIR_DEFAULT

# Sentinel date for papers that predate the arrivals log (backfilled at
# migration time). They were seen before the monitor tracked arrivals, so
# their true arrival date is unknown — never count them as "new".
LEGACY_DATE = "unknown"


def main():
    parser = argparse.ArgumentParser(
        description="arXiv HFT paper monitor — fetch, score, store, digest"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and score but do not store to database",
    )
    parser.add_argument(
        "--min-score", type=int, default=4,
        help="Minimum score for digest and storage (default: 4)",
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
    parser.add_argument(
        "--download", action="store_true",
        help="Download PDFs for high-score papers",
    )
    parser.add_argument(
        "--download-dir", type=str, default=str(PDF_DIR_DEFAULT),
        help=f"Directory to save PDFs (default: {PDF_DIR_DEFAULT})",
    )
    parser.add_argument(
        "--download-min-score", type=int, default=None,
        help="Min score for downloading PDFs (default: same as --min-score)",
    )
    parser.add_argument(
        "--arrivals-cutover-id", type=int, default=0,
        help=(
            "One-time migration: papers with a DB id above this value were "
            "inserted before the arrivals log existed but ARE today's "
            "arrivals, so they get dated today. Papers at or below it are "
            "legacy (true arrival date unknowable) and never count as new."
        ),
    )
    args = parser.parse_args()

    model = args.model or get_model()
    cats = args.categories or CATEGORIES
    download_score = (
        args.download_min_score
        if args.download_min_score is not None
        else args.min_score
    )

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
    known_ids = set()
    if not args.dry_run:
        conn = get_db()
        rows = conn.execute(
            "SELECT arxiv_id, score, relevance_reason FROM papers WHERE score > 0"
        ).fetchall()
        existing_scores = {r["arxiv_id"]: (r["score"], r["relevance_reason"]) for r in rows}
        # Every id the monitor has ever scored (incl. sub-threshold) — used
        # to report genuinely new papers rather than re-scored ones.
        known_ids = {
            r[0]
            for r in conn.execute("SELECT arxiv_id FROM papers").fetchall()
        }
        conn.close()

    # ── Arrivals ───────────────────────────────────────────────────
    # "New" must mean "first sighted today", and that has to survive a
    # same-day retry (arXiv rate-limits categories often enough that a
    # retry is routine). Deriving it from a live DB snapshot does not: the
    # first attempt already inserted the papers, so every retry reports 0
    # new. The arrivals log is persistent and written at INSERT time, so
    # a retry still sees today's arrivals.
    today = date.today().isoformat()
    arrivals_total = 0
    arrivals_new = 0
    if not args.dry_run:
        conn = get_db()
        if get_meta(conn, "arrivals_seeded") is None:
            # Baseline = the newest paper that predates the arrivals log.
            # Default: every existing paper is legacy (its true arrival date
            # is unknowable), so only papers arriving from now on count as
            # new. A deployment can set `arrivals_cutover_id` in the meta
            # table to a lower id to date the papers inserted by a
            # pre-migration run.
            baseline = int(get_meta(conn, "arrivals_cutover_id", "0"))
            if args.arrivals_cutover_id > 0:
                baseline = args.arrivals_cutover_id
            if baseline <= 0:
                row = conn.execute("SELECT MAX(id) FROM papers").fetchone()
                baseline = row[0] or 0
            legacy, recent = seed_arrivals(
                conn, baseline, LEGACY_DATE, today
            )
            set_meta(conn, "arrivals_seeded", "1")
            set_meta(conn, "arrivals_cutover_id", str(baseline))
            print(
                f"🧾 Seeded arrivals log: {legacy} legacy, {recent} dated today",
                file=sys.stderr,
            )
        # Ids fetched this run that were never logged before are genuinely
        # new arrivals.
        arrivals_new = record_arrivals(
            conn, [p.arxiv_id for p in unique], today
        )
        arrivals_total = len(get_arrivals(conn, today))
        conn.close()
        print(
            f"📥 Arrivals: {arrivals_new} new this run, "
            f"{arrivals_total} total seen today",
            file=sys.stderr,
        )

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
    # Store EVERY scored paper, not just those above the digest threshold.
    # Papers scoring below min_score are still cached, otherwise every run
    # re-scores the same hundreds of sub-threshold papers (wasting API calls
    # and making the "new papers" count meaningless).
    if not args.dry_run:
        conn = get_db()
        new_count = 0
        stored = [p for p in unique if p.score > 0]
        for paper in stored:
            if upsert_paper(conn, paper):
                new_count += 1
        conn.close()
        print(
            f"💾 Stored: {new_count} new, {len(stored) - new_count} updated "
            f"({len(stored)} scored total)",
            file=sys.stderr,
        )
    else:
        print("🧪 Dry run — nothing stored", file=sys.stderr)

    # ── Download ───────────────────────────────────────────────────
    if args.download:
        to_download = [p for p in scored if p.score >= download_score]
        if to_download:
            dl_dir = Path(args.download_dir).expanduser()
            results = download_papers(to_download, pdf_dir=dl_dir)

            # Update DB with download status
            if not args.dry_run and results:
                conn = get_db()
                for p in to_download:
                    if p.arxiv_id in results:
                        p.local_path = results[p.arxiv_id]
                        mark_downloaded(
                            conn,
                            p.arxiv_id,
                            p.local_path,
                            p.pdf_url,
                        )
                conn.close()
        else:
            print(f"📭 No papers scored ≥{download_score} to download", file=sys.stderr)

    # ── Digest ─────────────────────────────────────────────────────
    # "New" = papers first sighted TODAY (per the arrivals log), among the
    # papers that made the digest. Reading it from the arrivals log (not
    # from a DB snapshot) keeps the count correct across same-day retries.
    if not args.dry_run:
        conn = get_db()
        new_ids = get_arrivals(conn, today) & {p.arxiv_id for p in scored}
        conn.close()
    else:
        new_ids = {
            p.arxiv_id for p in scored if p.arxiv_id not in known_ids
        }
    digest = format_digest(scored, new_ids=new_ids)
    print(digest)

    if args.output:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(digest)
        print(f"📄 Digest saved to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
