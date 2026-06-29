import json
from datetime import datetime, timezone

import sqlite3

from app.decision_utils import DECISION_SELECT_COLUMNS, decision_detail_from_row, decision_summary_from_row
from app.integration_service import (
    consume_pending_market_signals,
    get_pending_market_signals,
    mark_position_with_quotes,
    upsert_quotes,
    _get_quote_map,
)
from app.intervention_service import evaluate_intervention
from app.budget_service import evaluate_run_budget, get_usage_budget
from app.freshness_service import evaluate_freshness, touch_data_source
from app.market_input_service import get_market_input_bundle
from app.memory_service import update_symbol_memory_for_decision
from app.news_service import get_recent_news_for_watchlist
from app.plan_service import get_active_plan_version
from app.run_constants import DEFAULT_RUN_TYPE, VALID_RUN_TYPES
from app.run_utils import RUN_SUMMARY_SELECT, run_summary_from_row
from app.snapshot_service import record_portfolio_snapshot
from app.config import settings
from app.schemas import (
    AutomationContextOut,
    ManualNoteCreate,
    ManualNoteOut,
    RunCreate,
    RunCreateResponse,
    RunDetailOut,
    RunSummaryOut,
    SimulatedPortfolioOut,
    SimulatedPositionOut,
    StrategyOut,
    StrategyRules,
    StrategyUpdate,
    UsageMetadata,
)
from app.safety import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    TRADE_ACTIONS,
    VALID_RUN_STATUSES,
    build_safety_snapshot,
    get_active_strategy,
    get_active_symbol_cooldowns,
    trading_is_allowed,
    validate_run_decisions,
)

