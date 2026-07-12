from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.lane_compare_service import compare_lanes
from app.lane_service import list_lanes
from app.live_history_service import get_live_trading_history
from app.compare_service import compare_strategy_versions
from app.alert_state_service import list_alerts, update_alert_status
from app.auth import DashboardStrategyWriteDep, ReadKeyDep
from app.database import get_connection
from app.dashboard_service import (
    export_csv,
    export_json,
    get_dashboard_decisions,
    get_dashboard_portfolio_snapshot_summary,
    get_dashboard_portfolio_snapshots,
    get_dashboard_runs,
    get_dashboard_stats,
    get_dashboard_usage,
    get_mobile_status,
    get_quote_cache,
)
from app.freshness_service import evaluate_freshness
from app.schemas import (
    AlertOut,
    AlertStatusUpdate,
    CursorUsageOut,
    DashboardStatsOut,
    DataFreshnessChecksOut,
    DecisionSummaryOut,
    MobileStatusOut,
    PortfolioSnapshotOut,
    PortfolioSnapshotSummaryOut,
    QuoteOut,
    ReconciliationSummaryOut,
    RobinhoodOrderOut,
    RunSummaryOut,
    LaneCompareOut,
    LaneOut,
    LiveTradingHistoryOut,
    StrategyCompareOut,
    StrategyOut,
    StrategyUpdate,
    TimelineEventOut,
    UsageSummaryOut,
)
from app.integration_service import get_reconciliation_summary, get_robinhood_orders
from app.services import get_simulated_portfolio, update_active_strategy
from app.timeline_service import get_activity_timeline
from app.usage_summary_service import get_usage_summary

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[ReadKeyDep],
)


@router.get("/runs", response_model=list[RunSummaryOut])
def dashboard_runs(limit: int = Query(default=50, ge=1, le=200)) -> list[RunSummaryOut]:
    conn = get_connection()
    try:
        return get_dashboard_runs(conn, limit=limit)
    finally:
        conn.close()


@router.get("/decisions", response_model=list[DecisionSummaryOut])
def dashboard_decisions(
    limit: int = Query(default=100, ge=1, le=500),
    symbol: str | None = None,
) -> list[DecisionSummaryOut]:
    conn = get_connection()
    try:
        return get_dashboard_decisions(conn, limit=limit, symbol=symbol)
    finally:
        conn.close()


@router.get("/stats", response_model=DashboardStatsOut)
def dashboard_stats() -> DashboardStatsOut:
    conn = get_connection()
    try:
        return get_dashboard_stats(conn)
    finally:
        conn.close()


@router.get("/portfolio/snapshots", response_model=list[PortfolioSnapshotOut])
def dashboard_portfolio_snapshots(
    limit: int = Query(default=100, ge=1, le=500),
    since: str | None = None,
    until: str | None = None,
    run_id: int | None = None,
    lane_id: int | None = None,
) -> list[PortfolioSnapshotOut]:
    conn = get_connection()
    try:
        rows = get_dashboard_portfolio_snapshots(
            conn, limit=limit, since=since, until=until, run_id=run_id, lane_id=lane_id
        )
        return list(reversed(rows))
    finally:
        conn.close()


@router.get("/portfolio/snapshots/summary", response_model=PortfolioSnapshotSummaryOut)
def dashboard_portfolio_snapshot_summary(lane_id: int | None = None) -> PortfolioSnapshotSummaryOut:
    conn = get_connection()
    try:
        summary = get_dashboard_portfolio_snapshot_summary(conn, lane_id=lane_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="No portfolio snapshots recorded yet")
        return summary
    finally:
        conn.close()


@router.get("/freshness/check", response_model=DataFreshnessChecksOut)
def dashboard_freshness_check() -> DataFreshnessChecksOut:
    conn = get_connection()
    try:
        return evaluate_freshness(conn)
    finally:
        conn.close()


@router.get("/timeline", response_model=list[TimelineEventOut])
def dashboard_timeline(limit: int = Query(default=100, ge=1, le=300)) -> list[TimelineEventOut]:
    conn = get_connection()
    try:
        return get_activity_timeline(conn, limit=limit)
    finally:
        conn.close()


