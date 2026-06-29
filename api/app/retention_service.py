import sqlite3

from app.schemas import RetentionRunOut


def run_retention(
    conn: sqlite3.Connection,
    *,
    keep_runs_days: int = 90,
    keep_snapshots_days: int = 180,
    keep_usage_days: int = 180,
) -> RetentionRunOut:
    if keep_runs_days < 7:
        raise ValueError("keep_runs_days must be at least 7")

    runs_deleted = conn.execute(
        """
        DELETE FROM automation_runs
        WHERE datetime(run_at) < datetime('now', ?)
        """,
        (f"-{keep_runs_days} days",),
    ).rowcount

    snapshots_deleted = conn.execute(
        """
        DELETE FROM portfolio_snapshots
        WHERE datetime(snapshot_at) < datetime('now', ?)
        """,
        (f"-{keep_snapshots_days} days",),
    ).rowcount

    usage_deleted = conn.execute(
        """
        DELETE FROM cursor_usage
        WHERE datetime(reconciled_at) < datetime('now', ?)
          AND run_id IS NULL
        """,
        (f"-{keep_usage_days} days",),
    ).rowcount

    resolved_alerts_deleted = conn.execute(
        """
        DELETE FROM alerts
        WHERE status = 'resolved'
          AND datetime(resolved_at) < datetime('now', '-30 days')
        """
    ).rowcount

    return RetentionRunOut(
        runs_deleted=runs_deleted,
        snapshots_deleted=snapshots_deleted,
        usage_deleted=usage_deleted,
        resolved_alerts_deleted=resolved_alerts_deleted,
        message="Retention pass complete.",
    )
