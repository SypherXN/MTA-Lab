import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.migrations import MIGRATIONS
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
    "symbol_discovery_enabled": False,
    "discovery_max_per_run": 2,
    "discovery_pool": [],
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
        from app.lane_service import ensure_primary_lane

        ensure_primary_lane(conn)
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
        """
        INSERT INTO manual_notes (content, active)
        VALUES (?, 1)
        """,
        ("Research mode: log all decisions; no live trades until mode is live.",),
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply versioned migrations, then one-time data backfills."""
    _apply_pending_migrations(conn)
    # Idempotent: safe for DBs that applied placeholder migrations before side effects existed
    _migrate_lane_tables(conn)

    from app.memory_service import backfill_symbol_memory_summaries
    from app.freshness_service import backfill_freshness_from_existing

    summary_count = conn.execute("SELECT COUNT(*) AS c FROM symbol_memory_summaries").fetchone()["c"]
    decision_count = conn.execute("SELECT COUNT(*) AS c FROM decisions").fetchone()["c"]
    if summary_count == 0 and decision_count > 0:
        backfill_symbol_memory_summaries(conn)

    backfill_freshness_from_existing(conn)
    from app.live_history_service import backfill_live_periods

    backfill_live_periods(conn)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(ddl)


def _migration_side_effects(conn: sqlite3.Connection, version: str) -> None:
    """Python upgrades paired with placeholder / partial SQL migrations."""
    if version == "002_run_type_column":
        _ensure_column(
            conn,
            "automation_runs",
            "run_type",
            "ALTER TABLE automation_runs ADD COLUMN run_type TEXT NOT NULL DEFAULT 'daily_research'",
        )
    elif version == "010_run_budget_columns":
        _ensure_column(
            conn,
            "automation_runs",
            "budget_exceeded",
            "ALTER TABLE automation_runs ADD COLUMN budget_exceeded INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            conn,
            "automation_runs",
            "expected_budget_usd",
            "ALTER TABLE automation_runs ADD COLUMN expected_budget_usd REAL",
        )
        _ensure_column(
            conn,
            "automation_runs",
            "actual_cost_usd",
            "ALTER TABLE automation_runs ADD COLUMN actual_cost_usd REAL",
        )
        _ensure_column(
            conn,
            "automation_runs",
            "self_critique",
            "ALTER TABLE automation_runs ADD COLUMN self_critique TEXT",
        )
        _ensure_column(
            conn,
            "automation_runs",
            "plan_version",
            "ALTER TABLE automation_runs ADD COLUMN plan_version TEXT",
        )
        for column, ddl in (
            ("technical_score", "ALTER TABLE decisions ADD COLUMN technical_score REAL"),
            ("news_score", "ALTER TABLE decisions ADD COLUMN news_score REAL"),
            ("risk_score", "ALTER TABLE decisions ADD COLUMN risk_score REAL"),
            ("action_rationale", "ALTER TABLE decisions ADD COLUMN action_rationale TEXT"),
        ):
            _ensure_column(conn, "decisions", column, ddl)
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
        _ensure_column(conn, "agent_plans", "content_hash", "ALTER TABLE agent_plans ADD COLUMN content_hash TEXT")
        _ensure_column(
            conn,
            "agent_plans",
            "change_source",
            "ALTER TABLE agent_plans ADD COLUMN change_source TEXT NOT NULL DEFAULT 'seed'",
        )
        for row in conn.execute(
            "SELECT id, plan_json FROM agent_plans WHERE content_hash IS NULL OR content_hash = ''"
        ):
            content_hash = seed_plan_content(conn, row["plan_json"])
            conn.execute(
                "UPDATE agent_plans SET content_hash = ? WHERE id = ?",
                (content_hash, row["id"]),
            )
    elif version == "011_simulation_lanes":
        _migrate_lane_tables(conn)


def _apply_pending_migrations(conn: sqlite3.Connection) -> list[str]:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    applied: list[str] = []
    for version, sql in sorted(MIGRATIONS.items()):
        row = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            (version,),
        ).fetchone()
        if row is not None:
            continue
        conn.executescript(sql)
        _migration_side_effects(conn, version)
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)",
            (version,),
        )
        applied.append(version)
    return applied


def _migrate_lane_tables(conn: sqlite3.Connection) -> None:
    cash_cols = _table_columns(conn, "simulated_cash")
    if "lane_id" not in cash_cols:
        legacy = conn.execute(
            "SELECT cash_usd, updated_at FROM simulated_cash WHERE id = 1"
        ).fetchone()
        cash_usd = float(legacy["cash_usd"]) if legacy else settings.initial_simulated_cash
        updated_at = legacy["updated_at"] if legacy else datetime.now(timezone.utc).isoformat()
        conn.execute("ALTER TABLE simulated_cash RENAME TO simulated_cash_legacy")
        conn.execute(
            """
            CREATE TABLE simulated_cash (
                lane_id INTEGER PRIMARY KEY,
                cash_usd REAL NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "INSERT INTO simulated_cash (lane_id, cash_usd, updated_at) VALUES (1, ?, ?)",
            (cash_usd, updated_at),
        )
        conn.execute("DROP TABLE simulated_cash_legacy")

    pos_cols = _table_columns(conn, "simulated_positions")
    if "lane_id" not in pos_cols:
        conn.executescript(
            """
            CREATE TABLE simulated_positions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lane_id INTEGER NOT NULL DEFAULT 1,
                symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                avg_cost REAL NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(lane_id, symbol)
            );
            INSERT INTO simulated_positions_new (id, lane_id, symbol, quantity, avg_cost, updated_at)
            SELECT id, 1, symbol, quantity, avg_cost, updated_at FROM simulated_positions;
            DROP TABLE simulated_positions;
            ALTER TABLE simulated_positions_new RENAME TO simulated_positions;
            """
        )

    if "lane_id" not in _table_columns(conn, "automation_runs"):
        conn.execute(
            "ALTER TABLE automation_runs ADD COLUMN lane_id INTEGER REFERENCES simulation_lanes(id)"
        )
        conn.execute("UPDATE automation_runs SET lane_id = 1 WHERE lane_id IS NULL")

    if "lane_id" not in _table_columns(conn, "portfolio_snapshots"):
        conn.execute(
            "ALTER TABLE portfolio_snapshots ADD COLUMN lane_id INTEGER NOT NULL DEFAULT 1"
        )
        conn.execute("UPDATE portfolio_snapshots SET lane_id = 1 WHERE lane_id IS NULL")

    mem_cols = _table_columns(conn, "symbol_memory_summaries")
    if "lane_id" not in mem_cols:
        conn.executescript(
            """
            CREATE TABLE symbol_memory_summaries_new (
                lane_id INTEGER NOT NULL DEFAULT 1,
                symbol TEXT NOT NULL,
                last_action TEXT,
                last_buy_at TEXT,
                last_sell_at TEXT,
                last_run_id INTEGER REFERENCES automation_runs(id) ON DELETE SET NULL,
                trade_count INTEGER NOT NULL DEFAULT 0,
                win_count INTEGER NOT NULL DEFAULT 0,
                loss_count INTEGER NOT NULL DEFAULT 0,
                realized_pnl_usd REAL NOT NULL DEFAULT 0,
                unrealized_pnl_usd REAL,
                risk_notes_json TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (lane_id, symbol)
            );
            INSERT INTO symbol_memory_summaries_new (
                lane_id, symbol, last_action, last_buy_at, last_sell_at, last_run_id,
                trade_count, win_count, loss_count, realized_pnl_usd, unrealized_pnl_usd,
                risk_notes_json, updated_at
            )
            SELECT
                1, symbol, last_action, last_buy_at, last_sell_at, last_run_id,
                trade_count, win_count, loss_count, realized_pnl_usd, unrealized_pnl_usd,
                risk_notes_json, updated_at
            FROM symbol_memory_summaries;
            DROP TABLE symbol_memory_summaries;
            ALTER TABLE symbol_memory_summaries_new RENAME TO symbol_memory_summaries;
            """
        )


def _seed_agent_plan_if_empty(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) AS c FROM agent_plans").fetchone()
    if row["c"] > 0:
        return

    from app.plan_service import _load_plan_file

    plan_path = settings.resolved_plans_dir() / "v1.json"
    if not plan_path.is_file():
        raise FileNotFoundError(f"Default plan not found at {plan_path}")
    version, name, payload, _make_active, _change_source = _load_plan_file(plan_path)
    plan_json = canonical_plan_json(payload)
    content_hash = seed_plan_content(conn, plan_json)
    conn.execute(
        """
        INSERT INTO agent_plans (
            version, name, plan_json, content_hash, change_source, is_active
        ) VALUES (?, ?, ?, ?, ?, 1)
        """,
        (
            version,
            name,
            plan_json,
            content_hash,
            "seed",
        ),
    )
