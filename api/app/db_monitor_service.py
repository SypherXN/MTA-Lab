import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.schemas import DbSizeSnapshotOut

MONITORED_TABLES = (
    "automation_runs",
    "decisions",
    "portfolio_snapshots",
    "cursor_usage",
    "alerts",
    "robinhood_orders",
    "news_event_summaries",
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _count_rows(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in MONITORED_TABLES:
        try:
            counts[table] = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        except sqlite3.OperationalError:
            counts[table] = 0
    return counts


def count_table_rows(conn: sqlite3.Connection) -> dict[str, int]:
    return _count_rows(conn)


def _latest_backup_size() -> int | None:
    backup_dir = Path(settings.backup_dir)
    if not backup_dir.is_dir():
        return None
    backups = sorted(backup_dir.glob("*.db*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        return None
    return backups[0].stat().st_size


def record_db_snapshot(conn: sqlite3.Connection) -> DbSizeSnapshotOut:
    db_path = Path(settings.database_path)
    file_size = db_path.stat().st_size if db_path.exists() else 0
    row_counts = _count_rows(conn)
    backup_size = _latest_backup_size()
    now = _iso_now()
    cursor = conn.execute(
        """
        INSERT INTO db_size_snapshots (
            snapshot_at, file_size_bytes, row_counts_json, backup_size_bytes
        ) VALUES (?, ?, ?, ?)
        """,
        (now, file_size, json.dumps(row_counts), backup_size),
    )
    return DbSizeSnapshotOut(
        id=int(cursor.lastrowid),
        snapshot_at=now,
        file_size_bytes=file_size,
        row_counts=row_counts,
        backup_size_bytes=backup_size,
    )


def list_db_snapshots(conn: sqlite3.Connection, limit: int = 30) -> list[DbSizeSnapshotOut]:
    rows = conn.execute(
        """
        SELECT id, snapshot_at, file_size_bytes, row_counts_json, backup_size_bytes
        FROM db_size_snapshots
        ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    )
    results: list[DbSizeSnapshotOut] = []
    for row in rows:
        results.append(
            DbSizeSnapshotOut(
                id=row["id"],
                snapshot_at=row["snapshot_at"],
                file_size_bytes=row["file_size_bytes"],
                row_counts=json.loads(row["row_counts_json"]),
                backup_size_bytes=row["backup_size_bytes"],
            )
        )
    return results
