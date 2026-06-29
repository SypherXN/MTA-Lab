# Cursor Automation Setup

## Prerequisites

1. Robinhood Agentic Trading access and OAuth for `https://agent.robinhood.com/mcp/trading`
2. MTA-Lab API deployed and reachable over HTTPS
3. Write API key configured on the API (`MTA_WRITE_API_KEY`)

## Create the automation

1. Open [cursor.com/automations](https://cursor.com/automations)
2. Create a new automation named `mta-research`
3. Trigger: scheduled cron (`0 9 * * 1-5` to start)
4. Model: Composer 2.5
5. Repository: none
6. Enable tools:
   - Robinhood Trading MCP
   - MCP/HTTP access to your MTA-Lab API if configured as a custom MCP; otherwise include API URLs in the prompt
7. Paste the prompt from [research-prompt.md](./research-prompt.md)
8. Replace `{API_BASE}` and `{WRITE_API_KEY}` with your deployed values

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
- [ ] Automation run logs a completed research run
- [ ] Dashboard shows the new run and decisions
- [ ] `review_equity_order` works without placing a trade
- [ ] Live `place_equity_order` remains blocked until strategy mode is `live`

## Going live later

Only after multiple successful research runs:

1. Fund the Robinhood Agentic account with a small amount
2. Update the active strategy in the database/API to `mode=live` and `trading_enabled=true`
3. Keep `kill_switch=false` only when you intend to allow trading
4. Tighten schedule and monitor Robinhood push notifications
