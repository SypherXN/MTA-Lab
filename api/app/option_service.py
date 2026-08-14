"""Paper listed-options book: long debit calls/puts and cash-secured shorts.

Live Robinhood option orders are never placed here. This module only updates
simulated cash / option lots when a run logs simulated_option_* actions.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import sqlite3

from app.schemas import DecisionIn, SimulatedPositionOut, StrategyOut

OPTION_MULTIPLIER = 100
OPTION_QUOTE_PREFIX = "OPT:"

SIMULATED_OPTION_BUY = "simulated_option_buy"
SIMULATED_OPTION_SELL = "simulated_option_sell"
SIMULATED_OPTION_WRITE = "simulated_option_write"
SIMULATED_OPTION_COVER = "simulated_option_cover"

SIMULATED_OPTION_OPEN_ACTIONS = {SIMULATED_OPTION_BUY, SIMULATED_OPTION_WRITE}
SIMULATED_OPTION_CLOSE_ACTIONS = {SIMULATED_OPTION_SELL, SIMULATED_OPTION_COVER}
SIMULATED_OPTION_ACTIONS = SIMULATED_OPTION_OPEN_ACTIONS | SIMULATED_OPTION_CLOSE_ACTIONS

_EXPIRY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def format_strike(strike: float) -> str:
    text = f"{float(strike):.8f}".rstrip("0").rstrip(".")
    return text or "0"


def normalize_right(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw in {"c", "call", "calls"}:
        return "call"
    if raw in {"p", "put", "puts"}:
        return "put"
    raise ValueError("option_right must be call or put")


def option_quote_key(underlying: str, expiry: str, strike: float, right: str) -> str:
    letter = "C" if normalize_right(right) == "call" else "P"
    return f"{OPTION_QUOTE_PREFIX}{underlying.upper()}:{expiry}:{format_strike(strike)}:{letter}"


def option_display_symbol(underlying: str, expiry: str, strike: float, right: str) -> str:
    letter = "C" if normalize_right(right) == "call" else "P"
    return f"{underlying.upper()} {expiry} {format_strike(strike)}{letter}"


def parse_expiry(value: str | None) -> str:
    text = (value or "").strip()
    if not _EXPIRY_RE.match(text):
        raise ValueError("expiry must be YYYY-MM-DD")
    date.fromisoformat(text)
    return text


def contracts_from_decision(decision: DecisionIn) -> float:
    contracts = 1.0 if decision.contracts is None else float(decision.contracts)
    if contracts <= 0:
        raise ValueError("contracts must be positive")
    if abs(contracts - round(contracts)) > 1e-9:
        raise ValueError("contracts must be a whole number")
    return float(int(round(contracts)))


def premium_from_decision(decision: DecisionIn) -> float | None:
    if decision.premium is not None and decision.premium > 0:
        return float(decision.premium)
    if decision.fill_price is not None and decision.fill_price > 0:
        return float(decision.fill_price)
    return None


def option_debit_usd(premium: float, contracts: float) -> float:
    return float(premium) * OPTION_MULTIPLIER * float(contracts)


def option_collateral_usd(strike: float, contracts: float) -> float:
    return float(strike) * OPTION_MULTIPLIER * float(contracts)


def option_open_notional_usd(decision: DecisionIn) -> float:
    """Daily buy-notional: premium debit for longs, strike collateral for CSPs."""
    action = decision.action.lower()
    contracts = contracts_from_decision(decision)
    if action == SIMULATED_OPTION_BUY:
        premium = premium_from_decision(decision) or 0.0
        return option_debit_usd(premium, contracts)
    if action == SIMULATED_OPTION_WRITE:
        right = normalize_right(decision.option_right)
        if right == "put":
            if decision.strike is None or decision.strike <= 0:
                return 0.0
            return option_collateral_usd(decision.strike, contracts)
        return 0.0
    return 0.0


def option_cash_amount_usd(decision: DecisionIn) -> float | None:
    premium = premium_from_decision(decision)
    if premium is None:
        return decision.amount_usd
    try:
        contracts = contracts_from_decision(decision)
    except ValueError:
        return decision.amount_usd
    return option_debit_usd(premium, contracts)


def option_rationale_suffix(decision: DecisionIn) -> str | None:
    try:
        right = normalize_right(decision.option_right)
        expiry = parse_expiry(decision.expiry)
        strike = float(decision.strike or 0)
        contracts = contracts_from_decision(decision)
    except (ValueError, TypeError):
        return None
    if strike <= 0:
        return None
    display = option_display_symbol(decision.symbol, expiry, strike, right)
    premium = premium_from_decision(decision)
    prem = f" @ {premium:g}" if premium else ""
    return f"[option {display} x{int(contracts)}{prem}]"


def reserved_cash_usd(conn: sqlite3.Connection, lane_id: int) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(strike * ? * contracts), 0) AS reserved
        FROM simulated_option_positions
        WHERE lane_id = ? AND side = 'short' AND option_right = 'put'
        """,
        (OPTION_MULTIPLIER, lane_id),
    ).fetchone()
    return float(row["reserved"] if row else 0.0)