@router.get("/portfolio")
def dashboard_portfolio(lane_id: int | None = None):
    conn = get_connection()
    try:
        return get_simulated_portfolio(conn, lane_id, require_active=False)
    finally:
        conn.close()


@router.get("/usage/summary", response_model=UsageSummaryOut)
def dashboard_usage_summary() -> UsageSummaryOut:
    conn = get_connection()
    try:
        return get_usage_summary(conn)
    finally:
        conn.close()


@router.get("/usage", response_model=list[CursorUsageOut])
def dashboard_usage(limit: int = Query(default=50, ge=1, le=200)) -> list[CursorUsageOut]:
    conn = get_connection()
    try:
        return get_dashboard_usage(conn, limit=limit)
    finally:
        conn.close()


@router.get("/orders", response_model=list[RobinhoodOrderOut])
def dashboard_orders(limit: int = Query(default=50, ge=1, le=200)) -> list[RobinhoodOrderOut]:
    conn = get_connection()
    try:
        return get_robinhood_orders(conn, limit=limit)
    finally:
        conn.close()


@router.get("/reconciliation", response_model=ReconciliationSummaryOut)
def dashboard_reconciliation() -> ReconciliationSummaryOut:
    conn = get_connection()
    try:
        return get_reconciliation_summary(conn)
    finally:
        conn.close()


@router.get("/quotes", response_model=list[QuoteOut])
def dashboard_quotes() -> list[QuoteOut]:
    conn = get_connection()
    try:
        return get_quote_cache(conn)
    finally:
        conn.close()


@router.patch("/strategy", response_model=StrategyOut, dependencies=[DashboardStrategyWriteDep])
def dashboard_strategy_update(payload: StrategyUpdate) -> StrategyOut:
    conn = get_connection()
    try:
        result = update_active_strategy(conn, payload)
        conn.commit()
        return result
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.get("/export")
def dashboard_export(
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    type: str = Query(default="all", pattern="^(all|runs|decisions)$"),
) -> Response:
    conn = get_connection()
    try:
        if format == "json":
            content = export_json(conn, export_type=type)
            return Response(
                content=content,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="mta-lab-{type}.json"'},
            )
        content = export_csv(conn, export_type=type)
        filename = f"mta-lab-{type}.csv"
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        conn.close()


@router.get("/alerts", response_model=list[AlertOut])
def dashboard_alerts(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AlertOut]:
    conn = get_connection()
    try:
        return list_alerts(conn, status=status, limit=limit)
    finally:
        conn.close()


@router.patch("/alerts/{alert_id}", response_model=AlertOut, dependencies=[DashboardStrategyWriteDep])
def dashboard_alert_update(alert_id: int, payload: AlertStatusUpdate) -> AlertOut:
    conn = get_connection()
    try:
        result = update_alert_status(conn, alert_id, payload)
        conn.commit()
        return result
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.get("/strategy/compare", response_model=StrategyCompareOut)
def dashboard_strategy_compare(since: str | None = None) -> StrategyCompareOut:
    conn = get_connection()
    try:
        return compare_strategy_versions(conn, since=since)
    finally:
        conn.close()


@router.get("/lanes", response_model=list[LaneOut])
def dashboard_lanes() -> list[LaneOut]:
    conn = get_connection()
    try:
        return list_lanes(conn)
    finally:
        conn.close()


@router.get("/lanes/compare", response_model=LaneCompareOut)
def dashboard_lanes_compare(
    lane_ids: str | None = None,
    since: str | None = None,
) -> LaneCompareOut:
    conn = get_connection()
    try:
        parsed_ids = None
        if lane_ids:
            parsed_ids = [int(part.strip()) for part in lane_ids.split(",") if part.strip()]
        return compare_lanes(conn, lane_ids=parsed_ids, since=since)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.get("/lanes/live-history", response_model=LiveTradingHistoryOut)
def dashboard_live_trading_history() -> LiveTradingHistoryOut:
    conn = get_connection()
    try:
        return get_live_trading_history(conn)
    finally:
        conn.close()


@router.get("/status/mobile", response_model=MobileStatusOut)
def dashboard_mobile_status() -> MobileStatusOut:
    conn = get_connection()
    try:
        return get_mobile_status(conn)
    finally:
        conn.close()
