from fastapi import APIRouter, HTTPException, Query

from app.alert_service import dispatch_reconciliation_alert, maybe_alert_after_order_import
from app.auth import WriteKeyDep
from app.database import get_connection
from app.dashboard_service import import_cursor_usage
from app.integration_service import import_quotes, import_robinhood_orders, ingest_price_alert
from app.schemas import (
    AlertDispatchResponse,
    CursorUsageImportRequest,
    CursorUsageImportResponse,
    PortfolioResetResponse,
    PriceAlertWebhook,
    QuoteImportRequest,
    QuoteImportResponse,
    RobinhoodOrderImportRequest,
    RobinhoodOrderImportResponse,
    WebhookIngestResponse,
)
from app.services import reset_simulated_portfolio

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/cursor-usage/import", response_model=CursorUsageImportResponse, dependencies=[WriteKeyDep])
def cursor_usage_import(payload: CursorUsageImportRequest) -> CursorUsageImportResponse:
    conn = get_connection()
    try:
        inserted, linked = import_cursor_usage(conn, payload)
        conn.commit()
        return CursorUsageImportResponse(inserted=inserted, linked=linked)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/portfolio/reset", response_model=PortfolioResetResponse, dependencies=[WriteKeyDep])
def portfolio_reset() -> PortfolioResetResponse:
    conn = get_connection()
    try:
        positions_cleared, portfolio = reset_simulated_portfolio(conn)
        conn.commit()
        return PortfolioResetResponse(
            cash_usd=portfolio.cash_usd,
            positions_cleared=positions_cleared,
            message="Simulated portfolio reset to configured starting cash.",
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/quotes/import", response_model=QuoteImportResponse, dependencies=[WriteKeyDep])
def quotes_import(payload: QuoteImportRequest) -> QuoteImportResponse:
    conn = get_connection()
    try:
        upserted = import_quotes(conn, payload)
        conn.commit()
        return QuoteImportResponse(upserted=upserted)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post(
    "/robinhood-orders/import",
    response_model=RobinhoodOrderImportResponse,
    dependencies=[WriteKeyDep],
)
def robinhood_orders_import(payload: RobinhoodOrderImportRequest) -> RobinhoodOrderImportResponse:
    conn = get_connection()
    try:
        upserted, linked = import_robinhood_orders(conn, payload)
        alert_result = maybe_alert_after_order_import(conn)
        conn.commit()
        response = RobinhoodOrderImportResponse(upserted=upserted, linked=linked)
        if alert_result and alert_result.dispatched:
            return response
        return response
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post(
    "/webhooks/price-alert",
    response_model=WebhookIngestResponse,
    dependencies=[WriteKeyDep],
)
def webhook_price_alert(payload: PriceAlertWebhook) -> WebhookIngestResponse:
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    conn = get_connection()
    try:
        result = ingest_price_alert(conn, payload)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post(
    "/alerts/reconciliation-check",
    response_model=AlertDispatchResponse,
    dependencies=[WriteKeyDep],
)
def reconciliation_alert_check(force: bool = Query(default=False)) -> AlertDispatchResponse:
    conn = get_connection()
    try:
        result = dispatch_reconciliation_alert(conn, force=force)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