def _cash_usd(conn: sqlite3.Connection, lane_id: int) -> float:
    row = conn.execute(
        "SELECT cash_usd FROM simulated_cash WHERE lane_id = ?",
        (lane_id,),
    ).fetchone()
    return float(row["cash_usd"]) if row else 0.0


def available_cash_usd(conn: sqlite3.Connection, lane_id: int) -> float:
    return _cash_usd(conn, lane_id) - reserved_cash_usd(conn, lane_id)


def _set_cash(conn: sqlite3.Connection, lane_id: int, cash: float) -> None:
    conn.execute(
        """
        INSERT INTO simulated_cash (lane_id, cash_usd, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(lane_id) DO UPDATE SET
            cash_usd = excluded.cash_usd,
            updated_at = excluded.updated_at
        """,
        (lane_id, cash, _iso_now()),
    )


def _equity_quantity(conn: sqlite3.Connection, lane_id: int, symbol: str) -> float:
    row = conn.execute(
        """
        SELECT quantity FROM simulated_positions
        WHERE lane_id = ? AND symbol = ?
        """,
        (lane_id, symbol.upper()),
    ).fetchone()
    return float(row["quantity"]) if row else 0.0


def _short_call_contracts(conn: sqlite3.Connection, lane_id: int, underlying: str) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(contracts), 0) AS c
        FROM simulated_option_positions
        WHERE lane_id = ? AND underlying = ? AND side = 'short' AND option_right = 'call'
        """,
        (lane_id, underlying.upper()),
    ).fetchone()
    return float(row["c"] if row else 0.0)


def _get_lot(
    conn: sqlite3.Connection,
    lane_id: int,
    underlying: str,
    right: str,
    strike: float,
    expiry: str,
    side: str,
):
    return conn.execute(
        """
        SELECT id, contracts, avg_premium, last_mark
        FROM simulated_option_positions
        WHERE lane_id = ? AND underlying = ? AND option_right = ? AND strike = ?
          AND expiry = ? AND side = ?
        """,
        (lane_id, underlying.upper(), right, float(strike), expiry, side),
    ).fetchone()


def _upsert_quote(conn: sqlite3.Connection, key: str, premium: float) -> None:
    conn.execute(
        """
        INSERT INTO quote_cache (symbol, price_usd, source, updated_at)
        VALUES (?, ?, 'simulated_fill', ?)
        ON CONFLICT(symbol) DO UPDATE SET
            price_usd = excluded.price_usd,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (key, premium, _iso_now()),
    )


def _intrinsic_premium(right: str, strike: float, spot: float | None) -> float | None:
    if spot is None or spot <= 0:
        return None
    if right == "call":
        return max(0.0, spot - strike)
    return max(0.0, strike - spot)


