#!/usr/bin/env python3
"""Poll quote prices and fire MTA-Lab price-alert webhooks on threshold moves."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

DEFAULT_THRESHOLD = 1.5


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def api_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def pct_change(old: float, new: float) -> float:
    if old <= 0:
        return 0.0
    return ((new - old) / old) * 100.0


def main() -> int:
    parser = argparse.ArgumentParser(description="MTA-Lab intraday price watcher")
    parser.add_argument("--api-base", default=os.environ.get("MTA_API_BASE", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.environ.get("MTA_WRITE_API_KEY", ""))
    parser.add_argument(
        "--quotes-file",
        type=Path,
        help="JSON file: [{\"symbol\":\"SPY\",\"price_usd\":520.5}]",
    )
    parser.add_argument(
        "--threshold-pct",
        type=float,
        default=float(os.environ.get("MTA_WATCHER_PCT_THRESHOLD", DEFAULT_THRESHOLD)),
    )
    parser.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parent.parent / ".env")
    args = parser.parse_args()

    load_env_file(args.env_file)
    api_base = args.api_base.rstrip("/")
    api_key = args.api_key or os.environ.get("MTA_WRITE_API_KEY", "")
    threshold = args.threshold_pct

    if args.quotes_file is None:
        quotes_env = os.environ.get("MTA_WATCHER_QUOTES_JSON")
        if not quotes_env:
            print("Provide --quotes-file or MTA_WATCHER_QUOTES_JSON", file=sys.stderr)
            return 1
        quotes = json.loads(quotes_env)
    else:
        quotes = json.loads(args.quotes_file.read_text(encoding="utf-8"))

    headers = api_headers(api_key)
    with httpx.Client(timeout=20.0) as client:
        context = client.get(f"{api_base}/api/automation/context", headers=headers)
        context.raise_for_status()
        watchlist = set(context.json()["strategy"]["rules"]["watchlist"])

        cached = {
            row["symbol"]: float(row["price_usd"])
            for row in client.get(f"{api_base}/api/dashboard/quotes", headers=headers).json()
        }

        import_payload = {
            "quotes": [
                {
                    "symbol": q["symbol"].upper(),
                    "price_usd": float(q["price_usd"]),
                    "source": q.get("source", "price_watcher"),
                }
                for q in quotes
                if q.get("symbol") and float(q.get("price_usd", 0)) > 0
            ]
        }
        if not import_payload["quotes"]:
            print("No valid quotes to import.")
            return 0

        client.post(
            f"{api_base}/api/admin/quotes/import",
            headers=headers,
            json=import_payload,
        ).raise_for_status()

        alerts = 0
        for quote in import_payload["quotes"]:
            symbol = quote["symbol"]
            if watchlist and symbol not in watchlist:
                continue
            new_price = quote["price_usd"]
            old_price = cached.get(symbol)
            if old_price is None:
                continue
            change = pct_change(old_price, new_price)
            if abs(change) < threshold:
                continue
            message = (
                f"{symbol} moved {change:+.2f}% ({old_price:.2f} -> {new_price:.2f}); "
                f"threshold {threshold:g}%"
            )
            client.post(
                f"{api_base}/api/admin/webhooks/price-alert",
                headers=headers,
                json={
                    "symbol": symbol,
                    "message": message,
                    "signal_type": "price_alert",
                    "source": "price_watcher",
                    "payload": {
                        "old_price": old_price,
                        "new_price": new_price,
                        "pct_change": change,
                    },
                },
            ).raise_for_status()
            alerts += 1
            print(message)

    print(f"Imported {len(import_payload['quotes'])} quote(s); fired {alerts} alert(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
