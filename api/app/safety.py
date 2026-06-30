import json
from datetime import datetime, timedelta, timezone

import sqlite3

from app.schemas import DecisionIn, RunCreate, SafetySnapshotOut, StrategyOut, StrategyRules, SymbolCooldownOut

LIVE_ACTIONS = {"buy", "sell", "place_buy", "place_sell"}
SIMULATED_ACTIONS = {"simulated_buy", "simulated_sell", "paper_buy", "paper_sell"}
TRADE_ACTIONS = LIVE_ACTIONS | SIMULATED_ACTIONS
BUY_ACTIONS = {"buy", "place_buy", "simulated_buy", "paper_buy"}
PASSIVE_ACTIONS = {"hold", "skip", "no_action", "review_only", "error"}

RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
VALID_RUN_STATUSES = {RUN_STATUS_COMPLETED, RUN_STATUS_FAILED}


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _parse_db_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _buy_action_placeholders() -> str:
    return ", ".join("?" * len(BUY_ACTIONS))


def get_active_symbol_cooldowns(
    conn: sqlite3.Connection,
    cooldown_hours: float,
    lane_id: int | None = None,
) -> dict[str, SymbolCooldownOut]:
    if cooldown_hours <= 0:
        return {}

    now = datetime.now(timezone.utc)
    cooldowns: dict[str, SymbolCooldownOut] = {}
    buy_actions = tuple(BUY_ACTIONS)

    lane_filter = ""
    params: list = [RUN_STATUS_COMPLETED, *buy_actions]
    if lane_id is not None:
        lane_filter = " AND r.lane_id = ?"
        params.append(lane_id)

    rows = conn.execute(
        f"""
        SELECT d.symbol, d.action, MAX(d.created_at) AS last_trade_at
        FROM decisions d
        JOIN automation_runs r ON r.id = d.run_id
        WHERE lower(r.status) = ?
          AND lower(d.action) IN ({_buy_action_placeholders()})
          {lane_filter}
        GROUP BY d.symbol
        """,
        tuple(params),
    ).fetchall()

    for row in rows:
        last_trade_at = _parse_db_timestamp(row["last_trade_at"])
        blocked_until = last_trade_at + timedelta(hours=cooldown_hours)
        if blocked_until <= now:
            continue

        symbol = row["symbol"].upper()
        action = row["action"].lower()
        cooldowns[symbol] = SymbolCooldownOut(
            blocked_until=blocked_until.isoformat(),
            reason=f"{action} within last {cooldown_hours:g}h",
            last_action=action,
            last_trade_at=last_trade_at.isoformat(),
        )

    return cooldowns


