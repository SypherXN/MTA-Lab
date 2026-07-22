# Cost Tracking

MTA-Lab tracks Cursor usage in two ways:

## 1. Per-run metadata

Each automation POST may include:

```json
"usage": {
  "model": "composer-2.5",
  "cursor_run_id": "bc-abc123",
  "cost_usd": 0.08,
  "input_tokens": 42000,
  "output_tokens": 3500
}
```

This is stored on the run (`usage_json`) and in the `cursor_usage` table when `cost_usd` is present.

## 2. Dashboard CSV reconciliation

Cursor billing is often split across multiple events per automation run. Automation rows in the usage-events export use a different CSV shape than IDE chat rows.

**Automation rows** have `Cloud Agent ID` (`bc-…`) and `Automation ID` populated. **IDE rows** leave those columns blank. Costs may show as `Included` (subscription pool) rather than a dollar amount.

To backfill automation usage:

1. Export usage CSV from [cursor.com/dashboard/usage](https://cursor.com/dashboard/usage)
2. Run (defaults to **automations only**):

```bash
cd api
python scripts/import_cursor_usage.py /path/to/usage-events.csv \
  --api-url https://your-api.example.com \
  --api-key YOUR_WRITE_KEY
```

Dry-run first:

```bash
python scripts/import_cursor_usage.py /path/to/usage-events.csv \
  --api-url https://your-api.example.com \
  --api-key YOUR_WRITE_KEY \
  --dry-run
```

Import IDE + automation rows:

```bash
python scripts/import_cursor_usage.py /path/to/usage-events.csv \
  --api-url https://your-api.example.com \
  --api-key YOUR_WRITE_KEY \
  --no-automations-only
```

3. Rows link to automation runs via `Cloud Agent ID` → `cursor_run_id` when the run logged the same id.

## Admin endpoint

`POST /api/admin/cursor-usage/import`

Requires `X-API-Key`. Accepts:

```json
{
  "rows": [
    {
      "cursor_run_id": "bc-abc123",
      "run_id": 12,
      "model": "composer-2.5",
      "cost_usd": 0.08,
      "input_tokens": 42000,
      "output_tokens": 3500
    }
  ]
}
```

Dashboard stats aggregate billed `cost_usd` and imputed `estimated_cost_usd` into **effective cost** (`billed` when present, otherwise token estimate). The **Cost Dashboard** shows effective totals, daily spend, and breakdowns by model and run type.

## Token-based effective cost (Included rows)

When CSV rows show `Included` / `Free`, `cost_usd` is stored as **0** but `estimated_cost_usd` is computed from tokens using imputed list rates in `api/app/cursor_pricing.py`:

| Model | Input ($/1M tok) | Output ($/1M tok) |
|-------|------------------|-------------------|
| `composer-2.5` | $0.25 | $1.00 |
| `composer-2.5-fast` | $0.15 | $0.60 |
| `auto` | $0.30 | $1.20 |
| default / unknown | $0.30 | $1.20 |

**Effective cost** = billed amount when &gt; 0, else estimated.

Calibrate rates from your on-demand overage rows in the usage CSV export, then edit `MODEL_RATES` in `cursor_pricing.py`.

Example: a lane run with 343k input + 7.7k output tokens on `composer-2.5` → ~**$0.09** effective (even when billed as Included).

See [dashboard/README.md](../dashboard/README.md).
