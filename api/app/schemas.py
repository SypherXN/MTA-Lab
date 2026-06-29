from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class StrategyRules(BaseModel):
    allowed_symbols: list[str] = Field(default_factory=list)
    max_order_usd: float = 500
    max_daily_trades: int = 3
    max_daily_notional_usd: float = 1500
    require_review_before_place: bool = True
    watchlist: list[str] = Field(default_factory=list)
    symbol_cooldown_hours: float = 24


class StrategyOut(BaseModel):
    version: str
    name: str
    mode: str
    trading_enabled: bool
    kill_switch: bool
    rules: StrategyRules


class ManualNoteOut(BaseModel):
    id: int
    content: str
    created_at: str


class SimulatedPositionOut(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    last_price: float | None = None
    market_value: float | None = None
    cost_basis: float | None = None
    unrealized_pnl: float | None = None


class SimulatedPortfolioOut(BaseModel):
    cash_usd: float
    positions: list[SimulatedPositionOut]
    total_equity: float
    total_unrealized_pnl: float | None = None


class DecisionScoresIn(BaseModel):
    technical: float | None = Field(None, ge=0, le=1)
    news: float | None = Field(None, ge=0, le=1)
    risk: float | None = Field(None, ge=0, le=1)
    confidence: float | None = Field(None, ge=0, le=1)


class DecisionScoresOut(BaseModel):
    technical: float | None = None
    news: float | None = None
    risk: float | None = None
    confidence: float | None = None


class DecisionSummaryOut(BaseModel):
    id: int
    run_id: int
    symbol: str
    action: str
    reason: str
    confidence: float | None
    scores: DecisionScoresOut | None = None
    action_rationale: str | None = None
    review_output: str | None = None
    mode: str
    amount_usd: float | None
    created_at: str


class RunSummaryOut(BaseModel):
    id: int
    run_at: str
    automation_name: str | None
    market_summary: str | None
    status: str
    strategy_version: str | None
    plan_version: str | None = None
    mode: str | None
    buying_power: float | None
    cursor_run_id: str | None
    created_at: str


class UsageMetadata(BaseModel):
    model: str | None = None
    cursor_run_id: str | None = None
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class DecisionIn(BaseModel):
    symbol: str
    action: str
    reason: str
    confidence: float | None = Field(None, ge=0, le=1)
    scores: DecisionScoresIn | None = None
    action_rationale: str | None = None
    review_output: str | None = None
    order_id: str | None = None
    amount_usd: float | None = None
    fill_price: float | None = None

    def resolved_confidence(self) -> float | None:
        if self.scores and self.scores.confidence is not None:
            return self.scores.confidence
        return self.confidence

    def resolved_technical_score(self) -> float | None:
        return self.scores.technical if self.scores else None

    def resolved_news_score(self) -> float | None:
        return self.scores.news if self.scores else None

    def resolved_risk_score(self) -> float | None:
        return self.scores.risk if self.scores else None


class QuoteImportRow(BaseModel):
    symbol: str
    price_usd: float
    source: str = "import"


class RunCreate(BaseModel):
    run_at: datetime | None = None
    automation_name: str | None = "mta-research"
    market_summary: str | None = None
    status: str = "completed"
    buying_power: float | None = None
    errors: list[str] = Field(default_factory=list)
    cursor_run_id: str | None = None
    usage: UsageMetadata | None = None
    decisions: list[DecisionIn] = Field(default_factory=list)
    quotes: list[QuoteImportRow] = Field(default_factory=list)

    def normalized_status(self) -> str:
        return self.status.lower().strip()


class RunCreateResponse(BaseModel):
    run_id: int
    mode: str
    trading_allowed: bool
    safety_violations: list[str]
    simulated_portfolio: SimulatedPortfolioOut
    duplicate: bool = False


class SafetySnapshotOut(BaseModel):
    mode: str
    trading_enabled: bool
    kill_switch: bool
    trading_allowed: bool
    require_review_before_place: bool
    allowed_symbols: list[str]
    max_order_usd: float
    max_daily_trades: int
    max_daily_notional_usd: float
    daily_trades_used: int
    daily_notional_used: float
    daily_trades_remaining: int
    daily_notional_remaining: float
    allowed_actions: list[str]


class DecisionDetailOut(DecisionSummaryOut):
    order_id: str | None = None


class RunDetailOut(RunSummaryOut):
    errors: list[str] = Field(default_factory=list)
    usage: UsageMetadata | None = None
    decisions: list[DecisionDetailOut] = Field(default_factory=list)
    safety_violations: list[str] = Field(default_factory=list)


class SymbolCooldownOut(BaseModel):
    blocked_until: str
    reason: str
    last_action: str
    last_trade_at: str


class MarketSignalOut(BaseModel):
    id: int
    signal_type: str
    symbol: str | None
    message: str
    source: str
    created_at: str


class AutomationContextOut(BaseModel):
    strategy: StrategyOut
    manual_notes: list[ManualNoteOut]
    recent_runs: list[RunSummaryOut]
    recent_decisions: list[DecisionSummaryOut]
    simulated_portfolio: SimulatedPortfolioOut
    safety: SafetySnapshotOut
    cooldowns: dict[str, SymbolCooldownOut] = Field(default_factory=dict)
    check_needed: bool = False
    market_signals: list[MarketSignalOut] = Field(default_factory=list)


class DashboardStatsOut(BaseModel):
    total_runs: int
    completed_runs: int
    failed_runs: int
    total_decisions: int
    simulated_trades: int
    live_trades: int
    holds_and_skips: int
    total_cursor_cost_usd: float
    strategy_mode: str
    trading_enabled: bool


class CursorUsageImportRow(BaseModel):
    cursor_run_id: str | None = None
    run_id: int | None = None
    model: str | None = None
    cost_usd: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    timestamp: datetime | None = None


class CursorUsageImportRequest(BaseModel):
    rows: list[CursorUsageImportRow]


class CursorUsageOut(BaseModel):
    id: int
    run_id: int | None
    cursor_run_id: str | None
    model: str | None
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    source: str
    reconciled_at: str
    created_at: str


class StrategyUpdate(BaseModel):
    mode: str | None = None
    trading_enabled: bool | None = None
    kill_switch: bool | None = None
    rules: StrategyRules | None = None


class ManualNoteCreate(BaseModel):
    content: str


class ManualNoteUpdate(BaseModel):
    active: bool = False


class PortfolioResetResponse(BaseModel):
    cash_usd: float
    positions_cleared: int
    message: str


class HealthOut(BaseModel):
    status: str
    service: str
    database: str


class QuoteImportRequest(BaseModel):
    quotes: list[QuoteImportRow]


class QuoteImportResponse(BaseModel):
    upserted: int


class RobinhoodOrderImportRow(BaseModel):
    robinhood_order_id: str
    symbol: str
    side: str
    status: str
    quantity: float | None = None
    filled_quantity: float | None = None
    average_fill_price: float | None = None
    notional_usd: float | None = None
    submitted_at: str | None = None
    updated_at_rh: str | None = None
    raw_json: dict[str, Any] | None = None


class RobinhoodOrderImportRequest(BaseModel):
    orders: list[RobinhoodOrderImportRow]


class RobinhoodOrderImportResponse(BaseModel):
    upserted: int
    linked: int


class RobinhoodOrderOut(BaseModel):
    id: int
    robinhood_order_id: str
    symbol: str
    side: str
    status: str
    quantity: float | None
    filled_quantity: float | None
    average_fill_price: float | None
    notional_usd: float | None
    decision_id: int | None
    reconciliation_status: str
    synced_at: str
    created_at: str


class ReconciliationSummaryOut(BaseModel):
    total_orders: int
    linked_orders: int
    unmatched_orders: int
    decisions_with_order_id: int
    unmatched_decisions: int


class PriceAlertWebhook(BaseModel):
    symbol: str | None = None
    message: str
    signal_type: str = "price_alert"
    source: str = "webhook"
    payload: dict[str, Any] | None = None


class WebhookIngestResponse(BaseModel):
    signal_id: int
    check_needed: bool
    message: str


class PreflightCheckOut(BaseModel):
    name: str
    passed: bool
    message: str


class PreflightOut(BaseModel):
    ready_for_live: bool
    checks: list[PreflightCheckOut]


class AlertDispatchResponse(BaseModel):
    dispatched: bool
    reason: str
    summary: ReconciliationSummaryOut
    message: str


class QuoteOut(BaseModel):
    symbol: str
    price_usd: float
    source: str
    updated_at: str


class CursorUsageImportResponse(BaseModel):
    inserted: int
    linked: int


class AgentPlanRunStepOut(BaseModel):
    step: int
    action: str
    description: str
    endpoint: str | None = None
    source: str | None = None
    required: bool = True


class AgentPlanRequiredInputOut(BaseModel):
    name: str
    source: str
    description: str
    required: bool = True


class AgentPlanScoringRuleOut(BaseModel):
    id: str
    priority: str
    rule: str


class AgentPlanDataSourceOut(BaseModel):
    name: str
    type: str
    description: str | None = None
    url: str | None = None
    tools: list[str] = Field(default_factory=list)


class AgentPlanStopConditionOut(BaseModel):
    condition: str
    action: str
    description: str


class AgentPlanPayload(BaseModel):
    run_order: list[AgentPlanRunStepOut]
    required_inputs: list[AgentPlanRequiredInputOut]
    scoring_rules: list[AgentPlanScoringRuleOut]
    data_sources: list[AgentPlanDataSourceOut]
    stop_conditions: list[AgentPlanStopConditionOut]


class AgentPlanOut(AgentPlanPayload):
    version: str
    name: str
    change_source: str
    content_hash: str | None = None
    created_at: str
    updated_at: str


class AgentPlanSummaryOut(BaseModel):
    version: str
    name: str
    is_active: bool
    change_source: str
    content_hash: str | None = None
    created_at: str
    updated_at: str


class AgentPlanUpdate(BaseModel):
    name: str | None = None
    change_source: str = "api"
    plan: AgentPlanPayload | None = None


class AgentPlanUpdateResponse(BaseModel):
    plan: AgentPlanOut
    unchanged: bool
    previous_version: str | None = None
    message: str