def get_active_strategy(conn: sqlite3.Connection) -> StrategyOut:
    row = conn.execute(
        """
        SELECT version, name, mode, trading_enabled, kill_switch, rules_json
        FROM strategies
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("No active strategy configured")

    rules = StrategyRules.model_validate(json.loads(row["rules_json"]))
    return StrategyOut(
        version=row["version"],
        name=row["name"],
        mode=row["mode"],
        trading_enabled=bool(row["trading_enabled"]),
        kill_switch=bool(row["kill_switch"]),
        rules=rules,
    )


def get_strategy_by_version(conn: sqlite3.Connection, version: str) -> StrategyOut:
    row = conn.execute(
        """
        SELECT version, name, mode, trading_enabled, kill_switch, rules_json
        FROM strategies
        WHERE version = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (version,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Strategy version {version} not found")

    rules = StrategyRules.model_validate(json.loads(row["rules_json"]))
    return StrategyOut(
        version=row["version"],
        name=row["name"],
        mode=row["mode"],
        trading_enabled=bool(row["trading_enabled"]),
        kill_switch=bool(row["kill_switch"]),
        rules=rules,
    )


def trading_is_allowed(strategy: StrategyOut) -> bool:
    return (
        strategy.mode == "live"
        and strategy.trading_enabled
        and not strategy.kill_switch
    )


def get_daily_trade_usage(conn: sqlite3.Connection, lane_id: int | None = None) -> tuple[int, float]:
    lane_filter = ""
    params: list = [_today_utc()]
    if lane_id is not None:
        lane_filter = " AND r.lane_id = ?"
        params.append(lane_id)

    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS trade_count,
            COALESCE(SUM(d.amount_usd), 0) AS notional
        FROM decisions d
        JOIN automation_runs r ON r.id = d.run_id
        WHERE date(r.run_at) = date(?)
          AND lower(d.action) IN (
              'buy', 'sell', 'place_buy', 'place_sell',
              'simulated_buy', 'simulated_sell', 'paper_buy', 'paper_sell'
          )
          {lane_filter}
        """,
        tuple(params),
    ).fetchone()
    return int(row["trade_count"]), float(row["notional"])


def allowed_actions_for_strategy(strategy: StrategyOut) -> list[str]:
    if strategy.kill_switch:
        return sorted(PASSIVE_ACTIONS)

    actions = set(PASSIVE_ACTIONS) | SIMULATED_ACTIONS
    if trading_is_allowed(strategy):
        actions |= LIVE_ACTIONS
    return sorted(actions)


def build_safety_snapshot(
    conn: sqlite3.Connection,
    strategy: StrategyOut,
    lane_id: int | None = None,
) -> SafetySnapshotOut:
    daily_trades_used, daily_notional_used = get_daily_trade_usage(conn, lane_id=lane_id)
    max_trades = strategy.rules.max_daily_trades
    max_notional = strategy.rules.max_daily_notional_usd

    return SafetySnapshotOut(
        mode=strategy.mode,
        trading_enabled=strategy.trading_enabled,
        kill_switch=strategy.kill_switch,
        trading_allowed=trading_is_allowed(strategy),
        require_review_before_place=strategy.rules.require_review_before_place,
        allowed_symbols=strategy.rules.allowed_symbols,
        max_order_usd=strategy.rules.max_order_usd,
        max_daily_trades=max_trades,
        max_daily_notional_usd=max_notional,
        daily_trades_used=daily_trades_used,
        daily_notional_used=daily_notional_used,
        daily_trades_remaining=max(0, max_trades - daily_trades_used),
        daily_notional_remaining=max(0.0, max_notional - daily_notional_used),
        allowed_actions=allowed_actions_for_strategy(strategy),
    )


def validate_run_decisions(
    conn: sqlite3.Connection,
    strategy: StrategyOut,
    payload: RunCreate,
    *,
    lane_id: int | None = None,
    lane_allows_live: bool = False,
) -> list[str]:
    violations: list[str] = []
    action_lower = {d.action.lower() for d in payload.decisions}

    if any(action in LIVE_ACTIONS for action in action_lower):
        if not lane_allows_live:
            violations.append("Live trade actions are blocked for this simulation lane")
        elif strategy.mode != "live":
            violations.append("Live trade actions are blocked while mode is not live")
        if not strategy.trading_enabled:
            violations.append("Live trade actions are blocked while trading_enabled is false")
        if strategy.kill_switch:
            violations.append("Live trade actions are blocked while kill_switch is true")

    daily_trades, daily_notional = get_daily_trade_usage(conn, lane_id=lane_id)
    projected_trades = daily_trades
    projected_notional = daily_notional

    for decision in payload.decisions:
        action = decision.action.lower()
        if action not in TRADE_ACTIONS:
            continue

        if decision.symbol.upper() not in {s.upper() for s in strategy.rules.allowed_symbols}:
            violations.append(f"Symbol {decision.symbol} is not in allowed_symbols")

        if decision.amount_usd is not None and decision.amount_usd > strategy.rules.max_order_usd:
            violations.append(
                f"Decision for {decision.symbol} exceeds max_order_usd ({decision.amount_usd})"
            )

        if action in LIVE_ACTIONS and strategy.rules.require_review_before_place:
            if not decision.review_output:
                violations.append(
                    f"Live action for {decision.symbol} requires review_output when require_review_before_place is true"
                )

        projected_trades += 1
        projected_notional += decision.amount_usd or 0

    if projected_trades > strategy.rules.max_daily_trades:
        violations.append("Run would exceed max_daily_trades")

    if projected_notional > strategy.rules.max_daily_notional_usd:
        violations.append("Run would exceed max_daily_notional_usd")

    active_cooldowns = get_active_symbol_cooldowns(
        conn, strategy.rules.symbol_cooldown_hours, lane_id=lane_id
    )
    for decision in payload.decisions:
        action = decision.action.lower()
        if action not in BUY_ACTIONS:
            continue
        symbol = decision.symbol.upper()
        cooldown = active_cooldowns.get(symbol)
        if cooldown is not None:
            violations.append(
                f"Symbol {symbol} is in buy cooldown until {cooldown.blocked_until}"
            )

    return violations
