#!/usr/bin/env python3
"""Seed a sample research run for local dashboard testing."""

from datetime import datetime, timezone

import httpx

API = "http://127.0.0.1:8000"
KEY = "dev-key-change-me"


def main() -> None:
    run_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "run_at": run_at,
        "automation_name": "mta-research-daily",
        "cursor_run_id": "sample-run-001",
        "status": "completed",
        "market_summary": "Markets mixed; tech flat, rates steady. No strong signal on watchlist.",
        "buying_power": 10000.0,
        "decisions": [
            {
                "symbol": "SPY",
                "action": "hold",
                "reason": "Already near target allocation; no rebalance trigger.",
            },
            {
                "symbol": "AAPL",
                "action": "simulated_buy",
                "reason": "Would add on pullback; review_equity_order passed in research mode.",
                "amount_usd": 250.0,
                "fill_price": 250.0,
                "review_output": "Simulated market buy $250 AAPL — no warnings.",
            },
        ],
        "usage": {
            "model": "composer-2.5",
            "cost_usd": 0.08,
        },
    }
    response = httpx.post(
        f"{API}/api/automation/runs",
        json=payload,
        headers={"X-API-Key": KEY},
        timeout=10.0,
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
