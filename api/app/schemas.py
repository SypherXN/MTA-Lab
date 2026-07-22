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
    symbol_discovery_enabled: bool = False
    discovery_max_per_run: int = Field(default=2, ge=0, le=10)
    discovery_pool: list[str] = Field(
        default_factory=list,
        description="Optional extra symbols to consider; must be subset of allowed_symbols. "
        "When empty, uses allowed_symbols minus watchlist.",
    )


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
    lane_id: int | None = None
    lane_name: str | None = None
    lane_role: str | None = None


class RunSummaryOut(BaseModel):
    id: int
    run_at: str
    automation_name: str | None
    run_type: str | None = None
    market_summary: str | None
    status: str
    strategy_version: str | None
    plan_version: str | None = None
    mode: str | None
    buying_power: float | None
    cursor_run_id: str | None
    created_at: str
    lane_id: int | None = None
    lane_name: str | None = None
    lane_role: str | None = None
    budget_exceeded: bool = False
    expected_budget_usd: float | None = None
    actual_cost_usd: float | None = None


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
    run_type: str | None = None
    lane_id: int | None = None
    market_summary: str | None = None
    self_critique: str | None = None
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
    lane_id: int
    lane_name: str | None = None
    mode: str
    trading_allowed: bool
    safety_violations: list[str]
    simulated_portfolio: SimulatedPortfolioOut
    duplicate: bool = False
    budget_check: "RunBudgetCheckOut | None" = None


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
    self_critique: str | None = None
    decisions: list[DecisionDetailOut] = Field(default_factory=list)
    safety_violations: list[str] = Field(default_factory=list)
    audit: "RunAuditOut | None" = None


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


class DataSourceFreshnessOut(BaseModel):
    source_key: str
    last_updated_at: str | None
    detail: str | None = None
    updated_at: str | None = None
    max_age_minutes: int | None = None
    age_minutes: float | None = None
    is_stale: bool = False


class DataFreshnessChecksOut(BaseModel):
    sources: list[DataSourceFreshnessOut] = Field(default_factory=list)
    stale_sources: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    ready_for_analysis: bool = True
    warnings: list[str] = Field(default_factory=list)


class NewsEventIn(BaseModel):
    symbol: str | None = None
    source: str
    event_at: str
    event_type: str | None = None
    importance: float | None = Field(None, ge=0, le=1)
    sentiment: float | None = Field(None, ge=-1, le=1)
    summary: str
    external_id: str | None = None


class NewsEventImportRequest(BaseModel):
    events: list[NewsEventIn]


class NewsEventImportResponse(BaseModel):
    inserted: int
    skipped: int


class NewsEventOut(BaseModel):
    id: int
    symbol: str | None
    source: str
    event_at: str
    event_type: str | None = None
    importance: float | None = None
    sentiment: float | None = None
    summary: str
    ingested_at: str


class MarketInputCheckItemOut(BaseModel):
    key: str
    label: str
    required: bool
    present: bool
    source: str | None = None
    detail: str | None = None


class MarketInputQuoteOut(BaseModel):
    symbol: str
    price_usd: float
    source: str | None = None
    updated_at: str | None = None


class MarketInputMoverOut(BaseModel):
    symbol: str
    price_usd: float | None = None
    change_pct: float | None = None
    detail: str | None = None


class MarketInputBundleOut(BaseModel):
    checklist: list[MarketInputCheckItemOut] = Field(default_factory=list)
    ready: bool = False
    watchlist: list[str] = Field(default_factory=list)
    watchlist_quotes: list[MarketInputQuoteOut] = Field(default_factory=list)
    index_quotes: list[MarketInputQuoteOut] = Field(default_factory=list)
    volatility_quotes: list[MarketInputQuoteOut] = Field(default_factory=list)
    movers: list[MarketInputMoverOut] = Field(default_factory=list)
    simulated_portfolio: SimulatedPortfolioOut | None = None
    recent_orders_count: int = 0
    gathered_at: str


class InterventionTriggerOut(BaseModel):
    code: str
    severity: str
    message: str
    action: str


class InterventionStatusOut(BaseModel):
    intervention_required: bool = False
    triggers: list[InterventionTriggerOut] = Field(default_factory=list)
    recommended_action: str = ""


class UsageDayOut(BaseModel):
    day: str
    cost_usd: float
    row_count: int


