import sqlite3

from app.schemas import TimelineEventOut


def get_activity_timeline(conn: sqlite3.Connection, limit: int = 100) -> list[TimelineEventOut]:
    events: list[TimelineEventOut] = []

    for row in conn.execute(
        """
        SELECT id, run_at, automation_name, run_type, status, market_summary
        FROM automation_runs
        ORDER BY run_at DESC
        LIMIT ?
        """,
        (limit,),
    ):
        title = f"Run #{row['id']} · {row['status']}"
        detail = row["market_summary"] or row["automation_name"] or ""
        events.append(
            TimelineEventOut(
                at=row["run_at"],
                event_type="run",
                title=title,
                detail=detail,
                run_id=row["id"],
                symbol=None,
                meta={"run_type": row["run_type"], "status": row["status"]},
            )
        )

    for row in conn.execute(
        """
        SELECT d.id, d.created_at, d.symbol, d.action, d.reason, d.run_id, d.confidence
        FROM decisions d
        ORDER BY d.created_at DESC
        LIMIT ?
        """,
        (limit,),
    ):
        events.append(
            TimelineEventOut(
                at=row["created_at"],
                event_type="decision",
                title=f"{row['symbol']} · {row['action']}",
                detail=row["reason"],
                run_id=row["run_id"],
                symbol=row["symbol"],
                meta={"decision_id": row["id"], "confidence": row["confidence"]},
            )
        )

    for row in conn.execute(
        """
        SELECT id, created_at, symbol, message, signal_type, source
        FROM market_signals
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ):
        events.append(
            TimelineEventOut(
                at=row["created_at"],
                event_type="signal",
                title=f"Signal · {row['symbol'] or 'market'}",
                detail=row["message"],
                run_id=None,
                symbol=row["symbol"],
                meta={"signal_type": row["signal_type"], "source": row["source"]},
            )
        )

    for row in conn.execute(
        """
        SELECT ro.id, ro.created_at, ro.symbol, ro.side, ro.status, ro.decision_id
        FROM robinhood_orders ro
        ORDER BY ro.created_at DESC
        LIMIT ?
        """,
        (limit,),
    ):
        recon = "linked" if row["decision_id"] is not None else "unmatched"
        events.append(
            TimelineEventOut(
                at=row["created_at"],
                event_type="order",
                title=f"Order · {row['symbol']} {row['side']}",
                detail=row["status"],
                run_id=None,
                symbol=row["symbol"],
                meta={
                    "order_id": row["id"],
                    "decision_id": row["decision_id"],
                    "reconciliation_status": recon,
                },
            )
        )

    events.sort(key=lambda e: e.at, reverse=True)
    return events[:limit]
