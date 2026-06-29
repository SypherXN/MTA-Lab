"""Extended run audit fields for dashboard drill-down."""

import json
import sqlite3

from app.preflight_service import get_live_preflight
from app.schemas import RunAuditOut, RunLinkedOrderOut, RunUsageSummaryOut
from app.safety import build_safety_snapshot, get_active_strategy


def get_run_audit(conn: sqlite3.Connection, run_id: int) -> RunAuditOut:
    run_row = conn.execute(
        "SELECT id, cursor_run_id, usage_json FROM automation_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if run_row is None:
        raise ValueError(f"Run {run_id} not found")

    order_ids = [
        row["order_id"]
        for row in conn.execute(
            """
            SELECT order_id FROM decisions
            WHERE run_id = ? AND order_id IS NOT NULL AND trim(order_id) != ''
            """,
            (run_id,),
        )
    ]

    linked_orders: list[RunLinkedOrderOut] = []
    unmatched: list[str] = []
    for order_id in order_ids:
        rh = conn.execute(
            """
            SELECT robinhood_order_id, symbol, side, status, decision_id
            FROM robinhood_orders WHERE robinhood_order_id = ?
            """,
            (order_id,),
        ).fetchone()
        if rh is None:
            unmatched.append(order_id)
            linked_orders.append(
                RunLinkedOrderOut(
                    order_id=order_id,
                    symbol="—",
                    side="—",
                    status="missing",
                    linked=False,
                )
            )
        else:
            linked_orders.append(
                RunLinkedOrderOut(
                    order_id=rh["robinhood_order_id"],
                    symbol=rh["symbol"],
                    side=rh["side"],
                    status=rh["status"],
                    linked=rh["decision_id"] is not None,
                )
            )

    usage_summary = None
    if run_row["usage_json"]:
        usage = json.loads(run_row["usage_json"])
        usage_summary = RunUsageSummaryOut(
            model=usage.get("model"),
            cost_usd=usage.get("cost_usd"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cursor_run_id=usage.get("cursor_run_id") or run_row["cursor_run_id"],
        )

    strategy = get_active_strategy(conn)
    preflight = get_live_preflight(conn)

    return RunAuditOut(
        run_id=run_id,
        linked_orders=linked_orders,
        unmatched_order_ids=unmatched,
        usage_summary=usage_summary,
        safety_snapshot=build_safety_snapshot(conn, strategy),
        preflight_ready=preflight.ready_for_live,
        preflight_checks=[c.model_dump() for c in preflight.checks],
        inputs_summary={
            "decision_count": conn.execute(
                "SELECT COUNT(*) AS c FROM decisions WHERE run_id = ?", (run_id,)
            ).fetchone()["c"],
            "quote_symbols_at_run": conn.execute(
                "SELECT COUNT(DISTINCT symbol) AS c FROM quote_cache"
            ).fetchone()["c"],
        },
    )