class UsageBreakdownOut(BaseModel):
    key: str
    cost_usd: float
    row_count: int


class UsagePeriodOut(BaseModel):
    """Effective automation spend for a calendar or rolling window."""

    cost_usd: float
    row_count: int
    run_count: int
    days_with_data: int
    avg_per_day_usd: float | None = None
    cost_per_run_usd: float | None = None


class UsageProjectionsOut(BaseModel):
    """Forward-looking estimates from recent daily spend."""

    avg_daily_usd: float
    projected_weekly_usd: float
    projected_monthly_usd: float
    active_lane_count: int
    projected_weekly_per_lane_usd: float | None = None


class UsageSummaryOut(BaseModel):
    total_cost_usd: float
    total_estimated_cost_usd: float = 0.0
    total_effective_cost_usd: float = 0.0
    usage_row_count: int
    total_decisions: int
    cost_per_decision: float | None = None
    estimated_cost_per_decision: float | None = None
    last_7_days: UsagePeriodOut | None = None
    last_30_days: UsagePeriodOut | None = None
    this_week: UsagePeriodOut | None = None
    this_month: UsagePeriodOut | None = None
    projections: UsageProjectionsOut | None = None
    by_day: list[UsageDayOut] = Field(default_factory=list)
    by_model: list[UsageBreakdownOut] = Field(default_factory=list)
    by_run_type: list[UsageBreakdownOut] = Field(default_factory=list)
    by_lane: list[UsageBreakdownOut] = Field(default_factory=list)


class AutomationContextOut(BaseModel):
    lane_id: int
    lane_name: str
    lane_role: str
    plan_version: str
    agent_plan: "AgentPlanOut | None" = None
    strategy: StrategyOut
    manual_notes: list[ManualNoteOut]
    recent_runs: list[RunSummaryOut]
    recent_decisions: list[DecisionSummaryOut]
    simulated_portfolio: SimulatedPortfolioOut
    safety: SafetySnapshotOut
    cooldowns: dict[str, SymbolCooldownOut] = Field(default_factory=dict)
    check_needed: bool = False
    market_signals: list[MarketSignalOut] = Field(default_factory=list)
    valid_run_types: list[str] = Field(default_factory=list)
    data_freshness: list[DataSourceFreshnessOut] = Field(default_factory=list)
    freshness_checks: DataFreshnessChecksOut | None = None
    recent_news: list[NewsEventOut] = Field(default_factory=list)
    market_input_bundle: MarketInputBundleOut | None = None
    intervention_status: InterventionStatusOut | None = None
    usage_budget: "UsageBudgetOut | None" = None
    lane_turn: "LaneTurnOut | None" = None
    symbol_discovery: "SymbolDiscoveryOut | None" = None


class SymbolDiscoveryOut(BaseModel):
    enabled: bool
    max_per_run: int
    core_watchlist: list[str] = Field(default_factory=list)
    candidate_pool: list[str] = Field(default_factory=list)
    allowed_symbols: list[str] = Field(default_factory=list)
    pending_proposals: list["SymbolProposalOut"] = Field(default_factory=list)
    message: str = ""


class SymbolProposalIn(BaseModel):
    symbol: str
    thesis: str
    source: str = "manual_scout"
    score: float | None = Field(None, ge=0, le=1)
    tags: list[str] = Field(default_factory=list)


class SymbolProposalsImportRequest(BaseModel):
    proposals: list[SymbolProposalIn]
    scout_run_id: str | None = None


class SymbolProposalsImportResponse(BaseModel):
    inserted: int
    updated: int
    skipped: int
    proposals: list["SymbolProposalOut"] = Field(default_factory=list)


class SymbolProposalOut(BaseModel):
    id: int
    symbol: str
    status: str
    source: str
    thesis: str
    score: float | None = None
    tags: str | None = None
    scout_run_id: str | None = None
    created_at: str
    updated_at: str
    promoted_at: str | None = None


class SymbolProposalPromoteRequest(BaseModel):
    proposal_ids: list[int] | None = None
    symbols: list[str] | None = None
    enable_discovery: bool = True
    discovery_max_per_run: int | None = Field(None, ge=0, le=10)
    update_lanes: bool = True


