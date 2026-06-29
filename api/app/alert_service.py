import json
from datetime import datetime, timezone

import httpx
import sqlite3

from app.alert_routing import route_for
from app.alert_state_service import create_alert
from app.config import settings
from app.integration_service import get_reconciliation_summary
from app.schemas import AlertDispatchResponse, ReconciliationSummaryOut


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _alert_already_sent(conn: sqlite3.Connection, alert_key: str) -> bool:
    row = conn.execute(
        """
        SELECT id FROM reconciliation_alerts_sent
        WHERE alert_key = ?
          AND datetime(sent_at) >= datetime('now', ?)
        """,
        (alert_key, f"-{settings.alert_cooldown_minutes} minutes"),
    ).fetchone()
    return row is not None


def _record_alert_sent(conn: sqlite3.Connection, alert_key: str) -> None:
    conn.execute(
        "INSERT INTO reconciliation_alerts_sent (alert_key, sent_at) VALUES (?, ?)",
        (alert_key, _iso_now()),
    )


def _send_webhook(payload: dict) -> tuple[bool, str]:
    if not settings.alert_webhook_url:
        return False, "webhook_not_configured"
    try:
        response = httpx.post(
            settings.alert_webhook_url,
            json=payload,
            timeout=10.0,
            headers={"User-Agent": "mta-lab-api/1.0"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return False, f"webhook_error: {exc}"
    return True, "sent"


def dispatch_typed_alert(
    conn: sqlite3.Connection,
    *,
    alert_type: str,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    run_id: int | None = None,
    payload: dict | None = None,
    force: bool = False,
    alert_key: str | None = None,
) -> AlertDispatchResponse:
    route = route_for(alert_type)
    alert_id = None
    if route.persist:
        alert = create_alert(
            conn,
            alert_type=alert_type,
            title=title,
            message=message,
            severity=route.severity,
            entity_type=entity_type,
            entity_id=entity_id,
            run_id=run_id,
            payload=payload,
        )
        alert_id = alert.id

    dispatched = False
    reason = "persisted_only"
    if route.webhook:
        if alert_key and not force and _alert_already_sent(conn, alert_key):
            reason = "cooldown"
        elif not settings.alert_webhook_url:
            reason = "webhook_not_configured"
        else:
            webhook_payload = {
                "event": alert_type,
                "service": "mta-lab-api",
                "severity": route.severity,
                "title": title,
                "message": message,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "run_id": run_id,
                "payload": payload,
            }
            ok, webhook_reason = _send_webhook(webhook_payload)
            if ok:
                dispatched = True
                reason = "sent"
                if alert_key:
                    _record_alert_sent(conn, alert_key)
            else:
                reason = webhook_reason

    return AlertDispatchResponse(
        dispatched=dispatched,
        reason=reason,
        message=message if dispatched else f"Alert recorded (id={alert_id}); webhook: {reason}",
        alert_id=alert_id,
    )


def dispatch_reconciliation_alert(
    conn: sqlite3.Connection,
    *,
    force: bool = False,
) -> AlertDispatchResponse:
    summary = get_reconciliation_summary(conn)
    has_issues = summary.unmatched_orders > 0 or summary.unmatched_decisions > 0

    if not has_issues:
        return AlertDispatchResponse(
            dispatched=False,
            reason="no_issues",
            summary=summary,
            message="Reconciliation is clean; no alert sent.",
        )

    message = (
        f"Reconciliation alert: {summary.unmatched_orders} unmatched order(s), "
        f"{summary.unmatched_decisions} unmatched decision(s)."
    )
    alert_key = (
        f"recon:{summary.unmatched_orders}:{summary.unmatched_decisions}:"
        f"{summary.linked_orders}:{summary.decisions_with_order_id}"
    )
    result = dispatch_typed_alert(
        conn,
        alert_type="reconciliation_mismatch",
        title="Reconciliation mismatch",
        message=message,
        entity_type="reconciliation",
        payload=_build_reconciliation_payload(summary),
        force=force,
        alert_key=alert_key,
    )
    return AlertDispatchResponse(
        dispatched=result.dispatched,
        reason=result.reason,
        summary=summary,
        message=result.message,
        alert_id=result.alert_id,
    )


def _build_reconciliation_payload(summary: ReconciliationSummaryOut) -> dict:
    return {
        "event": "reconciliation_mismatch",
        "service": "mta-lab-api",
        "summary": summary.model_dump(),
    }


def dispatch_failed_run_alert(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    errors: list[str],
) -> AlertDispatchResponse | None:
    message = "; ".join(errors[:3])
    return dispatch_typed_alert(
        conn,
        alert_type="failed_run",
        title=f"Failed automation run #{run_id}",
        message=message or "Run failed without error detail.",
        entity_type="run",
        entity_id=str(run_id),
        run_id=run_id,
        payload={"errors": errors},
        alert_key=f"failed_run:{run_id}",
        force=True,
    )


def maybe_alert_after_order_import(conn: sqlite3.Connection) -> AlertDispatchResponse | None:
    summary = get_reconciliation_summary(conn)
    if summary.unmatched_orders == 0 and summary.unmatched_decisions == 0:
        return None
    return dispatch_reconciliation_alert(conn)
