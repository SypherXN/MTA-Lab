"""Prometheus text metrics for MTA-Lab API."""

import sqlite3

from app.alert_state_service import open_alert_count
from app.config import settings
from app.db_monitor_service import count_table_rows
from app.freshness_service import evaluate_freshness
from app.schemas import DashboardStatsOut
from app.dashboard_service import get_dashboard_stats
from pathlib import Path


def render_prometheus_metrics(conn: sqlite3.Connection) -> str:
    stats: DashboardStatsOut = get_dashboard_stats(conn)
    freshness = evaluate_freshness(conn)
    open_alerts = open_alert_count(conn)
    db_path = Path(settings.database_path)
    db_bytes = db_path.stat().st_size if db_path.exists() else 0
    row_counts = count_table_rows(conn)

    lines = [
        "# HELP mta_runs_total Total automation runs logged",
        "# TYPE mta_runs_total gauge",
        f"mta_runs_total {stats.total_runs}",
        "# HELP mta_runs_failed_total Failed automation runs",
        "# TYPE mta_runs_failed_total gauge",
        f"mta_runs_failed_total {stats.failed_runs}",
        "# HELP mta_decisions_total Total decisions logged",
        "# TYPE mta_decisions_total gauge",
        f"mta_decisions_total {stats.total_decisions}",
        "# HELP mta_cursor_cost_usd_total Total Cursor spend tracked",
        "# TYPE mta_cursor_cost_usd_total gauge",
        f"mta_cursor_cost_usd_total {stats.total_cursor_cost_usd or 0}",
        "# HELP mta_alerts_open Open alerts",
        "# TYPE mta_alerts_open gauge",
        f"mta_alerts_open {open_alerts}",
        "# HELP mta_db_file_bytes SQLite database file size",
        "# TYPE mta_db_file_bytes gauge",
        f"mta_db_file_bytes {db_bytes}",
        "# HELP mta_freshness_ready Whether all required data sources are fresh",
        "# TYPE mta_freshness_ready gauge",
        f"mta_freshness_ready {1 if freshness.ready_for_analysis else 0}",
    ]
    for table, count in row_counts.items():
        safe = table.replace("-", "_")
        lines.append(f"mta_table_rows{{table=\"{safe}\"}} {count}")
    return "\n".join(lines) + "\n"
