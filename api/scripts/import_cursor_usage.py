#!/usr/bin/env python3
"""Import Cursor usage rows from a CSV export into MTA-Lab."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from urllib import error, request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Cursor dashboard usage CSV export")
    parser.add_argument("--api-url", required=True, help="Base URL of MTA-Lab API")
    parser.add_argument("--api-key", required=True, help="MTA write API key")
    return parser.parse_args()


def load_rows(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            cost = row.get("cost") or row.get("Cost") or row.get("cost_usd") or row.get("charged")
            if cost in (None, ""):
                continue
            rows.append(
                {
                    "cursor_run_id": row.get("run_id") or row.get("Run ID") or row.get("cursor_run_id"),
                    "model": row.get("model") or row.get("Model"),
                    "cost_usd": float(str(cost).replace("$", "")),
                    "input_tokens": _maybe_int(row.get("input_tokens") or row.get("Input Tokens")),
                    "output_tokens": _maybe_int(row.get("output_tokens") or row.get("Output Tokens")),
                    "timestamp": row.get("timestamp") or row.get("Timestamp"),
                }
            )
    return rows


def _maybe_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def main() -> None:
    args = parse_args()
    payload = {"rows": load_rows(args.csv_path)}
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