class SymbolProposalPromoteResponse(BaseModel):
    strategy_version: str
    added_to_allowed: list[str] = Field(default_factory=list)
    added_to_discovery_pool: list[str] = Field(default_factory=list)
    lanes_updated: int = 0
    promoted: list[SymbolProposalOut] = Field(default_factory=list)
    message: str = ""


class SymbolProposalAutoPromoteRequest(BaseModel):
    min_score: float = Field(0.65, ge=0, le=1)
    max_symbols: int = Field(8, ge=1, le=25)
    enable_discovery: bool = True
    discovery_max_per_run: int = Field(2, ge=0, le=10)
    update_lanes: bool = True


class LaneTurnOut(BaseModel):
    sequential_mode: bool
    granted: bool
    lane_id: int
    holder_lane_id: int | None = None
    holder_since: str | None = None
    next_lane_id: int | None = None
    retry_after_seconds: int | None = None
    message: str = ""


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
    estimated_cost_usd: float | None = None
    usage_import_key: str | None = None
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
    estimated_cost_usd: float | None = None
    effective_cost_usd: float | None = None
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


class DashboardLoginRequest(BaseModel):
    password: str


class DashboardLoginResponse(BaseModel):
    token: str
    expires_at: str


class DashboardLogoutResponse(BaseModel):
    revoked: bool
    message: str


class AuthStatusOut(BaseModel):
    dashboard_login_required: bool
    read_key_required: bool


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
    message: str
    alert_id: int | None = None
    summary: ReconciliationSummaryOut | None = None


class AlertOut(BaseModel):
    id: int
    alert_type: str
    severity: str
    status: str
    title: str
    message: str
    entity_type: str | None = None
    entity_id: str | None = None
    run_id: int | None = None
    payload: dict | None = None
    created_at: str
    acknowledged_at: str | None = None
    resolved_at: str | None = None


class AlertStatusUpdate(BaseModel):
    status: str


class LivePromotionRequestResponse(BaseModel):
    promotion_token: str
    expires_at: str
    preflight_ready: bool
    message: str


class LivePromotionApproveRequest(BaseModel):
    promotion_token: str
    approved_by: str | None = None


class LivePromotionRequestOut(BaseModel):
    id: int
    status: str
    requested_at: str
    approved_at: str | None = None
    expires_at: str
    approved_by: str | None = None


class LivePromotionStatusOut(BaseModel):
    latest_request: LivePromotionRequestOut | None = None
    preflight_ready: bool
    live_trading_allowed: bool


class RetentionRunRequest(BaseModel):
    keep_runs_days: int = 90
    keep_snapshots_days: int = 180
    keep_usage_days: int = 180


class RetentionRunOut(BaseModel):
    runs_deleted: int
    snapshots_deleted: int
    usage_deleted: int
    resolved_alerts_deleted: int
    message: str


class MaintenanceRunOut(BaseModel):
    vacuum_ran: bool
    analyze_ran: bool
    snapshot_id: int
    file_size_bytes: int
    message: str


class DbSizeSnapshotOut(BaseModel):
    id: int
    snapshot_at: str
    file_size_bytes: int
    row_counts: dict[str, int]
    backup_size_bytes: int | None = None


class StrategyPerformanceSliceOut(BaseModel):
    key: str
    count: int
    avg_confidence: float | None = None


class StrategyPerformanceOut(BaseModel):
    strategy_version: str | None = None
    since: str | None = None
    run_count: int
    decision_count: int
    simulated_trades: int
    passive_decisions: int
    avg_confidence: float | None = None
    equity_change_usd: float | None = None
    by_action: list[StrategyPerformanceSliceOut] = Field(default_factory=list)
    available_strategy_versions: list[str] = Field(default_factory=list)


class QuoteOut(BaseModel):
    symbol: str
    price_usd: float
    source: str
    updated_at: str


class CursorUsageImportResponse(BaseModel):
    inserted: int
    linked: int
    skipped: int = 0
    relinked: "UsageRelinkOut | None" = None


class UsageRelinkOut(BaseModel):
    exact_usage_linked: int = 0
    fuzzy_usage_linked: int = 0
    runs_cursor_run_id_backfilled: int = 0
    scout_runs_created: int = 0
    remaining_unlinked: int = 0


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


class AgentPlanSyncItemOut(BaseModel):
    version: str
    name: str
    status: str
    message: str


