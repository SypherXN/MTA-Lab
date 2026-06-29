from fastapi import APIRouter, HTTPException, Query

from app.alert_service import dispatch_reconciliation_alert, maybe_alert_after_order_import
from app.auth import WriteKeyDep
from app.database import get_connection
from app.dashboard_service import import_cursor_usage
from app.integration_service import import_quotes, import_robinhood_orders, ingest_price_alert
from app.live_promotion_service import approve_live_promotion, request_live_promotion
from app.maintenance_service import run_maintenance
from app.news_service import ingest_news_events
from app.payload_service import store_compact_payload
from app.retention_service import run_retention
from app.rollup_service import run_rollup_job
from app.schemas import (
    AlertDispatchResponse,
    CompactPayloadOut,
    CompactPayloadStoreRequest,
    CursorUsageImportRequest,
    CursorUsageImportResponse,
    LivePromotionApproveRequest,
    LivePromotionRequestResponse,
    LivePromotionStatusOut,
    MaintenanceRunOut,
    NewsEventImportRequest,
    NewsEventImportResponse,
    PortfolioResetResponse,
    PriceAlertWebhook,
    QuoteImportRequest,
    QuoteImportResponse,
    RetentionRunOut,
    RetentionRunRequest,
    RollupRunOut,
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


@router.post("/news/import", response_model=NewsEventImportResponse, dependencies=[WriteKeyDep])
def news_import(payload: NewsEventImportRequest) -> NewsEventImportResponse:
    if not payload.events:
        raise HTTPException(status_code=400, detail="events must not be empty")
    conn = get_connection()
    try:
        inserted, skipped = ingest_news_events(conn, payload.events)
        conn.commit()
        return NewsEventImportResponse(inserted=inserted, skipped=skipped)
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


@router.post(
    "/live-promotion/request",
    response_model=LivePromotionRequestResponse,
    dependencies=[WriteKeyDep],
)
def live_promotion_request() -> LivePromotionRequestResponse:
    conn = get_connection()
    try:
        result = request_live_promotion(conn)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post(
    "/live-promotion/approve",
    response_model=LivePromotionStatusOut,
    dependencies=[WriteKeyDep],
)
def live_promotion_approve(payload: LivePromotionApproveRequest) -> LivePromotionStatusOut:
    conn = get_connection()
    try:
        result = approve_live_promotion(conn, payload)
        conn.commit()
        return result
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post(
    "/retention/run",
    response_model=RetentionRunOut,
    dependencies=[WriteKeyDep],
)
def retention_run(payload: RetentionRunRequest | None = None) -> RetentionRunOut:
    body = payload or RetentionRunRequest()
    conn = get_connection()
    try:
        result = run_retention(
            conn,
            keep_runs_days=body.keep_runs_days,
            keep_snapshots_days=body.keep_snapshots_days,
            keep_usage_days=body.keep_usage_days,
        )
        conn.commit()
        return result
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post(
    "/maintenance/run",
    response_model=MaintenanceRunOut,
    dependencies=[WriteKeyDep],
)
def maintenance_run(
    vacuum: bool = Query(default=True),
    analyze: bool = Query(default=True),
) -> MaintenanceRunOut:
    conn = get_connection()
    try:
        result = run_maintenance(conn, vacuum=vacuum, analyze=analyze)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/rollups/run", response_model=RollupRunOut, dependencies=[WriteKeyDep])
def rollups_run(days: int = Query(default=30, ge=1, le=365)) -> RollupRunOut:
    conn = get_connection()
    try:
        result = run_rollup_job(conn, days=days)
        conn.commit()
        return result
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.post(
    "/payloads/store",
    response_model=CompactPayloadOut,
    dependencies=[WriteKeyDep],
)
def compact_payload_store(payload: CompactPayloadStoreRequest) -> CompactPayloadOut:
    conn = get_connection()
    try:
        result = store_compact_payload(
            conn,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            payload=payload.payload,
            summary=payload.summary,
        )
        conn.commit()
        return result
    finally:
        conn.close()
