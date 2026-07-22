#!/usr/bin/env python3
"""Backfill cursor_usage → automation_runs links and cursor_run_id on runs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)

from app.database import get_connection, init_db  # noqa: E402
from app.usage_relink_service import relink_cursor_usage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Relink cursor usage rows to automation runs.")
    parser.add_argument("--tolerance-minutes", type=int, default=120)
    parser.add_argument("--no-scout-runs", action="store_true")
    args = parser.parse_args()

    init_db()
    conn = get_connection()
    try:
        result = relink_cursor_usage(
            conn,
            tolerance_minutes=args.tolerance_minutes,
            create_scout_runs=not args.no_scout_runs,
        )
        conn.commit()
    finally:
        conn.close()

    print(
        "exact_linked={exact} fuzzy_linked={fuzzy} runs_backfilled={backfill} "
        "scout_runs_created={scout} remaining_unlinked={remaining}".format(
            exact=result.exact_usage_linked,
            fuzzy=result.fuzzy_usage_linked,
            backfill=result.runs_cursor_run_id_backfilled,
            scout=result.scout_runs_created,
            remaining=result.remaining_unlinked,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