SIMULATED_BUY_ACTIONS = {"simulated_buy", "paper_buy"}
SIMULATED_SELL_ACTIONS = {"simulated_sell", "paper_sell"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_simulated_portfolio(conn: sqlite3.Connection) -> SimulatedPortfolioOut:
    cash_row = conn.execute("SELECT cash_usd FROM simulated_cash WHERE id = 1").fetchone()
    cash = float(cash_row["cash_usd"]) if cash_row else 0.0
    quote_map = _get_quote_map(conn)

    positions = []
    position_value = 0.0
    total_unrealized_pnl = 0.0
    has_marked_prices = False

    for row in conn.execute(
        "SELECT symbol, quantity, avg_cost FROM simulated_positions ORDER BY symbol"
    ):
        qty = float(row["quantity"])
        avg = float(row["avg_cost"])
        symbol = row["symbol"]
        market_value, last_price, cost_basis, unrealized_pnl = mark_position_with_quotes(
            symbol, qty, avg, quote_map
        )
        position_value += market_value
        if unrealized_pnl is not None:
            has_marked_prices = True
            total_unrealized_pnl += unrealized_pnl
        positions.append(
            SimulatedPositionOut(
                symbol=symbol,
                quantity=qty,
                avg_cost=avg,
                last_price=last_price,
                market_value=market_value,
                cost_basis=cost_basis,
                unrealized_pnl=unrealized_pnl,
            )
        )

    return SimulatedPortfolioOut(
        cash_usd=cash,
        positions=positions,
        total_equity=cash + position_value,
        total_unrealized_pnl=total_unrealized_pnl if has_marked_prices else None,
    )


def get_automation_context(conn: sqlite3.Connection) -> AutomationContextOut:
    strategy = get_active_strategy(conn)

    notes = [
        ManualNoteOut(id=row["id"], content=row["content"], created_at=row["created_at"])
        for row in conn.execute(
            """
            SELECT id, content, created_at
            FROM manual_notes
            WHERE active = 1
            ORDER BY id DESC
            LIMIT 10
            """
        )
    ]

    recent_runs = [
        run_summary_from_row(row)
        for row in conn.execute(
            f"""
            SELECT {RUN_SUMMARY_SELECT}
            FROM automation_runs
            ORDER BY id DESC
            LIMIT 10
            """
        )
    ]

    recent_decisions = [
        decision_summary_from_row(row)
        for row in conn.execute(
            f"""
            SELECT {DECISION_SELECT_COLUMNS}
            FROM decisions
            ORDER BY id DESC
            LIMIT 50
            """
        )
    ]

    market_signals = get_pending_market_signals(conn)
    freshness = evaluate_freshness(conn)
    watchlist = strategy.rules.watchlist or strategy.rules.allowed_symbols
    recent_news = get_recent_news_for_watchlist(conn, watchlist, limit=15)
    market_inputs = get_market_input_bundle(conn)
    intervention = evaluate_intervention(conn)

    return AutomationContextOut(
        strategy=strategy,
        manual_notes=notes,
        recent_runs=recent_runs,
        recent_decisions=recent_decisions,
        simulated_portfolio=get_simulated_portfolio(conn),
        safety=build_safety_snapshot(conn, strategy),
        cooldowns=get_active_symbol_cooldowns(conn, strategy.rules.symbol_cooldown_hours),
        check_needed=len(market_signals) > 0,
        market_signals=market_signals,
        valid_run_types=sorted(VALID_RUN_TYPES),
        data_freshness=freshness.sources,
        freshness_checks=freshness,
        recent_news=recent_news,
        market_input_bundle=market_inputs,
        intervention_status=intervention,
        usage_budget=get_usage_budget(conn),
    )


def _apply_simulated_trade(
    conn: sqlite3.Connection,
    symbol: str,
    action: str,
    amount_usd: float | None,
    fill_price: float | None,
) -> None:
    if amount_usd is None or amount_usd <= 0:
        return

    price = fill_price
    if price is None or price <= 0:
        price = amount_usd

    quantity = amount_usd / price
    symbol = symbol.upper()
    action = action.lower()

    conn.execute(
        """
        INSERT INTO quote_cache (symbol, price_usd, source, updated_at)
        VALUES (?, ?, 'simulated_fill', ?)
        ON CONFLICT(symbol) DO UPDATE SET
            price_usd = excluded.price_usd,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (symbol, price, _iso_now()),
    )

    cash_row = conn.execute("SELECT cash_usd FROM simulated_cash WHERE id = 1").fetchone()
    cash = float(cash_row["cash_usd"])

    pos = conn.execute(
        "SELECT id, quantity, avg_cost FROM simulated_positions WHERE symbol = ?",
        (symbol,),
    ).fetchone()

    if action in SIMULATED_BUY_ACTIONS:
        if cash < amount_usd:
            raise ValueError(f"Insufficient simulated cash for {symbol}")
        new_cash = cash - amount_usd
        if pos is None:
            conn.execute(
                """
                INSERT INTO simulated_positions (symbol, quantity, avg_cost, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (symbol, quantity, price, _iso_now()),
            )
        else:
            old_qty = float(pos["quantity"])
            old_avg = float(pos["avg_cost"])
            new_qty = old_qty + quantity
            new_avg = ((old_qty * old_avg) + (quantity * price)) / new_qty
            conn.execute(
                """
                UPDATE simulated_positions
                SET quantity = ?, avg_cost = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_qty, new_avg, _iso_now(), pos["id"]),
            )
        conn.execute(
            "UPDATE simulated_cash SET cash_usd = ?, updated_at = ? WHERE id = 1",
            (new_cash, _iso_now()),
        )
    elif action in SIMULATED_SELL_ACTIONS:
        if pos is None:
            raise ValueError(f"No simulated position to sell for {symbol}")
        old_qty = float(pos["quantity"])
        if quantity > old_qty:
            quantity = old_qty
        proceeds = quantity * price
        new_qty = old_qty - quantity
        if new_qty <= 0:
            conn.execute("DELETE FROM simulated_positions WHERE id = ?", (pos["id"],))
        else:
            conn.execute(
                """
                UPDATE simulated_positions
                SET quantity = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_qty, _iso_now(), pos["id"]),
            )
        conn.execute(
            "UPDATE simulated_cash SET cash_usd = ?, updated_at = ? WHERE id = 1",
            (cash + proceeds, _iso_now()),
        )


def get_run_by_id(conn: sqlite3.Connection, run_id: int) -> RunDetailOut:
    row = conn.execute(
        f"""
        SELECT {RUN_SUMMARY_SELECT}, errors_json, usage_json, self_critique
        FROM automation_runs
        WHERE id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Run {run_id} not found")

    errors = json.loads(row["errors_json"]) if row["errors_json"] else []
    usage_data = json.loads(row["usage_json"]) if row["usage_json"] else None
    usage = UsageMetadata.model_validate(usage_data) if usage_data else None

    decisions = [
        decision_detail_from_row(d)
        for d in conn.execute(
            f"""
            SELECT {DECISION_SELECT_COLUMNS}
            FROM decisions
            WHERE run_id = ?
            ORDER BY id
            """,
            (run_id,),
        )
    ]

    return RunDetailOut(
        **run_summary_from_row(row).model_dump(),
        errors=errors,
        usage=usage,
        self_critique=row["self_critique"] if "self_critique" in row.keys() else None,
        decisions=decisions,
        audit=_get_run_audit_safe(conn, run_id),
    )


def _get_run_audit_safe(conn: sqlite3.Connection, run_id: int):
    from app.run_audit_service import get_run_audit

    try:
        return get_run_audit(conn, run_id)
    except ValueError:
        return None


def get_run_by_cursor_run_id(conn: sqlite3.Connection, cursor_run_id: str) -> RunDetailOut | None:
    row = conn.execute(
        "SELECT id FROM automation_runs WHERE cursor_run_id = ?",
        (cursor_run_id,),
    ).fetchone()
    if row is None:
        return None
    return get_run_by_id(conn, row["id"])


def build_run_create_response(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    duplicate: bool = False,
    safety_violations: list[str] | None = None,
    budget_check=None,
) -> RunCreateResponse:
    strategy = get_active_strategy(conn)
    return RunCreateResponse(
        run_id=run_id,
        mode=strategy.mode,
        trading_allowed=trading_is_allowed(strategy),
        safety_violations=safety_violations or [],
        simulated_portfolio=get_simulated_portfolio(conn),
        duplicate=duplicate,
        budget_check=budget_check,
    )


def _next_strategy_version(current: str) -> str:
    if len(current) >= 2 and current[0] == "v" and current[1:].isdigit():
        return f"v{int(current[1:]) + 1}"
    return f"{current}.1"


def _strategy_materially_changed(
    strategy: StrategyOut,
    mode: str,
    trading_enabled: bool,
    kill_switch: bool,
    rules: StrategyRules,
) -> bool:
    return (
        mode != strategy.mode
        or trading_enabled != strategy.trading_enabled
        or kill_switch != strategy.kill_switch
        or rules != strategy.rules
    )


def _normalize_run_type(run_type: str | None) -> str:
    normalized = (run_type or DEFAULT_RUN_TYPE).lower().strip()
    if normalized not in VALID_RUN_TYPES:
        allowed = ", ".join(sorted(VALID_RUN_TYPES))
        raise ValueError(f"run_type must be one of: {allowed}")
    return normalized


def _validate_run_payload(payload: RunCreate) -> str:
    status = payload.normalized_status()
    if status not in VALID_RUN_STATUSES:
        raise ValueError("status must be 'completed' or 'failed'")

    if status == RUN_STATUS_FAILED:
        if not payload.errors:
            raise ValueError("Failed runs must include at least one entry in errors[]")
        if any(d.action.lower() in TRADE_ACTIONS for d in payload.decisions):
            raise ValueError("Failed runs cannot include trade decisions")

    if status == RUN_STATUS_COMPLETED and payload.decisions and not (payload.self_critique or "").strip():
        raise ValueError("Completed runs with decisions must include self_critique")

    return status


def reset_simulated_portfolio(conn: sqlite3.Connection) -> tuple[int, SimulatedPortfolioOut]:
    positions_cleared = conn.execute("SELECT COUNT(*) AS c FROM simulated_positions").fetchone()["c"]
    conn.execute("DELETE FROM simulated_positions")
    conn.execute(
        "UPDATE simulated_cash SET cash_usd = ?, updated_at = ? WHERE id = 1",
        (settings.initial_simulated_cash, _iso_now()),
    )
    return int(positions_cleared), get_simulated_portfolio(conn)


def create_run(conn: sqlite3.Connection, payload: RunCreate) -> RunCreateResponse:
    if payload.cursor_run_id:
        existing = get_run_by_cursor_run_id(conn, payload.cursor_run_id)
        if existing is not None:
            return build_run_create_response(conn, existing.id, duplicate=True)

    status = _validate_run_payload(payload)
    run_type = _normalize_run_type(payload.run_type)
    strategy = get_active_strategy(conn)
    plan_version = get_active_plan_version(conn)
    violations = validate_run_decisions(conn, strategy, payload)

    has_trade_actions = any(d.action.lower() in TRADE_ACTIONS for d in payload.decisions)
    if violations and has_trade_actions:
        raise ValueError("; ".join(violations))

    run_at = (payload.run_at or datetime.now(timezone.utc)).isoformat()
    usage_json = payload.usage.model_dump() if payload.usage else None
    budget_check = evaluate_run_budget(
        run_type=run_type,
        cost_usd=payload.usage.cost_usd if payload.usage else None,
        input_tokens=payload.usage.input_tokens if payload.usage else None,
        output_tokens=payload.usage.output_tokens if payload.usage else None,
    )

    try:
        if payload.quotes:
            upsert_quotes(conn, payload.quotes)

        cursor = conn.execute(
            """
            INSERT INTO automation_runs (
                run_at, automation_name, run_type, market_summary, self_critique, status, strategy_version,
                plan_version, mode, buying_power, errors_json, cursor_run_id, usage_json,
                budget_exceeded, expected_budget_usd, actual_cost_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_at,
                payload.automation_name,
                run_type,
                payload.market_summary,
                payload.self_critique,
                status,
                strategy.version,
                plan_version,
                strategy.mode,
                payload.buying_power,
                json.dumps(payload.errors),
                payload.cursor_run_id,
                json.dumps(usage_json) if usage_json else None,
                1 if budget_check.budget_exceeded else 0,
                budget_check.expected_budget_usd,
                budget_check.actual_cost_usd,
            ),
        )
        run_id = cursor.lastrowid

        for decision in payload.decisions:
            conn.execute(
                """
                INSERT INTO decisions (
                    run_id, symbol, action, reason, confidence, technical_score,
                    news_score, risk_score, action_rationale, review_output,
                    order_id, amount_usd, mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    decision.symbol.upper(),
                    decision.action,
                    decision.reason,
                    decision.resolved_confidence(),
                    decision.resolved_technical_score(),
                    decision.resolved_news_score(),
                    decision.resolved_risk_score(),
                    decision.action_rationale,
                    decision.review_output,
                    decision.order_id,
                    decision.amount_usd,
                    strategy.mode,
                ),
            )

            if status != RUN_STATUS_COMPLETED:
                continue

            action = decision.action.lower()
            if action in SIMULATED_BUY_ACTIONS or action in SIMULATED_SELL_ACTIONS:
                _apply_simulated_trade(
                    conn,
                    decision.symbol,
                    action,
                    decision.amount_usd,
                    decision.fill_price,
                )

            update_symbol_memory_for_decision(
                conn,
                run_id=run_id,
                symbol=decision.symbol,
                action=action,
            )

        if payload.usage and payload.usage.cost_usd is not None:
            conn.execute(
                """
                INSERT INTO cursor_usage (
                    run_id, cursor_run_id, model, cost_usd, input_tokens, output_tokens, source
                ) VALUES (?, ?, ?, ?, ?, ?, 'automation_run')
                """,
                (
                    run_id,
                    payload.usage.cursor_run_id or payload.cursor_run_id,
                    payload.usage.model,
                    payload.usage.cost_usd,
                    payload.usage.input_tokens,
                    payload.usage.output_tokens,
                ),
            )

        if status == RUN_STATUS_COMPLETED:
            consume_pending_market_signals(conn)
            portfolio = get_simulated_portfolio(conn)
            record_portfolio_snapshot(
                conn,
                run_id=run_id,
                source="run",
                snapshot_at=run_at,
                cash_usd=portfolio.cash_usd,
                total_equity=portfolio.total_equity,
                unrealized_pnl=portfolio.total_unrealized_pnl,
            )
            touch_data_source(conn, "automation_runs", updated_at=run_at)
            touch_data_source(conn, "portfolio", updated_at=run_at)
            touch_data_source(conn, "symbol_memory", updated_at=_iso_now())
        elif status == RUN_STATUS_FAILED:
            from app.alert_service import dispatch_failed_run_alert

            dispatch_failed_run_alert(conn, run_id=run_id, errors=payload.errors or [])

        if payload.usage and payload.usage.cost_usd:
            budget = get_usage_budget(conn)
            if budget.daily_exceeded or budget.monthly_exceeded:
                from app.alert_service import dispatch_typed_alert

                dispatch_typed_alert(
                    conn,
                    alert_type="budget_exceeded",
                    title="Cursor budget exceeded",
                    message=(
                        f"Daily ${budget.daily_spent_usd:.2f}/{budget.daily_budget_usd:.2f}; "
                        f"Monthly ${budget.monthly_spent_usd:.2f}/{budget.monthly_budget_usd:.2f}"
                    ),
                    run_id=run_id,
                    alert_key=f"budget:{budget.daily_spent_usd}:{budget.monthly_spent_usd}",
                )

        if budget_check.budget_exceeded:
            from app.alert_service import dispatch_typed_alert

            dispatch_typed_alert(
                conn,
                alert_type="budget_exceeded",
                title=f"Run budget exceeded ({run_type})",
                message=budget_check.message,
                run_id=run_id,
                entity_type="run",
                entity_id=str(run_id),
                alert_key=f"run_budget:{run_id}",
                force=True,
            )
    except sqlite3.IntegrityError as exc:
        if payload.cursor_run_id and "cursor_run_id" in str(exc).lower():
            existing = get_run_by_cursor_run_id(conn, payload.cursor_run_id)
            if existing is not None:
                return build_run_create_response(conn, existing.id, duplicate=True)
        raise ValueError("Failed to create run due to a database constraint") from exc
    except Exception:
        raise

    return build_run_create_response(
        conn, run_id, safety_violations=violations, budget_check=budget_check
    )


def update_active_strategy(conn: sqlite3.Connection, payload: StrategyUpdate) -> StrategyOut:
    strategy = get_active_strategy(conn)
    mode = payload.mode if payload.mode is not None else strategy.mode
    trading_enabled = (
        payload.trading_enabled if payload.trading_enabled is not None else strategy.trading_enabled
    )
    kill_switch = payload.kill_switch if payload.kill_switch is not None else strategy.kill_switch
    rules = payload.rules if payload.rules is not None else strategy.rules

    if mode not in {"research", "paper", "live"}:
        raise ValueError("mode must be research, paper, or live")

    version = strategy.version
    if _strategy_materially_changed(strategy, mode, trading_enabled, kill_switch, rules):
        version = _next_strategy_version(strategy.version)

    conn.execute("UPDATE strategies SET is_active = 0 WHERE is_active = 1")
    conn.execute(
        """
        INSERT INTO strategies (version, name, mode, trading_enabled, kill_switch, rules_json, is_active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (
            version,
            strategy.name,
            mode,
            int(trading_enabled),
            int(kill_switch),
            rules.model_dump_json(),
        ),
    )
    return get_active_strategy(conn)


def deactivate_manual_note(conn: sqlite3.Connection, note_id: int) -> ManualNoteOut:
    row = conn.execute(
        "SELECT id, content, created_at FROM manual_notes WHERE id = ?",
        (note_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Note {note_id} not found")

    conn.execute("UPDATE manual_notes SET active = 0 WHERE id = ?", (note_id,))
    return ManualNoteOut(id=row["id"], content=row["content"], created_at=row["created_at"])


def add_manual_note(conn: sqlite3.Connection, payload: ManualNoteCreate) -> ManualNoteOut:
    cursor = conn.execute(
        "INSERT INTO manual_notes (content, active) VALUES (?, 1)",
        (payload.content.strip(),),
    )
    note_id = cursor.lastrowid
    row = conn.execute(
        "SELECT id, content, created_at FROM manual_notes WHERE id = ?",
        (note_id,),
    ).fetchone()
    return ManualNoteOut(id=row["id"], content=row["content"], created_at=row["created_at"])