class AgentPlanSyncResponse(BaseModel):
    imported: int
    updated: int
    unchanged: int
    errors: list[str] = Field(default_factory=list)
    items: list[AgentPlanSyncItemOut] = Field(default_factory=list)


class SymbolMemorySummaryOut(BaseModel):
    symbol: str
    last_action: str | None = None
    last_buy_at: str | None = None
    last_sell_at: str | None = None
    last_run_id: int | None = None
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    realized_pnl_usd: float = 0
    unrealized_pnl_usd: float | None = None
    risk_notes: list[str] = Field(default_factory=list)
    updated_at: str


class SymbolMemoryOut(BaseModel):
    symbol: str
    lane_id: int | None = None
    summary: SymbolMemorySummaryOut | None = None
    cooldown: SymbolCooldownOut | None = None
    position: SimulatedPositionOut | None = None
    portfolio_total_equity: float
    recent_decisions: list[DecisionSummaryOut] = Field(default_factory=list)
    related_notes: list[ManualNoteOut] = Field(default_factory=list)
    recent_signals: list[MarketSignalOut] = Field(default_factory=list)
    recent_news: list[NewsEventOut] = Field(default_factory=list)


class PortfolioSnapshotOut(BaseModel):
    id: int
    lane_id: int | None = None
    snapshot_at: str
    run_id: int | None
    cash_usd: float
    positions_value_usd: float
    total_equity_usd: float
    unrealized_pnl_usd: float | None
    source: str
    created_at: str


class PortfolioSnapshotSummaryOut(BaseModel):
    snapshot_count: int
    first_snapshot_at: str
    last_snapshot_at: str
    first_equity_usd: float
    last_equity_usd: float
    min_equity_usd: float
    max_equity_usd: float
    change_usd: float
    change_pct: float
    last_run_id: int | None
    last_unrealized_pnl_usd: float | None = None


class TimelineEventOut(BaseModel):
    at: str
    event_type: str
    title: str
    detail: str
    run_id: int | None = None
    symbol: str | None = None
    meta: dict = Field(default_factory=dict)


class UsageBudgetOut(BaseModel):
    daily_budget_usd: float
    monthly_budget_usd: float
    daily_spent_usd: float
    monthly_spent_usd: float
    daily_remaining_usd: float
    monthly_remaining_usd: float
    daily_exceeded: bool
    monthly_exceeded: bool
    budget_ok: bool
    run_type_budget_usd: dict[str, float] = Field(default_factory=dict)
    run_type_token_limits: dict[str, int] = Field(default_factory=dict)


class RunBudgetCheckOut(BaseModel):
    run_type: str
    expected_budget_usd: float
    actual_cost_usd: float | None = None
    expected_token_limit: int
    actual_tokens: int | None = None
    budget_exceeded: bool
    message: str


class DailyRollupOut(BaseModel):
    rollup_date: str
    run_count: int
    completed_runs: int
    failed_runs: int
    decision_count: int
    simulated_trades: int
    live_trades: int
    passive_decisions: int
    avg_confidence: float | None = None
    total_cost_usd: float
    alert_count: int
    equity_change_usd: float | None = None
    runs_by_strategy: dict[str, int] = Field(default_factory=dict)


class RollupRunOut(BaseModel):
    upserted_days: int
    message: str


class CompactPayloadOut(BaseModel):
    id: int
    entity_type: str
    entity_id: str
    summary: str
    byte_size: int
    truncated: bool
    is_compressed: bool
    updated_at: str
    full_payload: str | None = None


class CompactPayloadStoreRequest(BaseModel):
    entity_type: str
    entity_id: str
    payload: dict | str
    summary: str | None = None


class BacktestReplayRowOut(BaseModel):
    decision_id: int
    run_id: int
    run_at: str
    strategy_version: str | None
    symbol: str
    original_action: str
    alternate_action: str
    confidence: float | None
    amount_usd: float | None
    changed: bool
    reason: str


class BacktestReplayOut(BaseModel):
    strategy_version: str | None = None
    since: str | None = None
    alternate_max_order_usd: float | None = None
    require_min_confidence: float | None = None
    total_decisions: int
    would_change_count: int
    blocked_by_cap_count: int
    rows: list[BacktestReplayRowOut] = Field(default_factory=list)


class StrategyCompareVersionOut(BaseModel):
    key: str
    kind: str
    run_count: int
    decision_count: int
    simulated_trades: int
    avg_confidence: float | None = None
    equity_change_usd: float | None = None
    total_cost_usd: float


