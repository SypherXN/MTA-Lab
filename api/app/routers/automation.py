from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import ReadKeyDep, WriteKeyDep
from app.database import get_connection
from app.dashboard_service import (
    get_dashboard_portfolio_snapshot_summary,
    get_dashboard_portfolio_snapshots,
)
from app.freshness_service import evaluate_freshness, get_data_freshness
from app.news_service import list_news_events
from app.news_service import ingest_news_events, list_news_events
from app.preflight_service import get_live_preflight
from app.plan_service import (
    get_active_agent_plan,
    get_agent_plan_by_version,
    list_agent_plan_versions,
    update_active_agent_plan,
)
from app.intervention_service import evaluate_intervention
from app.lane_execution_service import get_lane_turn
from app.live_promotion_service import get_live_promotion_status
from app.market_input_service import get_market_input_bundle
from app.memory_service import get_symbol_memory
from app.schemas import (
    AgentPlanOut,
    AgentPlanSummaryOut,
    AgentPlanUpdate,
    AgentPlanUpdateResponse,
    AutomationContextOut,
    ManualNoteCreate,
    ManualNoteOut,
    ManualNoteUpdate,
    PreflightOut,
    RunCreate,
    RunCreateResponse,
    RunDetailOut,
    StrategyOut,
    StrategyUpdate,
    SymbolMemoryOut,
    DataFreshnessChecksOut,
    DataSourceFreshnessOut,
    InterventionStatusOut,
    LivePromotionStatusOut,
    LaneTurnOut,
    MarketInputBundleOut,
    NewsEventOut,
    PortfolioSnapshotOut,
    PortfolioSnapshotSummaryOut,
)
from app.services import (
    add_manual_note,
    create_run,
    deactivate_manual_note,
    get_automation_context,
    get_run_by_id,
    update_active_strategy,
)

router = APIRouter(prefix="/api/automation", tags=["automation"])


@router.get("/plan", response_model=AgentPlanOut, dependencies=[ReadKeyDep])
def automation_plan(lane_id: int | None = None) -> AgentPlanOut:
    conn = get_connection()
    try:
        if lane_id is None:
            return get_active_agent_plan(conn)
        from app.lane_service import get_lane

        lane = get_lane(conn, lane_id)
        return get_agent_plan_by_version(conn, lane.plan_version)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        conn.close()


@router.get("/plans", response_model=list[AgentPlanSummaryOut], dependencies=[ReadKeyDep])
def automation_plan_history(limit: int = 50) -> list[AgentPlanSummaryOut]:
    conn = get_connection()
    try:
        return list_agent_plan_versions(conn, limit=min(limit, 200))
    finally:
        conn.close()


