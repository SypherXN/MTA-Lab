from fastapi import APIRouter, HTTPException, Query

from app.alert_service import dispatch_reconciliation_alert, maybe_alert_after_order_import
from app.auth import WriteKeyDep
from app.database import get_connection
from app.dashboard_service import import_cursor_usage
from app.integration_service import import_quotes, import_robinhood_orders, ingest_price_alert
from app.live_promotion_service import approve_live_promotion, request_live_promotion
from app.maintenance_service import run_maintenance
from app.news_service import ingest_news_events
from app.retention_service import run_retention
from app.schemas import (
    AlertDispatchResponse,
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
    RobinhoodOrderImportRequest,
    RobinhoodOrderImportResponse,
    UsageRelinkOut,
    LaneCreate,
    LaneOut,
    LanePromoteRequest,
    LanePromoteResponse,
    LaneResetResponse,
    LaneUpdate,
    AgentPlanSyncResponse,
    SymbolProposalOut,
    SymbolProposalsImportRequest,
    SymbolProposalsImportResponse,
    SymbolProposalPromoteRequest,
    SymbolProposalPromoteResponse,
    SymbolProposalAutoPromoteRequest,
    WebhookIngestResponse,
)

from app.lane_service import (
    create_lane,
    list_lanes,
    promote_lane_to_live,
    reset_lane_portfolio,
    update_lane,
)
from app.plan_service import sync_agent_plans_from_directory
from app.symbol_proposal_service import (
    auto_promote_pending_proposals,
    dismiss_symbol_proposal,
    import_symbol_proposals,
    list_symbol_proposals,
    promote_symbol_proposals,
)
from app.services import reset_simulated_portfolio
from app.config import settings
from app.usage_relink_service import relink_cursor_usage

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/cursor-usage/import", response_model=CursorUsageImportResponse, dependencies=[WriteKeyDep])
def cursor_usage_import(payload: CursorUsageImportRequest) -> CursorUsageImportResponse:
    conn = get_connection()
    try:
        inserted, linked, skipped, relink = import_cursor_usage(conn, payload)
        conn.commit()
        return CursorUsageImportResponse(
            inserted=inserted,
            linked=linked,
            skipped=skipped,
            relinked=UsageRelinkOut(
                exact_usage_linked=relink.exact_usage_linked,
                fuzzy_usage_linked=relink.fuzzy_usage_linked,
                runs_cursor_run_id_backfilled=relink.runs_cursor_run_id_backfilled,
                scout_runs_created=relink.scout_runs_created,
                remaining_unlinked=relink.remaining_unlinked,
            ),
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/cursor-usage/relink", response_model=UsageRelinkOut, dependencies=[WriteKeyDep])
def cursor_usage_relink() -> UsageRelinkOut:
    conn = get_connection()
    try:
        result = relink_cursor_usage(conn)
        conn.commit()
        return UsageRelinkOut(
            exact_usage_linked=result.exact_usage_linked,
            fuzzy_usage_linked=result.fuzzy_usage_linked,
            runs_cursor_run_id_backfilled=result.runs_cursor_run_id_backfilled,
            scout_runs_created=result.scout_runs_created,
            remaining_unlinked=result.remaining_unlinked,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/portfolio/reset", response_model=PortfolioResetResponse, dependencies=[WriteKeyDep])
def portfolio_reset(lane_id: int | None = None) -> PortfolioResetResponse:
    conn = get_connection()
    try:
        positions_cleared, portfolio = reset_simulated_portfolio(conn, lane_id=lane_id)
        conn.commit()
        return PortfolioResetResponse(
            cash_usd=portfolio.cash_usd,
            positions_cleared=positions_cleared,
            message="Simulated portfolio reset to configured starting cash.",
        )
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/lanes", response_model=list[LaneOut], dependencies=[WriteKeyDep])
def admin_list_lanes(include_archived: bool = False) -> list[LaneOut]:
    conn = get_connection()
    try:
        return list_lanes(conn, include_archived=include_archived)
    finally:
        conn.close()


@router.post("/lanes", response_model=LaneOut, dependencies=[WriteKeyDep])
def admin_create_lane(payload: LaneCreate) -> LaneOut:
    conn = get_connection()
    try:
        lane = create_lane(conn, payload)
        conn.commit()
        return lane
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.patch("/lanes/{lane_id}", response_model=LaneOut, dependencies=[WriteKeyDep])
def admin_update_lane(lane_id: int, payload: LaneUpdate) -> LaneOut:
    conn = get_connection()
    try:
        lane = update_lane(conn, lane_id, payload)
        conn.commit()
        return lane
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/lanes/{lane_id}/reset", response_model=LaneResetResponse, dependencies=[WriteKeyDep])
def admin_reset_lane(lane_id: int) -> LaneResetResponse:
    conn = get_connection()
    try:
        positions_cleared, cash_usd = reset_lane_portfolio(conn, lane_id)
        conn.commit()
        return LaneResetResponse(
            lane_id=lane_id,
            positions_cleared=positions_cleared,
            cash_usd=cash_usd,
            message=f"Lane {lane_id} portfolio reset.",
        )
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post(
    "/lanes/{lane_id}/promote-to-live",
    response_model=LanePromoteResponse,
    dependencies=[WriteKeyDep],
)
def admin_promote_lane(
    lane_id: int,
    payload: LanePromoteRequest | None = None,
) -> LanePromoteResponse:
    conn = get_connection()
    try:
        result = promote_lane_to_live(conn, lane_id, payload=payload)
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


@router.post("/plans/sync-from-repo", response_model=AgentPlanSyncResponse, dependencies=[WriteKeyDep])
def sync_plans_from_repo() -> AgentPlanSyncResponse:
    conn = get_connection()
    try:
        result = sync_agent_plans_from_directory(conn, settings.resolved_plans_dir())
        conn.commit()
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post(
    "/symbol-proposals/import",
    response_model=SymbolProposalsImportResponse,
    dependencies=[WriteKeyDep],
)
def admin_import_symbol_proposals(
    payload: SymbolProposalsImportRequest,
) -> SymbolProposalsImportResponse:
    """Store ticker ideas from a manual scout run (does not change strategy yet)."""
    conn = get_connection()
    try:
        result = import_symbol_proposals(conn, payload)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/symbol-proposals", response_model=list[SymbolProposalOut], dependencies=[WriteKeyDep])
def admin_list_symbol_proposals(
    status: str | None = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
) -> list[SymbolProposalOut]:
    conn = get_connection()
    try:
        return list_symbol_proposals(conn, status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.post(
    "/symbol-proposals/{proposal_id}/dismiss",
    response_model=SymbolProposalOut,
    dependencies=[WriteKeyDep],
)
def admin_dismiss_symbol_proposal(proposal_id: int) -> SymbolProposalOut:
    conn = get_connection()
    try:
        result = dismiss_symbol_proposal(conn, proposal_id)
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
    "/symbol-proposals/promote",
    response_model=SymbolProposalPromoteResponse,
    dependencies=[WriteKeyDep],
)
def admin_promote_symbol_proposals(
    payload: SymbolProposalPromoteRequest,
) -> SymbolProposalPromoteResponse:
    """Add scouted tickers to allowed_symbols + discovery_pool and enable discovery."""
    conn = get_connection()
    try:
        result = promote_symbol_proposals(conn, payload)
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
    "/symbol-proposals/auto-promote",
    response_model=SymbolProposalPromoteResponse,
    dependencies=[WriteKeyDep],
)
def admin_auto_promote_symbol_proposals(
    payload: SymbolProposalAutoPromoteRequest | None = None,
) -> SymbolProposalPromoteResponse:
    """Promote top pending proposals above min_score into the discovery pool."""
    conn = get_connection()
    try:
        result = auto_promote_pending_proposals(conn, payload)
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
