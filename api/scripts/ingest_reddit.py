#!/usr/bin/env python3
"""Fetch public Reddit finance listings and ingest mention summaries.

Runs on the VM via cron before the reddit-research lane. Dedupes by source + external_id.
Does not log in or scrape private content.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)

from app.config import settings  # noqa: E402
from app.database import get_connection, init_db  # noqa: E402
from app.reddit_service import fetch_reddit_research, ingest_reddit_research  # noqa: E402
from app.safety import get_active_strategy  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--subreddits", default=None)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    init_db()
    conn = get_connection()
    try:
        allowed = get_active_strategy(conn).rules.allowed_symbols
        research = fetch_reddit_research(
            subreddits=args.subreddits,
            limit=args.limit,
            allowed_symbols=allowed,
        )
        print(
            f"fetched posts={len(research.posts)} mentions={len(research.mentions)} "
            f"errors={len(research.errors)}"
        )
        for error in research.errors:
            print(f"  error: {error}")
        if args.dry_run:
            for mention in research.mentions[:15]:
                print(
                    f"  {mention.symbol}: posts={mention.post_count} "
                    f"sentiment={mention.avg_sentiment:.2f}"
                )
            return 0
        inserted, skipped = ingest_reddit_research(conn, research)
        conn.commit()
        print(f"ingested inserted={inserted} skipped={skipped}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
