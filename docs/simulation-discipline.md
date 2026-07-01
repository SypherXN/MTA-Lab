# Research Mode Simulation Discipline

MTA-Lab defaults to **research mode**: the agent logs decisions and the API tracks a **simulated portfolio** with fake money. No live orders unless mode is `live`, preflight passes, and trading is explicitly enabled.

## Default behavior

- Strategy mode: `research`
- Allowed trade actions: `simulated_buy`, `simulated_sell`, `hold`, `skip`
- Simulated starting cash: `MTA_INITIAL_SIMULATED_CASH` (default $10,000)
- Portfolio snapshots recorded on each **completed** run

## Simulated trade rules

When logging `simulated_buy` or `simulated_sell`:

1. **Symbol** must be in `allowed_symbols` (strategy rules).
2. **Amount** must respect `max_order_usd` and daily notional caps.
3. **Cooldown** — do not buy a symbol still in cooldown from a prior buy.
4. **Fill price** — include `fill_price` from quotes or review when available. If omitted, the API uses the cached quote price.
5. **Shares** — computed as `amount_usd / fill_price`; cash and positions update atomically on run commit.

## Fill assumptions

| Field | Rule |
|-------|------|
| `fill_price` | Required for accurate P&L; prefer quote at decision time |
| `amount_usd` | Notional USD for the simulated leg |
| Slippage | Not modeled — fills at stated price |
| Partial fills | Not modeled — full notional applied |

## Paper P&L tracking

- **Cash** — debited on buy, credited on sell (proceeds = shares × fill price).
- **Positions** — average cost basis updated on buys; realized P&L on sells.
- **Unrealized P&L** — mark-to-market using latest quote cache prices.
- **Equity curve** — `portfolio_snapshots` on each completed run; dashboard charts from `GET /api/dashboard/portfolio/snapshots?lane_id=`.
- **Multi-lane** — each simulation lane has its own cash, positions, and snapshots. Select lane in the dashboard portfolio dropdown.

## Actions to avoid in research mode

- Do not use `buy` / `sell` (live actions) unless `safety.trading_allowed` is true.
- Do not log simulated trades on **failed** runs.
- Do not bypass safety budget — violations block trade application when trade actions are present.

## Promotion path

Research → live requires:

1. Passing `GET /api/automation/preflight`
2. `POST /api/admin/live-promotion/request` → operator approval token
3. `POST /api/admin/live-promotion/approve` with token

Until then, keep using `simulated_buy` / `simulated_sell` for all trade logging.

## Related docs

- [Safety gates](../safety-gates.md)
- [Intervention protocol](../intervention-protocol.md)
- [Multi-lane simulation](./automation/multi-lane-simulation.md)
- [Research prompt](./automation/research-prompt.md)
