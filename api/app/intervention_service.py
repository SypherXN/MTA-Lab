import sqlite3

from app.freshness_service import evaluate_freshness
from app.integration_service import get_reconciliation_summary
from app.preflight_service import get_live_preflight
from app.safety import get_active_strategy
from app.schemas import InterventionStatusOut, InterventionTriggerOut

FAILED_RUN_LOOKBACK = "-24 hours"
FAILED_RUN_THRESHOLD = 2


def evaluate_intervention(conn: sqlite3.Connection) -> InterventionStatusOut:
    strategy = get_active_strategy(conn)
    triggers: list[InterventionTriggerOut] = []

    failed_count = conn.execute(
        """
        SELECT COUNT(*) AS c FROM automation_runs
        WHERE status = 'failed'
          AND datetime(run_at) >= datetime('now', ?)
        """,
        (FAILED_RUN_LOOKBACK,),
    ).fetchone()["c"]
    if failed_count >= FAILED_RUN_THRESHOLD:
        triggers.append(
            InterventionTriggerOut(
                code="repeated_failed_runs",
                severity="critical",
                message=f"{failed_count} failed run(s) in the last 24 hours",
                action="stop_and_alert",
            )
        )

    reconciliation = get_reconciliation_summary(conn)
    if reconciliation.unmatched_orders > 0 or reconciliation.unmatched_decisions > 0:
        triggers.append(
            InterventionTriggerOut(
                code="reconciliation_mismatch",
                severity="high",
                message=(
                    f"{reconciliation.unmatched_orders} unmatched orders, "
                    f"{reconciliation.unmatched_decisions} unmatched decisions"
                ),
                action="manual_review",
            )
        )

    freshness = evaluate_freshness(conn)
    if not freshness.ready_for_analysis:
        triggers.append(
            InterventionTriggerOut(
                code="stale_required_inputs",
                severity="high",
                message="Required data sources are stale or missing",
                action="hold_only",
            )
        )

    if strategy.kill_switch:
        triggers.append(
            InterventionTriggerOut(
                code="kill_switch_active",
                severity="high",
                message="Kill switch is ON — live trading blocked",
                action="hold_only",
            )
        )

    if strategy.mode == "live" and strategy.trading_enabled:
        triggers.append(
            InterventionTriggerOut(
                code="live_trading_enabled",
                severity="high",
                message="Live mode with trading enabled — verify intent before each run",
                action="manual_review",
            )
        )
        preflight = get_live_preflight(conn)
        if not preflight.ready_for_live:
            triggers.append(
                InterventionTriggerOut(
                    code="live_preflight_failed",
                    severity="critical",
                    message="Live preflight checks failed",
                    action="stop_and_alert",
                )
            )

    severities = {t.severity for t in triggers}
    if "critical" in severities:
        recommended = "Stop automation, log failed run, and alert operator."
    elif triggers:
        recommended = "Hold/skip only; do not open new positions until triggers clear."
    else:
        recommended = "No intervention required — proceed with normal research workflow."

    intervention_required = any(
        t.action in {"stop_and_alert", "manual_review"} for t in triggers
    ) or "critical" in severities

    return InterventionStatusOut(
        intervention_required=intervention_required,
        triggers=triggers,
        recommended_action=recommended,
    )
