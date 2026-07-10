# Cursor Automation Setup

## Prerequisites

1. Robinhood Agentic Trading access and OAuth for `https://agent.robinhood.com/mcp/trading`
2. MTA-Lab API deployed and reachable over HTTPS
3. Write API key configured on the API (`MTA_WRITE_API_KEY`)
4. Agent plans synced from repo (`python3 api/scripts/sync_plans_from_repo.py`) — see [agent-plans.md](../agent-plans.md)

## Create the automation

1. Open [cursor.com/automations](https://cursor.com/automations)
2. Create a new automation named `mta-research` (or per-lane names for multi-lane — see [multi-lane-simulation.md](./multi-lane-simulation.md))
3. Trigger: scheduled cron (`0 9 * * 1-5` to start)
4. Model: Composer 2.5
5. Repository: none
6. Enable tools:
   - Robinhood Trading MCP
   - MCP/HTTP access to your MTA-Lab API if configured as a custom MCP; otherwise include API URLs in the prompt
7. Paste the prompt from [research-prompt.md](./research-prompt.md)
8. Replace `{API_BASE}`, `{WRITE_API_KEY}`, and `{N}` (lane id) with your deployed values

### Multi-lane

- Set `MTA_LANE_ID` in the automation environment or prompt (e.g. `1`, `2`, `3`).
- Pass `?lane_id=N` on plan, context, memory, and `"lane_id": N` on run POST.
- On OCI micro VM, enable `MTA_SEQUENTIAL_LANES=true` on the API so only one lane runs per cycle.

## Robinhood MCP

Add in Cursor Settings → Tools & MCPs:

```json
{
  "mcpServers": {
    "robinhood-trading": {
      "url": "https://agent.robinhood.com/mcp/trading"
    }
  }
}
```

Complete OAuth once on desktop before enabling the scheduled automation.

## Validation checklist

- [ ] `GET /api/automation/context` returns research mode
- [ ] `GET /api/automation/plan?lane_id=1` returns expected plan version
- [ ] Automation run logs a completed research run with correct `lane_id`
- [ ] Dashboard shows the new run, lane badge, and decisions
- [ ] Agent Plans section expands to show run order and scoring rules
- [ ] `review_equity_order` works without placing a trade
- [ ] Live `place_equity_order` remains blocked until strategy mode is `live`

## Going live later

Only after multiple successful research runs:

1. Fund the Robinhood Agentic account with a small amount
2. Pass preflight and promote a lane via `POST /api/admin/lanes/{id}/promote-to-live`
   - Include Robinhood `cash_usd` + `positions` in the body so other lanes sync paper books to the same starting point
3. Keep `kill_switch=false` only when you intend to allow trading
4. Tighten schedule and monitor Robinhood push notifications

See [safety-gates.md](../safety-gates.md) and [multi-lane-simulation.md](./multi-lane-simulation.md).

## Related docs

- [research-prompt.md](./research-prompt.md) — standing automation instructions
- [ticker-scout-prompt.md](./ticker-scout-prompt.md) — manual market scout → symbol proposals
- [multi-cadence.md](./multi-cadence.md) — separate schedules per run type
- [agent-plans.md](../agent-plans.md) — editing plans in GitHub
