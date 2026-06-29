"""Default agent plan content — how the automation should operate (not trading limits)."""

DEFAULT_AGENT_PLAN = {
    "run_order": [
        {
            "step": 1,
            "action": "fetch_plan",
            "description": "Load the active agent plan from the API.",
            "endpoint": "GET /api/automation/plan",
            "required": True,
        },
        {
            "step": 2,
            "action": "fetch_context",
            "description": "Load strategy, safety budget, history, notes, and signals.",
            "endpoint": "GET /api/automation/context",
            "required": True,
        },
        {
            "step": 3,
            "action": "fetch_market_state",
            "description": "Read portfolio, positions, watchlist quotes, and recent orders via Robinhood MCP.",
            "source": "robinhood_mcp",
            "required": True,
        },
        {
            "step": 4,
            "action": "sync_orders",
            "description": "Import Robinhood orders for reconciliation.",
            "endpoint": "POST /api/admin/robinhood-orders/import",
            "required": True,
        },
        {
            "step": 5,
            "action": "analyze",
            "description": "Analyze each watchlist/allowed symbol using plan inputs, strategy rules, and history.",
            "required": True,
        },
        {
            "step": 6,
            "action": "review_trades",
            "description": "Call review_equity_order for any would-be live trade; never place unless safety.trading_allowed.",
            "required": False,
        },
        {
            "step": 7,
            "action": "log_run",
            "description": "POST completed or failed run with decisions, quotes, usage, and errors.",
            "endpoint": "POST /api/automation/runs",
            "required": True,
        },
    ],
    "required_inputs": [
        {
            "name": "strategy",
            "source": "api_context.strategy",
            "description": "Active strategy mode, version, and rule caps.",
            "required": True,
        },
        {
            "name": "safety",
            "source": "api_context.safety",
            "description": "Allowed actions, daily budget, cooldowns, and trading_allowed flag.",
            "required": True,
        },
        {
            "name": "recent_decisions",
            "source": "api_context.recent_decisions",
            "description": "Prior agent actions for continuity and mistake avoidance.",
            "required": True,
        },
        {
            "name": "manual_notes",
            "source": "api_context.manual_notes",
            "description": "Operator notes that should influence behavior.",
            "required": False,
        },
        {
            "name": "market_signals",
            "source": "api_context.market_signals",
            "description": "Pending check_needed alerts from webhooks or price watcher.",
            "required": False,
        },
        {
            "name": "portfolio",
            "source": "robinhood_mcp.get_portfolio",
            "description": "Live account cash and buying power.",
            "required": True,
        },
        {
            "name": "positions",
            "source": "robinhood_mcp.get_equity_positions",
            "description": "Current equity holdings.",
            "required": True,
        },
        {
            "name": "quotes",
            "source": "robinhood_mcp.get_equity_quotes",
            "description": "Latest prices for watchlist symbols.",
            "required": True,
        },
        {
            "name": "recent_orders",
            "source": "robinhood_mcp.get_equity_orders",
            "description": "Recent Robinhood order history for reconciliation.",
            "required": True,
        },
    ],
    "scoring_rules": [
        {
            "id": "respect_safety",
            "priority": "critical",
            "rule": "Treat api_context.safety and strategy rules as hard constraints.",
        },
        {
            "id": "research_simulation",
            "priority": "critical",
            "rule": "In research/paper mode use simulated_buy/simulated_sell; never place_equity_order unless trading_allowed.",
        },
        {
            "id": "symbol_coverage",
            "priority": "high",
            "rule": "Produce a decision row for every symbol analyzed, including hold and skip.",
        },
        {
            "id": "decision_scoring",
            "priority": "high",
            "rule": "Every decision must include scores (technical, news, risk, confidence on 0-1) and action_rationale explaining how scores led to the action.",
        },
        {
            "id": "explain_decisions",
            "priority": "high",
            "rule": "Every decision must include a clear reason; add review_output for live trade intents when required.",
        },
        {
            "id": "prefer_hold_when_uncertain",
            "priority": "medium",
            "rule": "When data is missing, ambiguous, or conflicting, choose hold or skip.",
        },
        {
            "id": "respect_cooldowns",
            "priority": "high",
            "rule": "Do not log buy/simulated_buy on symbols listed in api_context.cooldowns.",
        },
    ],
    "data_sources": [
        {
            "name": "mta_api",
            "type": "http",
            "description": "MTA-Lab API for plan, context, logging, and reconciliation.",
        },
        {
            "name": "robinhood_mcp",
            "type": "mcp",
            "url": "https://agent.robinhood.com/mcp/trading",
            "tools": [
                "get_portfolio",
                "get_equity_positions",
                "get_equity_quotes",
                "get_equity_orders",
                "review_equity_order",
                "place_equity_order",
            ],
        },
    ],
    "stop_conditions": [
        {
            "condition": "context_or_plan_unavailable",
            "action": "log_failed_run_and_stop",
            "description": "Do not trade if plan or context cannot be loaded.",
        },
        {
            "condition": "kill_switch_active",
            "action": "hold_only",
            "description": "Only passive actions when kill_switch is true.",
        },
        {
            "condition": "required_mcp_data_missing",
            "action": "log_failed_run_and_stop",
            "description": "Stop if portfolio, quotes, or orders cannot be retrieved.",
        },
        {
            "condition": "safety_violation_detected",
            "action": "do_not_submit_trade_actions",
            "description": "Downgrade to hold/skip rather than violating caps or cooldowns.",
        },
        {
            "condition": "live_trading_not_allowed",
            "action": "research_only",
            "description": "Never call place_equity_order unless mode=live, trading_enabled, and kill_switch=false.",
        },
    ],
}
