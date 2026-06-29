"""Alert type routing rules — webhook dispatch and default severity."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AlertRoute:
    severity: str
    webhook: bool
    persist: bool = True


ALERT_ROUTES: dict[str, AlertRoute] = {
    "reconciliation_mismatch": AlertRoute(severity="high", webhook=True),
    "failed_run": AlertRoute(severity="critical", webhook=True),
    "kill_switch_triggered": AlertRoute(severity="critical", webhook=True),
    "stale_data": AlertRoute(severity="high", webhook=True),
    "budget_exceeded": AlertRoute(severity="medium", webhook=True),
    "simulated_drawdown": AlertRoute(severity="high", webhook=True),
    "live_promotion": AlertRoute(severity="high", webhook=False),
    "intervention_required": AlertRoute(severity="high", webhook=True),
}


def route_for(alert_type: str) -> AlertRoute:
    return ALERT_ROUTES.get(alert_type, AlertRoute(severity="medium", webhook=True))
