from fastapi import APIRouter, Depends, HTTPException

from app.auth import ReadKeyDep, WriteKeyDep
from app.database import get_connection
from app.preflight_service import get_live_preflight
from app.plan_service import (
    get_active_agent_plan,
    get_agent_plan_by_version,
    list_agent_plan_versions,
    update_active_agent_plan,
)
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
def automation_plan() -> AgentPlanOut:
    conn = get_connection()
    try:
        return get_active_agent_plan(conn)
    except RuntimeError as exc:
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


@router.get("/context", response_model=AutomationContextOut, dependencies=[ReadKeyDep])
def automation_context() -> AutomationContextOut:
    conn = get_connection()
    try:
        return get_automation_context(conn)
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
