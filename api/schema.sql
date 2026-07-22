-- MTA-Lab SQLite schema

CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('research', 'paper', 'live')),
    trading_enabled INTEGER NOT NULL DEFAULT 0,
    kill_switch INTEGER NOT NULL DEFAULT 0,
    rules_json TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS manual_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS simulation_lanes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    plan_version TEXT NOT NULL,
    lane_role TEXT NOT NULL DEFAULT 'research'
        CHECK (lane_role IN ('research', 'shadow', 'live')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived')),
    initial_cash_usd REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_simulation_lanes_status
    ON simulation_lanes(status, lane_role);

CREATE TABLE IF NOT EXISTS lane_live_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lane_id INTEGER NOT NULL REFERENCES simulation_lanes(id),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_lane_live_periods_lane
    ON lane_live_periods(lane_id, started_at);

CREATE INDEX IF NOT EXISTS idx_lane_live_periods_open
    ON lane_live_periods(ended_at);

CREATE TABLE IF NOT EXISTS lane_execution_lock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    holder_lane_id INTEGER NOT NULL REFERENCES simulation_lanes(id),
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS automation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    automation_name TEXT,
    run_type TEXT NOT NULL DEFAULT 'daily_research',
    market_summary TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    strategy_version TEXT,
    plan_version TEXT,
    mode TEXT,
    buying_power REAL,
    errors_json TEXT,
    cursor_run_id TEXT,
    usage_json TEXT,
    self_critique TEXT,
    budget_exceeded INTEGER NOT NULL DEFAULT 0,
    expected_budget_usd REAL,
    actual_cost_usd REAL,
    lane_id INTEGER REFERENCES simulation_lanes(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES automation_runs(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    confidence REAL,
    technical_score REAL,
    news_score REAL,
    risk_score REAL,
    action_rationale TEXT,
    review_output TEXT,
    order_id TEXT,
    amount_usd REAL,
    mode TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS simulated_cash (
    lane_id INTEGER PRIMARY KEY REFERENCES simulation_lanes(id),
    cash_usd REAL NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS simulated_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lane_id INTEGER NOT NULL REFERENCES simulation_lanes(id),
    symbol TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(lane_id, symbol)
);

CREATE TABLE IF NOT EXISTS cursor_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES automation_runs(id) ON DELETE SET NULL,
    cursor_run_id TEXT,
    model TEXT,
    cost_usd REAL,
    estimated_cost_usd REAL,
    usage_import_key TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    source TEXT NOT NULL DEFAULT 'cursor_dashboard',
    reconciled_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_decisions_run_id ON decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol);
CREATE INDEX IF NOT EXISTS idx_runs_run_at ON automation_runs(run_at);
CREATE INDEX IF NOT EXISTS idx_cursor_usage_run_id ON cursor_usage(run_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_cursor_run_id
    ON automation_runs(cursor_run_id)
    WHERE cursor_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS robinhood_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    robinhood_order_id TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    status TEXT NOT NULL,
    quantity REAL,
    filled_quantity REAL,
    average_fill_price REAL,
    notional_usd REAL,
    submitted_at TEXT,
    updated_at_rh TEXT,
    raw_json TEXT,
    decision_id INTEGER REFERENCES decisions(id) ON DELETE SET NULL,
    synced_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quote_cache (
    symbol TEXT PRIMARY KEY,
    price_usd REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'import',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS market_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_type TEXT NOT NULL DEFAULT 'price_alert',
    symbol TEXT,
    message TEXT NOT NULL,
    check_needed INTEGER NOT NULL DEFAULT 1,
    consumed_at TEXT,
    source TEXT NOT NULL DEFAULT 'webhook',
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_robinhood_orders_symbol ON robinhood_orders(symbol);
CREATE INDEX IF NOT EXISTS idx_robinhood_orders_decision_id ON robinhood_orders(decision_id);
CREATE INDEX IF NOT EXISTS idx_market_signals_pending ON market_signals(check_needed, consumed_at);

CREATE TABLE IF NOT EXISTS reconciliation_alerts_sent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_key TEXT NOT NULL,
    sent_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_alerts_key ON reconciliation_alerts_sent(alert_key, sent_at);
CREATE INDEX IF NOT EXISTS idx_cursor_usage_cursor_run_id ON cursor_usage(cursor_run_id);
-- idx_cursor_usage_import_key is created by migration 016 (existing DBs lack the column until then).

CREATE TABLE IF NOT EXISTS agent_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    content_hash TEXT,
    change_source TEXT NOT NULL DEFAULT 'seed',
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_plans_active ON agent_plans(is_active, id DESC);
CREATE INDEX IF NOT EXISTS idx_agent_plans_version ON agent_plans(version);

CREATE TABLE IF NOT EXISTS agent_plan_contents (
    content_hash TEXT PRIMARY KEY,
    plan_json TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dashboard_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_dashboard_sessions_expires ON dashboard_sessions(expires_at);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lane_id INTEGER NOT NULL DEFAULT 1 REFERENCES simulation_lanes(id),
    snapshot_at TEXT NOT NULL,
    run_id INTEGER REFERENCES automation_runs(id) ON DELETE SET NULL,
    cash_usd REAL NOT NULL,
    positions_value_usd REAL NOT NULL,
    total_equity_usd REAL NOT NULL,
    unrealized_pnl_usd REAL,
    source TEXT NOT NULL DEFAULT 'run',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_at ON portfolio_snapshots(snapshot_at);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_lane ON portfolio_snapshots(lane_id, snapshot_at);

CREATE TABLE IF NOT EXISTS symbol_memory_summaries (
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

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS data_source_freshness (
    source_key TEXT PRIMARY KEY,
    last_updated_at TEXT NOT NULL,
    detail TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

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