def _mark_premium(
    row,
    *,
    underlying: str,
    right: str,
    strike: float,
    expiry: str,
    quote_map: dict[str, float],
) -> float:
    key = option_quote_key(underlying, expiry, strike, right)
    display = option_display_symbol(underlying, expiry, strike, right)
    for candidate in (key, display.upper(), display):
        price = quote_map.get(candidate)
        if price is not None and price >= 0:
            return float(price)

    try:
        exp = date.fromisoformat(expiry)
    except ValueError:
        exp = None
    if exp is not None and exp < _today_utc():
        intrinsic = _intrinsic_premium(right, strike, quote_map.get(underlying.upper()))
        if intrinsic is not None:
            return intrinsic

    last_mark = row["last_mark"] if row["last_mark"] is not None else None
    if last_mark is not None and last_mark >= 0:
        return float(last_mark)
    return float(row["avg_premium"])


def option_positions_out(
    conn: sqlite3.Connection,
    lane_id: int,
    quote_map: dict[str, float],
) -> list[SimulatedPositionOut]:
    positions: list[SimulatedPositionOut] = []
    for row in conn.execute(
        """
        SELECT underlying, option_right, strike, expiry, side, contracts, avg_premium, last_mark
        FROM simulated_option_positions
        WHERE lane_id = ?
        ORDER BY underlying, expiry, strike, option_right, side
        """,
        (lane_id,),
    ):
        underlying = row["underlying"]
        right = row["option_right"]
        strike = float(row["strike"])
        expiry = row["expiry"]
        side = row["side"]
        contracts = float(row["contracts"])
        avg = float(row["avg_premium"])
        mark = _mark_premium(
            row,
            underlying=underlying,
            right=right,
            strike=strike,
            expiry=expiry,
            quote_map=quote_map,
        )
        signed = contracts if side == "long" else -contracts
        market_value = mark * OPTION_MULTIPLIER * signed
        cost_basis = avg * OPTION_MULTIPLIER * signed
        reserved = option_collateral_usd(strike, contracts) if side == "short" and right == "put" else None
        positions.append(
            SimulatedPositionOut(
                symbol=option_display_symbol(underlying, expiry, strike, right),
                quantity=signed,
                avg_cost=avg,
                last_price=mark,
                market_value=market_value,
                cost_basis=cost_basis,
                unrealized_pnl=market_value - cost_basis,
                asset_class="option",
                option_right=right,
                strike=strike,
                expiry=expiry,
                side=side,
                contracts=contracts,
                multiplier=OPTION_MULTIPLIER,
                reserved_usd=reserved,
                underlying=underlying,
            )
        )
    return positions


def clear_option_positions(conn: sqlite3.Connection, lane_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM simulated_option_positions WHERE lane_id = ?",
        (lane_id,),
    ).fetchone()
    conn.execute("DELETE FROM simulated_option_positions WHERE lane_id = ?", (lane_id,))
    return int(row["c"] if row else 0)


