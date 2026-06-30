from datetime import datetime, timezone
import csv
import io
import json

import sqlite3

from app.decision_utils import DECISION_SELECT_COLUMNS, decision_summary_from_row
from app.run_utils import RUN_SUMMARY_FROM, RUN_SUMMARY_SELECT, run_summary_from_row
from app.schemas import (
    CursorUsageImportRequest,
    CursorUsageOut,
    DashboardStatsOut,
    DecisionSummaryOut,
    MobileStatusOut,
    PortfolioSnapshotOut,
    PortfolioSnapshotSummaryOut,
    QuoteOut,
    RunSummaryOut,
)
from app.snapshot_service import get_portfolio_snapshot_summary, get_portfolio_snapshots

def get_dashboard_runs(conn: sqlite3.Connection, limit: int = 50) -> list[RunSummaryOut]:
    return [
        run_summary_from_row(row)
        for row in conn.execute(
            f"""
            SELECT {RUN_SUMMARY_SELECT}
            FROM {RUN_SUMMARY_FROM}
            ORDER BY r.id DESC
            LIMIT ?
            """,
            (limit,),
        )
    ]


def get_dashboard_decisions(
    conn: sqlite3.Connection,
    limit: int = 100,
    symbol: str | None = None,
) -> list[DecisionSummaryOut]:
    query = f"""
        SELECT {DECISION_SELECT_COLUMNS}
        FROM decisions
    """
    params: list = []
    if symbol:
        query += " WHERE upper(symbol) = upper(?)"
        params.append(symbol)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    return [
        decision_summary_from_row(row)
        for row in conn.execute(query, params)
    ]


def get_dashboard_stats(conn: sqlite3.Connection) -> DashboardStatsOut:
    strategy = conn.execute(
        """
        SELECT mode, trading_enabled
        FROM strategies
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    total_runs = conn.execute("SELECT COUNT(*) AS c FROM automation_runs").fetchone()["c"]
    completed_runs = conn.execute(
        "SELECT COUNT(*) AS c FROM automation_runs WHERE lower(status) = 'completed'"
    ).fetchone()["c"]
    failed_runs = conn.execute(
        "SELECT COUNT(*) AS c FROM automation_runs WHERE lower(status) = 'failed'"
    ).fetchone()["c"]
    total_decisions = conn.execute("SELECT COUNT(*) AS c FROM decisions").fetchone()["c"]
    simulated_trades = conn.execute(
        """
        SELECT COUNT(*) AS c FROM decisions
        WHERE lower(action) IN ('simulated_buy', 'simulated_sell', 'paper_buy', 'paper_sell')
        """
    ).fetchone()["c"]
    live_trades = conn.execute(
        """
        SELECT COUNT(*) AS c FROM decisions
        WHERE lower(action) IN ('buy', 'sell', 'place_buy', 'place_sell')
        """
    ).fetchone()["c"]
    holds = conn.execute(
        """
        SELECT COUNT(*) AS c FROM decisions
        WHERE lower(action) IN ('hold', 'skip', 'no_action')
        """
    ).fetchone()["c"]
    total_cost = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cursor_usage"
    ).fetchone()["total"]

    return DashboardStatsOut(
        total_runs=total_runs,
        completed_runs=completed_runs,
        failed_runs=failed_runs,
        total_decisions=total_decisions,
        simulated_trades=simulated_trades,
        live_trades=live_trades,
        holds_and_skips=holds,
        total_cursor_cost_usd=float(total_cost),
        strategy_mode=strategy["mode"] if strategy else "unknown",
        trading_enabled=bool(strategy["trading_enabled"]) if strategy else False,
    )


def _resolve_run_id(
    conn: sqlite3.Connection,
    run_id: int | None,
    cursor_run_id: str | None,
) -> int | None:
    if run_id is not None:
        return run_id
    if not cursor_run_id:
        return None
    row = conn.execute(
        "SELECT id FROM automation_runs WHERE cursor_run_id = ?",
        (cursor_run_id,),
    ).fetchone()
    return int(row["id"]) if row else None


def import_cursor_usage(conn: sqlite3.Connection, payload: CursorUsageImportRequest) -> tuple[int, int]:
    inserted = 0
    linked = 0
    for row in payload.rows:
        resolved_run_id = _resolve_run_id(conn, row.run_id, row.cursor_run_id)
        if resolved_run_id is not None and row.run_id is None:
            linked += 1
        conn.execute(
            """
            INSERT INTO cursor_usage (
                run_id, cursor_run_id, model, cost_usd, input_tokens, output_tokens,
                source, reconciled_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'cursor_dashboard_csv', ?)
            """,
            (
                resolved_run_id,
                row.cursor_run_id,
                row.model,
                row.cost_usd,
                row.input_tokens,
                row.output_tokens,
                (row.timestamp or datetime.now(timezone.utc)).isoformat(),
            ),
        )
        inserted += 1

    relink = conn.execute(
        """
        UPDATE cursor_usage
        SET run_id = (
            SELECT r.id FROM automation_runs r
            WHERE r.cursor_run_id = cursor_usage.cursor_run_id
            LIMIT 1
        )
        WHERE run_id IS NULL AND cursor_run_id IS NOT NULL
        """
    )
    linked += relink.rowcount
    if inserted:
        from app.freshness_service import touch_data_source

        touch_data_source(conn, "cursor_usage", detail=f"{inserted} rows")
    return inserted, linked

def get_dashboard_usage(conn: sqlite3.Connection, limit: int = 50) -> list[CursorUsageOut]:
    return [
        CursorUsageOut(
            id=row["id"],
            run_id=row["run_id"],
            cursor_run_id=row["cursor_run_id"],
            model=row["model"],
            cost_usd=row["cost_usd"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            source=row["source"],
            reconciled_at=row["reconciled_at"],
            created_at=row["created_at"],
        )
        for row in conn.execute(
            """
            SELECT id, run_id, cursor_run_id, model, cost_usd, input_tokens, output_tokens,
                   source, reconciled_at, created_at
            FROM cursor_usage
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
    ]


