"""Head-to-head comparison of simulation lanes."""

import sqlite3

from app.lane_service import get_lane, list_lanes
from app.schemas import LaneCompareOut, LaneCompareRowOut
from app.snapshot_service import get_lane_equity_change


def compare_lanes(
    conn: sqlite3.Connection,
    *,
    lane_ids: list[int] | None = None,
    since: str | None = None,
) -> LaneCompareOut:
    if lane_ids:
        lanes = [get_lane(conn, lid) for lid in lane_ids]
    else:
        lanes = [lane for lane in list_lanes(conn) if lane.status == "active"]

    rows: list[LaneCompareRowOut] = []
    for lane in lanes:
        lid = lane.id
        run_stats = conn.execute(
            """
            SELECT
                COUNT(*) AS run_count,
                SUM(CASE WHEN lower(status) = 'completed' THEN 1 ELSE 0 END) AS completed_runs
            FROM automation_runs
            WHERE lane_id = ?
            """ + (" AND run_at >= ?" if since else ""),
            (lid, since) if since else (lid,),
        ).fetchone()

        decision_stats = conn.execute(
            """
            SELECT
                COUNT(*) AS decision_count,
                AVG(d.confidence) AS avg_confidence,
                SUM(CASE WHEN lower(d.action) IN (
                    'simulated_buy', 'simulated_sell', 'paper_buy', 'paper_sell'
                ) THEN 1 ELSE 0 END) AS simulated_trades
            FROM decisions d
            JOIN automation_runs r ON r.id = d.run_id
            WHERE r.lane_id = ?
            """ + (" AND r.run_at >= ?" if since else ""),
            (lid, since) if since else (lid,),
        ).fetchone()

        cost_row = conn.execute(
            """
            SELECT COALESCE(SUM(cu.cost_usd), 0) AS total
            FROM cursor_usage cu
            JOIN automation_runs r ON r.id = cu.run_id
            WHERE r.lane_id = ?
            """ + (" AND r.run_at >= ?" if since else ""),
            (lid, since) if since else (lid,),
        ).fetchone()

        equity_change = get_lane_equity_change(conn, lid, since=since)

        rows.append(
            LaneCompareRowOut(
                lane_id=lid,
                name=lane.name,
                strategy_version=lane.strategy_version,
                plan_version=lane.plan_version,
                lane_role=lane.lane_role,
                status=lane.status,
                run_count=int(run_stats["run_count"] or 0),
                completed_runs=int(run_stats["completed_runs"] or 0),
                decision_count=int(decision_stats["decision_count"] or 0),
                simulated_trades=int(decision_stats["simulated_trades"] or 0),
                avg_confidence=decision_stats["avg_confidence"],
                equity_change_usd=equity_change,
                total_cost_usd=float(cost_row["total"] or 0),
            )
        )

    return LaneCompareOut(since=since, lanes=rows)
