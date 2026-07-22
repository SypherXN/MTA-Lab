#!/usr/bin/env python3
"""Import Cursor usage rows from a CSV export into MTA-Lab."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib import error, request

API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_ROOT))

from app.cursor_usage_csv import load_cursor_usage_csv  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Cursor dashboard usage CSV export")
    parser.add_argument("--api-url", required=True, help="Base URL of MTA-Lab API")
    parser.add_argument("--api-key", required=True, help="MTA write API key")
    parser.add_argument(
        "--automations-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Import only automation rows (Cloud Agent ID / Automation ID present). Default: true.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print row count without posting to the API.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_cursor_usage_csv(args.csv_path, automations_only=args.automations_only)
    if args.dry_run:
        estimated_total = sum(row.get("estimated_cost_usd") or 0 for row in rows)
        print(
            f"dry-run: would import {len(rows)} row(s) "
            f"(automations_only={args.automations_only}, estimated_total=${estimated_total:.2f})"
        )
        print("Note: re-import skips rows already stored (deduped by usage_import_key on the API).")
        if rows[:3]:
            print(json.dumps(rows[:3], indent=2))
        return

    if not rows:
        print("No matching usage rows found.", file=sys.stderr)
        raise SystemExit(1)

    payload = {"rows": rows}
    url = args.api_url.rstrip("/") + "/api/admin/cursor-usage/import"
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-API-Key": args.api_key,
        },
        method="POST",
    )
    try:
        with request.urlopen(req) as resp:
            print(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        print(exc.read().decode("utf-8"))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
