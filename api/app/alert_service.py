import json
from datetime import datetime, timezone

import httpx
import sqlite3

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


def _build_payload(summary: ReconciliationSummaryOut) -> dict:
    return {
        "event": "reconciliation_mismatch",
        "service": "mta-lab-api",
        "summary": summary.model_dump(),
        "message": (
            f"Reconciliation alert: {summary.unmatched_orders} unmatched order(s), "
            f"{summary.unmatched_decisions} unmatched decision(s)."
        ),
    }


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

    if not settings.alert_webhook_url:
        return AlertDispatchResponse(
            dispatched=False,
            reason="webhook_not_configured",
            summary=summary,
            message="Set MTA_ALERT_WEBHOOK_URL to enable reconciliation alerts.",
        )

    alert_key = (
        f"recon:{summary.unmatched_orders}:{summary.unmatched_decisions}:"
        f"{summary.linked_orders}:{summary.decisions_with_order_id}"
    )
    if not force and _alert_already_sent(conn, alert_key):
        return AlertDispatchResponse(
            dispatched=False,
            reason="cooldown",
            summary=summary,
            message=f"Alert suppressed (cooldown {settings.alert_cooldown_minutes}m).",
        )

    payload = _build_payload(summary)
    try:
        response = httpx.post(
            settings.alert_webhook_url,
            json=payload,
            timeout=10.0,
            headers={"User-Agent": "mta-lab-api/1.0"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return AlertDispatchResponse(
            dispatched=False,
            reason="webhook_error",
            summary=summary,
            message=f"Webhook delivery failed: {exc}",
        )

    _record_alert_sent(conn, alert_key)
    return AlertDispatchResponse(
        dispatched=True,
        reason="sent",
        summary=summary,
        message="Reconciliation alert dispatched to webhook.",
    )


def maybe_alert_after_order_import(conn: sqlite3.Connection) -> AlertDispatchResponse | None:
    if not settings.alert_webhook_url:
        return None
    summary = get_reconciliation_summary(conn)
    if summary.unmatched_orders == 0 and summary.unmatched_decisions == 0:
        return None
    return dispatch_reconciliation_alert(conn)
