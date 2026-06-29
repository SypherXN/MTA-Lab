import json
import sqlite3
from pathlib import Path

from app.config import settings
from app.plan_defaults import DEFAULT_AGENT_PLAN
from app.plan_service import canonical_plan_json, seed_plan_content
from app.schemas import AgentPlanPayload
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"

DEFAULT_RULES = {
    "allowed_symbols": ["SPY", "QQQ", "AAPL", "MSFT"],
    "max_order_usd": 500,
    "max_daily_trades": 3,
    "max_daily_notional_usd": 1500,
    "require_review_before_place": True,
    "watchlist": ["SPY", "QQQ", "AAPL", "MSFT"],
    "symbol_cooldown_hours": 24,
}


def get_connection() -> sqlite3.Connection:
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def check_database() -> tuple[bool, str]:
    try:
        conn = get_connection()
        try:
            conn.execute("SELECT 1").fetchone()
            conn.execute("SELECT COUNT(*) AS c FROM strategies").fetchone()
            return True, "ok"
        finally:
            conn.close()
    except Exception as exc:
        return False, str(exc)


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate_schema(conn)
        _seed_if_empty(conn)
        _seed_agent_plan_if_empty(conn)
        conn.commit()
    finally:
        conn.close()


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) AS c FROM strategies").fetchone()
    if row["c"] > 0:
        return

    conn.execute(
        """
        INSERT INTO strategies (version, name, mode, trading_enabled, kill_switch, rules_json, is_active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (
            "v1",
            "Default Research Strategy",
            "research",
            0,
            0,
            __import__("json").dumps(DEFAULT_RULES),
        ),
    )
    conn.execute(
        "INSERT INTO simulated_cash (id, cash_usd) VALUES (1, ?)",
        (settings.initial_simulated_cash,),
    )
    conn.execute(
        """
        INSERT INTO manual_notes (content, active)
        VALUES (?, 1)
        """,
        ("Research mode: log all decisions; no live trades until mode is live.",),
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_plan_contents (
            content_hash TEXT PRIMARY KEY,
            plan_json TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )

    plan_cols = _table_columns(conn, "agent_plans")
    if "content_hash" not in plan_cols:
        conn.execute("ALTER TABLE agent_plans ADD COLUMN content_hash TEXT")
    if "change_source" not in plan_cols:
        conn.execute(
            "ALTER TABLE agent_plans ADD COLUMN change_source TEXT NOT NULL DEFAULT 'seed'"
        )

    run_cols = _table_columns(conn, "automation_runs")
    if "plan_version" not in run_cols:
        conn.execute("ALTER TABLE automation_runs ADD COLUMN plan_version TEXT")

    decision_cols = _table_columns(conn, "decisions")
    for column, ddl in (
        ("technical_score", "ALTER TABLE decisions ADD COLUMN technical_score REAL"),
        ("news_score", "ALTER TABLE decisions ADD COLUMN news_score REAL"),
        ("risk_score", "ALTER TABLE decisions ADD COLUMN risk_score REAL"),
        ("action_rationale", "ALTER TABLE decisions ADD COLUMN action_rationale TEXT"),
    ):
        if column not in decision_cols:
            conn.execute(ddl)

    for row in conn.execute(
        "SELECT id, plan_json FROM agent_plans WHERE content_hash IS NULL OR content_hash = ''"
    ):
        content_hash = seed_plan_content(conn, row["plan_json"])
        conn.execute(
            "UPDATE agent_plans SET content_hash = ? WHERE id = ?",
            (content_hash, row["id"]),
        )


def _seed_agent_plan_if_empty(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) AS c FROM agent_plans").fetchone()
    if row["c"] > 0:
        return

    payload = AgentPlanPayload.model_validate(DEFAULT_AGENT_PLAN)
    plan_json = canonical_plan_json(payload)
    content_hash = seed_plan_content(conn, plan_json)
    conn.execute(
        """
        INSERT INTO agent_plans (
            version, name, plan_json, content_hash, change_source, is_active
        ) VALUES (?, ?, ?, ?, ?, 1)
        """,
        (
            "v1",
            "Default Research Agent Plan",
            plan_json,
            content_hash,
            "seed",
        ),
    )
