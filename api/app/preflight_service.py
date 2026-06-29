import sqlite3

from app.database import check_database
from app.integration_service import get_reconciliation_summary
from app.safety import get_active_strategy, trading_is_allowed
from app.schemas import PreflightCheckOut, PreflightOut


def _failed_runs_recent(conn: sqlite3.Connection, hours: int = 24) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM automation_runs
        WHERE lower(status) = 'failed'
          AND datetime(run_at) >= datetime('now', ?)
        """,
        (f"-{hours} hours",),
    ).fetchone()
    return int(row["c"])


def _completed_runs_recent(conn: sqlite3.Connection, days: int = 7) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM automation_runs
        WHERE lower(status) = 'completed'
          AND datetime(run_at) >= datetime('now', ?)
        """,
        (f"-{days} days",),
    ).fetchone()
    return int(row["c"])


def _pending_signals(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM market_signals
        WHERE check_needed = 1 AND consumed_at IS NULL
        """
    ).fetchone()
    return int(row["c"])


def get_live_preflight(conn: sqlite3.Connection) -> PreflightOut:
    checks: list[PreflightCheckOut] = []

    db_ok, db_msg = check_database()
    checks.append(
        PreflightCheckOut(
            name="database",
            passed=db_ok,
            message="SQLite reachable" if db_ok else f"Database error: {db_msg}",
        )
    )

    try:
        strategy = get_active_strategy(conn)
        checks.append(
            PreflightCheckOut(
                name="strategy_active",
                passed=True,
                message=f"Active strategy {strategy.version} ({strategy.mode})",
            )
        )
        checks.append(
            PreflightCheckOut(
                name="kill_switch_off",
                passed=not strategy.kill_switch,
                message="Kill switch is off" if not strategy.kill_switch else "Kill switch is ON",
            )
        )
        checks.append(
            PreflightCheckOut(
                name="mode_live",
                passed=strategy.mode == "live",
                message=f"Mode is {strategy.mode}"
                + (" (ready)" if strategy.mode == "live" else " — set mode to live before trading"),
            )
        )
        checks.append(
            PreflightCheckOut(
                name="trading_enabled",
                passed=strategy.trading_enabled,
                message="trading_enabled is true"
                if strategy.trading_enabled
                else "trading_enabled is false — enable after validation",
            )
        )
        trading_ready = trading_is_allowed(strategy)
        checks.append(
            PreflightCheckOut(
                name="trading_allowed",
                passed=trading_ready,
                message="All live trading gates pass"
                if trading_ready
                else "Live trading not allowed under current flags",
            )
        )
    except RuntimeError as exc:
        checks.append(
            PreflightCheckOut(name="strategy_active", passed=False, message=str(exc))
        )

    recon = get_reconciliation_summary(conn)
    recon_clean = recon.unmatched_orders == 0 and recon.unmatched_decisions == 0
    checks.append(
        PreflightCheckOut(
            name="reconciliation_clean",
            passed=recon_clean,
            message="No unmatched orders or decisions"
            if recon_clean
            else (
                f"Unmatched orders: {recon.unmatched_orders}, "
                f"unmatched decisions: {recon.unmatched_decisions}"
            ),
        )
    )

    failed_recent = _failed_runs_recent(conn)
    checks.append(
        PreflightCheckOut(
            name="no_recent_failed_runs",
            passed=failed_recent == 0,
            message="No failed runs in the last 24h"
            if failed_recent == 0
            else f"{failed_recent} failed run(s) in the last 24h",
        )
    )

    completed_recent = _completed_runs_recent(conn)
    checks.append(
        PreflightCheckOut(
            name="recent_successful_run",
            passed=completed_recent > 0,
            message=f"{completed_recent} completed run(s) in the last 7 days"
            if completed_recent > 0
            else "No completed runs in the last 7 days",
        )
    )

    pending = _pending_signals(conn)
    checks.append(
        PreflightCheckOut(
            name="no_pending_signals",
            passed=pending == 0,
            message="No unconsumed market signals"
            if pending == 0
            else f"{pending} pending market signal(s) — run automation to consume",
        )
    )

    critical = {
        "database",
        "strategy_active",
        "kill_switch_off",
        "reconciliation_clean",
        "no_recent_failed_runs",
    }
    ready = all(c.passed for c in checks if c.name in critical)

    return PreflightOut(ready_for_live=ready, checks=checks)