def get_dashboard_portfolio_snapshots(
    conn: sqlite3.Connection,
    limit: int = 100,
    since: str | None = None,
    until: str | None = None,
    run_id: int | None = None,
    lane_id: int | None = None,
) -> list[PortfolioSnapshotOut]:
    rows = get_portfolio_snapshots(
        conn, limit=limit, since=since, until=until, run_id=run_id, lane_id=lane_id
    )
    return [
        PortfolioSnapshotOut(
            id=row["id"],
            lane_id=row["lane_id"] if "lane_id" in row.keys() else None,
            snapshot_at=row["snapshot_at"],
            run_id=row["run_id"],
            cash_usd=float(row["cash_usd"]),
            positions_value_usd=float(row["positions_value_usd"]),
            total_equity_usd=float(row["total_equity_usd"]),
            unrealized_pnl_usd=row["unrealized_pnl_usd"],
            source=row["source"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_dashboard_portfolio_snapshot_summary(
    conn: sqlite3.Connection,
    lane_id: int | None = None,
) -> PortfolioSnapshotSummaryOut | None:
    summary = get_portfolio_snapshot_summary(conn, lane_id=lane_id)
    if summary is None:
        return None
    return PortfolioSnapshotSummaryOut.model_validate(summary)


def get_quote_cache(conn: sqlite3.Connection) -> list[QuoteOut]:
    return [
        QuoteOut(
            symbol=row["symbol"],
            price_usd=float(row["price_usd"]),
            source=row["source"],
            updated_at=row["updated_at"],
        )
        for row in conn.execute(
            "SELECT symbol, price_usd, source, updated_at FROM quote_cache ORDER BY symbol"
        )
    ]


def export_csv(conn: sqlite3.Connection, export_type: str = "all") -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    if export_type in ("all", "runs"):
        writer.writerow(
            [
                "run_id",
                "run_at",
                "automation_name",
                "run_type",
                "status",
                "mode",
                "strategy_version",
                "plan_version",
                "market_summary",
                "cursor_run_id",
                "buying_power",
                "created_at",
            ]
        )
        for row in conn.execute(
            """
            SELECT id, run_at, automation_name, run_type, status, mode, strategy_version, plan_version,
                   market_summary, cursor_run_id, buying_power, created_at
            FROM automation_runs
            ORDER BY id DESC
            """
        ):
            writer.writerow([row[c] for c in row.keys()])

    if export_type == "all":
        writer.writerow([])

    if export_type in ("all", "decisions"):
        writer.writerow(
            [
                "decision_id",
                "run_id",
                "symbol",
                "action",
                "reason",
                "confidence",
                "technical_score",
                "news_score",
                "risk_score",
                "action_rationale",
                "amount_usd",
                "order_id",
                "mode",
                "created_at",
            ]
        )
        for row in conn.execute(
            """
            SELECT id, run_id, symbol, action, reason, confidence, technical_score,
                   news_score, risk_score, action_rationale, amount_usd, order_id, mode, created_at
            FROM decisions
            ORDER BY id DESC
            """
        ):
            writer.writerow([row[c] for c in row.keys()])

    return buffer.getvalue()


def export_json(conn: sqlite3.Connection, export_type: str = "all") -> str:
    payload: dict = {}
    if export_type in ("all", "runs"):
        payload["runs"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, run_at, automation_name, run_type, status, mode, strategy_version,
                       plan_version, market_summary, cursor_run_id, buying_power, created_at
                FROM automation_runs ORDER BY id DESC
                """
            )
        ]
    if export_type in ("all", "decisions"):
        payload["decisions"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, run_id, symbol, action, reason, confidence, technical_score,
                       news_score, risk_score, action_rationale, amount_usd, order_id, mode, created_at
                FROM decisions ORDER BY id DESC
                """
            )
        ]
    if export_type == "all":
        payload["stats"] = get_dashboard_stats(conn).model_dump()
    return json.dumps(payload, indent=2)


def get_mobile_status(conn: sqlite3.Connection) -> MobileStatusOut:
    from app.alert_state_service import open_alert_count
    from app.budget_service import get_usage_budget
    from app.lane_service import list_lanes
    from app.preflight_service import get_live_preflight
    from app.services import get_simulated_portfolio
    from app.safety import get_active_strategy

    strategy = get_active_strategy(conn)
    live_lane = next(
        (lane for lane in list_lanes(conn) if lane.lane_role == "live" and lane.status == "active"),
        None,
    )
    equity_lane = live_lane.id if live_lane else 1
    portfolio = get_simulated_portfolio(conn, equity_lane)
    last_run = conn.execute(
        "SELECT run_at, status FROM automation_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    preflight = get_live_preflight(conn)
    budget = get_usage_budget(conn)
    return MobileStatusOut(
        strategy_mode=strategy.mode,
        trading_enabled=strategy.trading_enabled,
        kill_switch=strategy.kill_switch,
        total_equity_usd=portfolio.total_equity,
        open_alerts=open_alert_count(conn),
        last_run_at=last_run["run_at"] if last_run else None,
        last_run_status=last_run["status"] if last_run else None,
        preflight_ready=preflight.ready_for_live,
        budget_ok=budget.budget_ok,
        live_lane_id=live_lane.id if live_lane else None,
        live_lane_name=live_lane.name if live_lane else None,
    )
