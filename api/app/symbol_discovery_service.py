"""Optional symbol discovery — expand daily research beyond the core watchlist."""

from app.schemas import StrategyOut, SymbolDiscoveryOut


def _upper_set(symbols: list[str]) -> set[str]:
    return {s.upper() for s in symbols if s and str(s).strip()}


def validate_discovery_rules(rules) -> None:
    allowed = _upper_set(rules.allowed_symbols)
    if not allowed:
        raise ValueError("allowed_symbols must not be empty")

    watchlist = rules.watchlist or rules.allowed_symbols
    for symbol in watchlist:
        if symbol.upper() not in allowed:
            raise ValueError(f"watchlist symbol {symbol} is not in allowed_symbols")

    for symbol in rules.discovery_pool:
        if symbol.upper() not in allowed:
            raise ValueError(f"discovery_pool symbol {symbol} is not in allowed_symbols")

    if rules.discovery_max_per_run < 0 or rules.discovery_max_per_run > 10:
        raise ValueError("discovery_max_per_run must be between 0 and 10")


def build_symbol_discovery(strategy: StrategyOut) -> SymbolDiscoveryOut:
    rules = strategy.rules
    core_watchlist = list(rules.watchlist or rules.allowed_symbols)
    allowed = _upper_set(rules.allowed_symbols)
    watchset = _upper_set(core_watchlist)

    if rules.discovery_pool:
        candidate_pool = [
            s
            for s in rules.discovery_pool
            if s.upper() in allowed and s.upper() not in watchset
        ]
    else:
        candidate_pool = [s for s in rules.allowed_symbols if s.upper() not in watchset]

    enabled = bool(rules.symbol_discovery_enabled and candidate_pool and rules.discovery_max_per_run > 0)

    if not rules.symbol_discovery_enabled:
        message = "Symbol discovery is disabled; analyze the core watchlist only."
    elif not candidate_pool:
        message = (
            "Discovery is enabled but candidate_pool is empty. "
            "Add symbols to allowed_symbols (or discovery_pool) beyond the watchlist."
        )
    elif rules.discovery_max_per_run <= 0:
        message = "Discovery is enabled but discovery_max_per_run is 0."
    else:
        message = (
            f"May optionally research up to {rules.discovery_max_per_run} extra symbol(s) "
            f"from candidate_pool; trades only on allowed_symbols."
        )

    return SymbolDiscoveryOut(
        enabled=enabled,
        max_per_run=rules.discovery_max_per_run,
        core_watchlist=core_watchlist,
        candidate_pool=candidate_pool,
        allowed_symbols=list(rules.allowed_symbols),
        message=message,
    )
