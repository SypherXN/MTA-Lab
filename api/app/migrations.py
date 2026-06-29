"""Numbered SQL migrations applied idempotently via schema_migrations."""

MIGRATIONS: dict[str, str] = {
    "001_dashboard_sessions": """
        CREATE TABLE IF NOT EXISTS dashboard_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_dashboard_sessions_expires
            ON dashboard_sessions(expires_at);
    """,
    "002_run_type_column": """
        -- Applied via ALTER in Python when column missing; placeholder for tracking.
        SELECT 1;
    """,
    "003_portfolio_snapshots": """
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_at TEXT NOT NULL,
            run_id INTEGER REFERENCES automation_runs(id) ON DELETE SET NULL,
            cash_usd REAL NOT NULL,
            positions_value_usd REAL NOT NULL,
            total_equity_usd REAL NOT NULL,
            unrealized_pnl_usd REAL,
            source TEXT NOT NULL DEFAULT 'run',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_at
            ON portfolio_snapshots(snapshot_at);
    """,
    "004_symbol_memory_summaries": """
        CREATE TABLE IF NOT EXISTS symbol_memory_summaries (
            symbol TEXT PRIMARY KEY,
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
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """,
    "005_data_source_freshness": """
        CREATE TABLE IF NOT EXISTS data_source_freshness (
            source_key TEXT PRIMARY KEY,
            last_updated_at TEXT NOT NULL,
            detail TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """,
    "006_news_event_summaries": """
        CREATE TABLE IF NOT EXISTS news_event_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            source TEXT NOT NULL,
            event_at TEXT NOT NULL,
            event_type TEXT,
            importance REAL,
            sentiment REAL,
            summary TEXT NOT NULL,
            external_id TEXT,
            ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_news_symbol_event
            ON news_event_summaries(symbol, event_at);
        CREATE INDEX IF NOT EXISTS idx_news_event_at
            ON news_event_summaries(event_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_news_source_external
            ON news_event_summaries(source, external_id)
            WHERE external_id IS NOT NULL;
    """,
    "007_run_self_critique": """
        -- Applied via ALTER in Python when column missing; placeholder for tracking.
        SELECT 1;
    """,
    "008_alerts_and_ops": """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'high',
            status TEXT NOT NULL DEFAULT 'open',
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            entity_type TEXT,
            entity_id TEXT,
            run_id INTEGER REFERENCES automation_runs(id) ON DELETE SET NULL,
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            acknowledged_at TEXT,
            resolved_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type, created_at);

        CREATE TABLE IF NOT EXISTS live_promotion_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            requested_at TEXT NOT NULL,
            approved_at TEXT,
            approved_by TEXT,
            expires_at TEXT NOT NULL,
            preflight_snapshot_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_live_promotion_status
            ON live_promotion_requests(status, requested_at);

        CREATE TABLE IF NOT EXISTS db_size_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_at TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            row_counts_json TEXT NOT NULL,
            backup_size_bytes INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_db_size_snapshots_at
            ON db_size_snapshots(snapshot_at);
    """,
    "009_rollups_and_payloads": """
        CREATE TABLE IF NOT EXISTS daily_rollups (
            rollup_date TEXT PRIMARY KEY,
            run_count INTEGER NOT NULL DEFAULT 0,
            completed_runs INTEGER NOT NULL DEFAULT 0,
            failed_runs INTEGER NOT NULL DEFAULT 0,
            decision_count INTEGER NOT NULL DEFAULT 0,
            simulated_trades INTEGER NOT NULL DEFAULT 0,
            live_trades INTEGER NOT NULL DEFAULT 0,
            passive_decisions INTEGER NOT NULL DEFAULT 0,
            avg_confidence REAL,
            total_cost_usd REAL NOT NULL DEFAULT 0,
            alert_count INTEGER NOT NULL DEFAULT 0,
            equity_change_usd REAL,
            runs_by_strategy_json TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS compact_payloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            payload_storage TEXT NOT NULL,
            is_compressed INTEGER NOT NULL DEFAULT 0,
            byte_size INTEGER NOT NULL DEFAULT 0,
            truncated INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(entity_type, entity_id)
        );
        CREATE INDEX IF NOT EXISTS idx_compact_payloads_entity
            ON compact_payloads(entity_type, entity_id);
    """,
    "010_run_budget_columns": """
        -- Applied via ALTER in Python when columns missing; placeholder for tracking.
        SELECT 1;
    """,
}
