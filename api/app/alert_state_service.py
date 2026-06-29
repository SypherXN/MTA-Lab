import json
import sqlite3
from datetime import datetime, timezone

from app.schemas import AlertOut, AlertStatusUpdate

ALERT_STATUSES = {"open", "acknowledged", "resolved"}
ALERT_SEVERITIES = {"critical", "high", "medium", "low"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_alert(row: sqlite3.Row) -> AlertOut:
    payload = json.loads(row["payload_json"]) if row["payload_json"] else None
    return AlertOut(
        id=row["id"],
        alert_type=row["alert_type"],
        severity=row["severity"],
        status=row["status"],
        title=row["title"],
        message=row["message"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        run_id=row["run_id"],
        payload=payload,
        created_at=row["created_at"],
        acknowledged_at=row["acknowledged_at"],
        resolved_at=row["resolved_at"],
    )


def create_alert(
    conn: sqlite3.Connection,
    *,
    alert_type: str,
    title: str,
    message: str,
    severity: str = "high",
    entity_type: str | None = None,
    entity_id: str | None = None,
    run_id: int | None = None,
    payload: dict | None = None,
) -> AlertOut:
    if severity not in ALERT_SEVERITIES:
        severity = "high"
    now = _iso_now()
    cursor = conn.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, status, title, message,
            entity_type, entity_id, run_id, payload_json, created_at
        ) VALUES (?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alert_type,
            severity,
            title,
            message,
            entity_type,
            entity_id,
            run_id,
            json.dumps(payload) if payload else None,
            now,
        ),
    )
    row = conn.execute("SELECT * FROM alerts WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row_to_alert(row)


def list_alerts(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[AlertOut]:
    if status:
        rows = conn.execute(
            """
            SELECT * FROM alerts WHERE status = ?
            ORDER BY id DESC LIMIT ?
            """,
            (status, limit),
        )
    else:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    return [_row_to_alert(row) for row in rows]


def update_alert_status(
    conn: sqlite3.Connection,
    alert_id: int,
    update: AlertStatusUpdate,
) -> AlertOut:
    if update.status not in ALERT_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(ALERT_STATUSES))}")

    row = conn.execute("SELECT id FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    if row is None:
        raise ValueError(f"Alert {alert_id} not found")

    now = _iso_now()
    acknowledged_at = now if update.status == "acknowledged" else None
    resolved_at = now if update.status == "resolved" else None
    conn.execute(
        """
        UPDATE alerts
        SET status = ?,
            acknowledged_at = COALESCE(?, acknowledged_at),
            resolved_at = COALESCE(?, resolved_at)
        WHERE id = ?
        """,
        (update.status, acknowledged_at, resolved_at, alert_id),
    )
    updated = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    return _row_to_alert(updated)


def open_alert_count(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute("SELECT COUNT(*) AS c FROM alerts WHERE status = 'open'").fetchone()["c"]
    )