def validate_option_decision(decision: DecisionIn, strategy: StrategyOut) -> list[str]:
    violations: list[str] = []
    action = decision.action.lower()
    if action not in SIMULATED_OPTION_ACTIONS:
        return violations
    if not strategy.rules.options_enabled:
        violations.append(f"Options are disabled; {action} is not allowed")
        return violations

    try:
        right = normalize_right(decision.option_right)
    except ValueError as exc:
        violations.append(f"{decision.symbol}: {exc}")
        return violations

    try:
        expiry = parse_expiry(decision.expiry)
    except ValueError as exc:
        violations.append(f"{decision.symbol}: {exc}")
        return violations

    if decision.strike is None or decision.strike <= 0:
        violations.append(f"{decision.symbol}: strike must be positive")
        return violations

    try:
        contracts = contracts_from_decision(decision)
    except ValueError as exc:
        violations.append(f"{decision.symbol}: {exc}")
        return violations

    max_contracts = strategy.rules.max_option_contracts
    if contracts > max_contracts:
        violations.append(
            f"{decision.symbol}: contracts {int(contracts)} exceed max_option_contracts ({max_contracts})"
        )

    if action in SIMULATED_OPTION_OPEN_ACTIONS and date.fromisoformat(expiry) < _today_utc():
        violations.append(f"{decision.symbol}: cannot open an option that already expired ({expiry})")

    premium = premium_from_decision(decision)
    if action in SIMULATED_OPTION_OPEN_ACTIONS and (premium is None or premium <= 0):
        violations.append(f"{decision.symbol}: fill_price/premium is required to open an option")

    if action == SIMULATED_OPTION_BUY and premium is not None:
        debit = option_debit_usd(premium, contracts)
        cap = strategy.rules.max_option_debit_usd or strategy.rules.max_order_usd
        if debit > cap:
            violations.append(
                f"{decision.symbol}: option debit {debit:.2f} exceeds max_option_debit_usd ({cap})"
            )

    if action == SIMULATED_OPTION_WRITE and right == "put":
        collateral = option_collateral_usd(decision.strike, contracts)
        if collateral > strategy.rules.max_csp_notional_usd:
            violations.append(
                f"{decision.symbol}: CSP collateral {collateral:.2f} exceeds "
                f"max_csp_notional_usd ({strategy.rules.max_csp_notional_usd})"
            )

    if action == SIMULATED_OPTION_WRITE and right == "call":
        # Naked short calls are unbounded; paper book only allows covered calls.
        pass

    return violations


def apply_option_trade(conn: sqlite3.Connection, lane_id: int, decision: DecisionIn) -> None:
    action = decision.action.lower()
    underlying = decision.symbol.upper()
    right = normalize_right(decision.option_right)
    expiry = parse_expiry(decision.expiry)
    strike = float(decision.strike)
    premium = premium_from_decision(decision)
    if premium is None or premium < 0:
        raise ValueError(f"fill_price/premium is required for {action} on {underlying}")

    if action in SIMULATED_OPTION_CLOSE_ACTIONS:
        side = "long" if action == SIMULATED_OPTION_SELL else "short"
        existing = _get_lot(conn, lane_id, underlying, right, strike, expiry, side)
        if existing is None:
            raise ValueError(f"No {side} option position to close for {underlying}")
        if decision.percent_of_position is not None:
            contracts = float(existing["contracts"]) * float(decision.percent_of_position)
        elif decision.contracts is None:
            contracts = float(existing["contracts"])
        else:
            contracts = contracts_from_decision(decision)
        if contracts <= 0:
            raise ValueError("contracts to close must be positive")
    else:
        contracts = contracts_from_decision(decision)

    key = option_quote_key(underlying, expiry, strike, right)
    _upsert_quote(conn, key, premium)
    debit = option_debit_usd(premium, contracts)

    if action == SIMULATED_OPTION_BUY:
        _open_or_add(
            conn,
            lane_id,
            underlying=underlying,
            right=right,
            strike=strike,
            expiry=expiry,
            side="long",
            contracts=contracts,
            premium=premium,
            cash_delta=-debit,
        )
        return

    if action == SIMULATED_OPTION_WRITE:
        if right == "put":
            collateral = option_collateral_usd(strike, contracts)
            if available_cash_usd(conn, lane_id) + 1e-9 < collateral:
                raise ValueError(
                    f"Insufficient available cash to cash-secure {underlying} "
                    f"{format_strike(strike)}P ({collateral:.2f} required)"
                )
        else:
            shares_needed = (_short_call_contracts(conn, lane_id, underlying) + contracts) * OPTION_MULTIPLIER
            held = _equity_quantity(conn, lane_id, underlying)
            if held + 1e-9 < shares_needed:
                raise ValueError(
                    f"Covered call requires {shares_needed:g} {underlying} shares; paper book has {held:g}"
                )
        _open_or_add(
            conn,
            lane_id,
            underlying=underlying,
            right=right,
            strike=strike,
            expiry=expiry,
            side="short",
            contracts=contracts,
            premium=premium,
            cash_delta=debit,
        )
        return

    if action == SIMULATED_OPTION_SELL:
        _close_lot(
            conn,
            lane_id,
            underlying=underlying,
            right=right,
            strike=strike,
            expiry=expiry,
            side="long",
            contracts=contracts,
            premium=premium,
            cash_delta=debit,
        )
        return

    if action == SIMULATED_OPTION_COVER:
        if _cash_usd(conn, lane_id) + 1e-9 < debit:
            raise ValueError(f"Insufficient simulated cash to buy back {underlying} option")
        _close_lot(
            conn,
            lane_id,
            underlying=underlying,
            right=right,
            strike=strike,
            expiry=expiry,
            side="short",
            contracts=contracts,
            premium=premium,
            cash_delta=-debit,
        )
        return

    raise ValueError(f"Unsupported option action {action}")


