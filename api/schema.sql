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

CREATE TABLE IF NOT EXISTS automation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    automation_name TEXT,
    market_summary TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    strategy_version TEXT,
    plan_version TEXT,
    mode TEXT,
    buying_power REAL,
    errors_json TEXT,
    cursor_run_id TEXT,
    usage_json TEXT,
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
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cash_usd REAL NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS simulated_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cursor_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES automation_runs(id) ON DELETE SET NULL,
    cursor_run_id TEXT,
    model TEXT,
    cost_usd REAL,
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
