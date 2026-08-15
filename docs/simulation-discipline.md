# Research Mode Simulation Discipline

MTA-Lab defaults to **research mode**: the agent logs decisions and the API tracks a **simulated portfolio** with fake money. No live orders unless mode is `live`, preflight passes, and trading is explicitly enabled.

## Default behavior

- Strategy mode: `research`
- Allowed trade actions: `simulated_buy`, `simulated_add`, `simulated_sell`, `simulated_trim`, `simulated_stop`, `simulated_take_profit`, `simulated_flatten`, `hold`, `skip`
- Options lane only (plan v6, `options_enabled`): `simulated_option_buy`, `simulated_option_sell`, `simulated_option_write`, `simulated_option_cover`
- Simulated starting cash: `MTA_INITIAL_SIMULATED_CASH` (default $10,000); options-research and DTE lanes use $5,000
- Portfolio snapshots recorded on each **completed** run

## Simulated trade rules

When logging a paper trade (`simulated_buy`, `simulated_add`, `simulated_sell`, `simulated_trim`, `simulated_stop`, `simulated_take_profit`, `simulated_flatten`):

1. **Symbol** must be in `allowed_symbols` (strategy rules).
2. **Amount** — entries/adds must respect `max_order_usd` and daily **buy** notional caps. Exits are not capped by `max_order_usd` (you may flatten a winner that grew past the cap).
3. **Cooldown** — do not buy/add a symbol still in cooldown from a prior buy.
4. **Fill price** — include `fill_price` from quotes or review when available. If omitted on a buy, the API uses the cached quote price. Sells require `fill_price`. For options, `fill_price` is **premium per share**.
5. **Shares** — computed as `amount_usd / fill_price`; cash and positions update atomically on run commit. Omit `amount_usd` on a sell to flatten the whole lot, or set `percent_of_position` (0–1) to trim.

## Paper options (options-research lane)

When `strategy.rules.options_enabled` is true:

| Action | Cash effect |
|--------|-------------|
| `simulated_option_buy` | Debit `premium × 100 × contracts` |
| `simulated_option_sell` | Credit the same on close |
| `simulated_option_write` (put) | Credit premium; reserve `strike × 100 × contracts` (CSP) |
| `simulated_option_write` (call) | Credit premium; requires 100 paper shares per contract |
| `simulated_option_cover` | Debit premium to buy back a short |

Marks use `quotes[]` keys like `OPT:NVDA:2026-08-21:180:C`. Naked short calls are rejected. Live `place_option_order` is never applied by this API.

## Fill assumptions

| Field | Rule |
|-------|------|
| `fill_price` | Required for accurate P&L; prefer quote at decision time |
| `amount_usd` | Notional USD for the simulated leg. Optional on full exits (`simulated_flatten` / stop / take-profit). |
| `percent_of_position` | Optional 0–1 fraction to sell |
| `stop_price` / `target_price` | Optional levels recorded on the decision |
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