class StrategyCompareOut(BaseModel):
    since: str | None = None
    strategy_versions: list[StrategyCompareVersionOut] = Field(default_factory=list)
    plan_versions: list[StrategyCompareVersionOut] = Field(default_factory=list)


class RunLinkedOrderOut(BaseModel):
    order_id: str
    symbol: str
    side: str
    status: str
    linked: bool


class RunUsageSummaryOut(BaseModel):
    model: str | None = None
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cursor_run_id: str | None = None


class RunAuditOut(BaseModel):
    run_id: int
    linked_orders: list[RunLinkedOrderOut] = Field(default_factory=list)
    unmatched_order_ids: list[str] = Field(default_factory=list)
    usage_summary: RunUsageSummaryOut | None = None
    safety_snapshot: SafetySnapshotOut | None = None
    preflight_ready: bool = False
    preflight_checks: list[dict] = Field(default_factory=list)
    inputs_summary: dict = Field(default_factory=dict)


class MobileStatusOut(BaseModel):
    strategy_mode: str
    trading_enabled: bool
    kill_switch: bool
    total_equity_usd: float
    open_alerts: int
    last_run_at: str | None
    last_run_status: str | None
    preflight_ready: bool
    budget_ok: bool
    live_lane_id: int | None = None
    live_lane_name: str | None = None


class LaneOut(BaseModel):
    id: int
    name: str
    strategy_version: str
    plan_version: str
    lane_role: str
    status: str
    initial_cash_usd: float
    created_at: str
    updated_at: str


class LaneCreate(BaseModel):
    name: str
    strategy_version: str
    plan_version: str
    lane_role: str | None = "research"
    initial_cash_usd: float | None = None


class LaneUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    strategy_version: str | None = None
    plan_version: str | None = None


class LaneBaselinePosition(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float = Field(ge=0)


class LanePromoteRequest(BaseModel):
    """Optional Robinhood baseline so shadow lanes restart from the live starting point."""

    cash_usd: float | None = Field(None, ge=0)
    positions: list[LaneBaselinePosition] = Field(default_factory=list)
    sync_other_lanes: bool = True
    clear_symbol_memory: bool = True


class LanePromoteSyncOut(BaseModel):
    lane_id: int
    cash_usd: float
    positions: int
    message: str = ""


class LanePromoteResponse(BaseModel):
    lane: LaneOut
    message: str
    previous_live_lane_id: int | None = None
    live_strategy_version: str | None = None
    baseline_cash_usd: float | None = None
    synced_lanes: list[LanePromoteSyncOut] = Field(default_factory=list)


class LaneCompareRowOut(BaseModel):
    lane_id: int
    name: str
    strategy_version: str
    plan_version: str
    lane_role: str
    status: str
    run_count: int
    completed_runs: int
    decision_count: int
    simulated_trades: int
    avg_confidence: float | None = None
    equity_change_usd: float | None = None
    total_cost_usd: float


class LaneCompareOut(BaseModel):
    since: str | None = None
    lanes: list[LaneCompareRowOut] = Field(default_factory=list)


class LaneResetResponse(BaseModel):
    lane_id: int
    positions_cleared: int
    cash_usd: float
    message: str


class LaneLivePeriodOut(BaseModel):
    id: int
    lane_id: int
    lane_name: str
    strategy_version: str
    plan_version: str
    started_at: str
    ended_at: str | None = None
    is_current: bool = False
    snapshot_count: int = 0
    run_count: int = 0
    real_order_count: int = 0
    equity_change_usd: float | None = None


class LiveTradingSnapshotOut(BaseModel):
    snapshot_at: str
    total_equity_usd: float
    lane_id: int
    lane_name: str
    period_id: int
    is_handoff: bool = False


class LiveTradingHistoryOut(BaseModel):
    current_live_lane_id: int | None = None
    current_live_lane_name: str | None = None
    periods: list[LaneLivePeriodOut] = Field(default_factory=list)
    combined_snapshots: list[LiveTradingSnapshotOut] = Field(default_factory=list)
    combined_equity_change_usd: float | None = None
    total_real_orders: int = 0
    description: str = (
        "Stitched equity from each lane while it was live. "
        "Past live lanes keep their full history when demoted to shadow."
    )
