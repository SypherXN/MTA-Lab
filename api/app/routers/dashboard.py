from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.auth import ReadKeyDep
from app.database import get_connection
from app.dashboard_service import (
    export_csv,
    get_dashboard_decisions,
    get_dashboard_runs,
    get_dashboard_stats,
    get_dashboard_usage,
    get_quote_cache,
)
from app.schemas import (
    CursorUsageOut,
    DashboardStatsOut,
    DecisionSummaryOut,
    QuoteOut,
    ReconciliationSummaryOut,
    RobinhoodOrderOut,
    RunSummaryOut,
)
from app.integration_service import get_reconciliation_summary, get_robinhood_orders
from app.services import get_simulated_portfolio

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


@router.get("/portfolio")
def dashboard_portfolio():
    conn = get_connection()
    try:
        return get_simulated_portfolio(conn)
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


@router.get("/export")
def dashboard_export(
    format: str = Query(default="csv", pattern="^csv$"),
    type: str = Query(default="all", pattern="^(all|runs|decisions)$"),
) -> Response:
    conn = get_connection()
    try:
        content = export_csv(conn, export_type=type)
        filename = f"mta-lab-{type}.csv"
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        conn.close()
