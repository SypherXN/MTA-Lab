import sqlite3
from pathlib import Path

from app.config import settings
from app.db_monitor_service import record_db_snapshot
from app.schemas import MaintenanceRunOut


def run_maintenance(
    conn: sqlite3.Connection,
    *,
    vacuum: bool = True,
    analyze: bool = True,
) -> MaintenanceRunOut:
    vacuum_ran = False
    analyze_ran = False

    conn.commit()
    previous_isolation = conn.isolation_level
    conn.isolation_level = None
    try:
        if analyze:
            conn.execute("ANALYZE")
            analyze_ran = True

        if vacuum:
            conn.execute("VACUUM")
            vacuum_ran = True
    finally:
        conn.isolation_level = previous_isolation

    snapshot = record_db_snapshot(conn)
    db_path = Path(settings.database_path)
    file_size = db_path.stat().st_size if db_path.exists() else 0

    return MaintenanceRunOut(
        vacuum_ran=vacuum_ran,
        analyze_ran=analyze_ran,
        snapshot_id=snapshot.id,
        file_size_bytes=file_size,
        message="Maintenance complete.",
    )