def _open_or_add(
    conn: sqlite3.Connection,
    lane_id: int,
    *,
    underlying: str,
    right: str,
    strike: float,
    expiry: str,
    side: str,
    contracts: float,
    premium: float,
    cash_delta: float,
) -> None:
    cash = _cash_usd(conn, lane_id)
    if cash_delta < 0 and available_cash_usd(conn, lane_id) + 1e-9 < abs(cash_delta):
        raise ValueError(f"Insufficient available cash for {underlying} option")
    pos = _get_lot(conn, lane_id, underlying, right, strike, expiry, side)
    if pos is None:
        conn.execute(
            """
            INSERT INTO simulated_option_positions (
                lane_id, underlying, option_right, strike, expiry, side,
                contracts, avg_premium, last_mark, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lane_id,
                underlying,
                right,
                strike,
                expiry,
                side,
                contracts,
                premium,
                premium,
                _iso_now(),
            ),
        )
    else:
        old_qty = float(pos["contracts"])
        old_avg = float(pos["avg_premium"])
        new_qty = old_qty + contracts
        new_avg = ((old_qty * old_avg) + (contracts * premium)) / new_qty
        conn.execute(
            """
            UPDATE simulated_option_positions
            SET contracts = ?, avg_premium = ?, last_mark = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_qty, new_avg, premium, _iso_now(), pos["id"]),
        )
    _set_cash(conn, lane_id, cash + cash_delta)


def _close_lot(
    conn: sqlite3.Connection,
    lane_id: int,
    *,
    underlying: str,
    right: str,
    strike: float,
    expiry: str,
    side: str,
    contracts: float,
    premium: float,
    cash_delta: float,
) -> None:
    pos = _get_lot(conn, lane_id, underlying, right, strike, expiry, side)
    if pos is None:
        raise ValueError(f"No {side} option position to close for {underlying}")
    old_qty = float(pos["contracts"])
    close_qty = min(contracts, old_qty)
    scaled_delta = cash_delta * (close_qty / contracts) if contracts else 0.0
    cash = _cash_usd(conn, lane_id)
    if scaled_delta < 0 and cash + 1e-9 < abs(scaled_delta):
        raise ValueError(f"Insufficient simulated cash to close {underlying} option")
    remaining = old_qty - close_qty
    if remaining <= 1e-9:
        conn.execute("DELETE FROM simulated_option_positions WHERE id = ?", (pos["id"],))
    else:
        conn.execute(
            """
            UPDATE simulated_option_positions
            SET contracts = ?, last_mark = ?, updated_at = ?
            WHERE id = ?
            """,
            (remaining, premium, _iso_now(), pos["id"]),
        )
    _set_cash(conn, lane_id, cash + scaled_delta)
