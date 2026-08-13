#!/usr/bin/env python3
"""Backfill SPY/QQQ/DIA daily history from Yahoo for lane-vs-market comparison."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)

from app.database import get_connection, init_db  # noqa: E402
from app.quote_history_service import BENCHMARK_SYMBOLS, ensure_benchmark_history  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill benchmark quote history from Yahoo.")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if history already covers snapshots")
    args = parser.parse_args()

    init_db()
    conn = get_connection()
    try:
        result = ensure_benchmark_history(conn, symbols=BENCHMARK_SYMBOLS, force=args.force)
        conn.commit()
    finally:
        conn.close()

    for symbol, count in result.items():
        print(f"{symbol}: wrote {count} daily bar(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
