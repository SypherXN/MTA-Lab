VALID_RUN_TYPES = frozenset(
    {
        "daily_research",
        "signal_response",
        "post_market_review",
        "reconciliation_only",
        "live_preflight",
    }
)

DEFAULT_RUN_TYPE = "daily_research"