@router.get("/plans/{version}", response_model=AgentPlanOut, dependencies=[ReadKeyDep])
def automation_plan_version(version: str) -> AgentPlanOut:
    conn = get_connection()
    try:
        return get_agent_plan_by_version(conn, version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        conn.close()


@router.patch("/plan", response_model=AgentPlanUpdateResponse, dependencies=[WriteKeyDep])
def automation_plan_update(payload: AgentPlanUpdate) -> AgentPlanUpdateResponse:
    conn = get_connection()
    try:
        result = update_active_agent_plan(conn, payload)
        conn.commit()
        return result
    except RuntimeError as exc:
        conn.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/symbols/{symbol}/memory", response_model=SymbolMemoryOut, dependencies=[ReadKeyDep])
def automation_symbol_memory(symbol: str, lane_id: int | None = None) -> SymbolMemoryOut:
    conn = get_connection()
    try:
        return get_symbol_memory(conn, symbol, lane_id=lane_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.get("/portfolio/snapshots", response_model=list[PortfolioSnapshotOut], dependencies=[ReadKeyDep])
def automation_portfolio_snapshots(
    limit: int = Query(default=100, ge=1, le=500),
    since: str | None = None,
    until: str | None = None,
    run_id: int | None = None,
    lane_id: int | None = None,
) -> list[PortfolioSnapshotOut]:
    conn = get_connection()
    try:
        return get_dashboard_portfolio_snapshots(
            conn, limit=limit, since=since, until=until, run_id=run_id, lane_id=lane_id
        )
    finally:
        conn.close()


@router.get("/portfolio/snapshots/summary", response_model=PortfolioSnapshotSummaryOut, dependencies=[ReadKeyDep])
def automation_portfolio_snapshot_summary(lane_id: int | None = None) -> PortfolioSnapshotSummaryOut:
    conn = get_connection()
    try:
        summary = get_dashboard_portfolio_snapshot_summary(conn, lane_id=lane_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="No portfolio snapshots recorded yet")
        return summary
    finally:
        conn.close()


@router.get(
    "/freshness/check",
    response_model=DataFreshnessChecksOut,
    dependencies=[ReadKeyDep],
)
def automation_freshness_check() -> DataFreshnessChecksOut:
    conn = get_connection()
    try:
        return evaluate_freshness(conn)
    finally:
        conn.close()


@router.get(
    "/freshness",
    response_model=list[DataSourceFreshnessOut],
    dependencies=[ReadKeyDep],
)
def automation_freshness() -> list[DataSourceFreshnessOut]:
    conn = get_connection()
    try:
        return get_data_freshness(conn)
    finally:
        conn.close()


@router.get(
    "/intervention/check",
    response_model=InterventionStatusOut,
    dependencies=[ReadKeyDep],
)
def automation_intervention_check() -> InterventionStatusOut:
    conn = get_connection()
    try:
        return evaluate_intervention(conn)
    finally:
        conn.close()


@router.get(
    "/market-inputs",
    response_model=MarketInputBundleOut,
    dependencies=[ReadKeyDep],
)
def automation_market_inputs() -> MarketInputBundleOut:
    conn = get_connection()
    try:
        return get_market_input_bundle(conn)
    finally:
        conn.close()


@router.get(
    "/news",
    response_model=list[NewsEventOut],
    dependencies=[ReadKeyDep],
)
def automation_news(
    symbol: str | None = None,
    since: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[NewsEventOut]:
    conn = get_connection()
    try:
        return list_news_events(conn, symbol=symbol, since=since, limit=limit)
    finally:
        conn.close()


@router.get("/context", response_model=AutomationContextOut, dependencies=[ReadKeyDep])
def automation_context(lane_id: int | None = None) -> AutomationContextOut:
    conn = get_connection()
    try:
        result = get_automation_context(conn, lane_id=lane_id)
        conn.commit()
        return result
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.get("/lanes/turn", response_model=LaneTurnOut, dependencies=[ReadKeyDep])
def automation_lane_turn(lane_id: int) -> LaneTurnOut:
    conn = get_connection()
    try:
        result = get_lane_turn(conn, lane_id, acquire=True)
        conn.commit()
        return result
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.get("/preflight", response_model=PreflightOut, dependencies=[ReadKeyDep])
def automation_preflight() -> PreflightOut:
    conn = get_connection()
    try:
        return get_live_preflight(conn)
    finally:
        conn.close()


@router.get("/runs/{run_id}", response_model=RunDetailOut, dependencies=[ReadKeyDep])
def automation_run_detail(run_id: int) -> RunDetailOut:
    conn = get_connection()
    try:
        return get_run_by_id(conn, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        conn.close()


@router.get("/live-promotion/status", response_model=LivePromotionStatusOut, dependencies=[ReadKeyDep])
def automation_live_promotion_status() -> LivePromotionStatusOut:
    conn = get_connection()
    try:
        return get_live_promotion_status(conn)
    finally:
        conn.close()


@router.post("/runs", response_model=RunCreateResponse, dependencies=[WriteKeyDep])
def automation_runs(payload: RunCreate) -> RunCreateResponse:
    conn = get_connection()
    try:
        result = create_run(conn, payload)
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


@router.patch("/strategy", response_model=StrategyOut, dependencies=[WriteKeyDep])
def automation_strategy_update(payload: StrategyUpdate) -> StrategyOut:
    conn = get_connection()
    try:
        result = update_active_strategy(conn, payload)
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


@router.patch("/notes/{note_id}", response_model=ManualNoteOut, dependencies=[WriteKeyDep])
def automation_notes_deactivate(note_id: int, payload: ManualNoteUpdate) -> ManualNoteOut:
    conn = get_connection()
    try:
        if payload.active:
            raise HTTPException(status_code=400, detail="Only deactivation (active=false) is supported")
        result = deactivate_manual_note(conn, note_id)
        conn.commit()
        return result
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/notes", response_model=ManualNoteOut, dependencies=[WriteKeyDep])
def automation_notes_create(payload: ManualNoteCreate) -> ManualNoteOut:
    conn = get_connection()
    try:
        if not payload.content.strip():
            raise HTTPException(status_code=400, detail="Note content cannot be empty")
        result = add_manual_note(conn, payload)
        conn.commit()
        return result
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
