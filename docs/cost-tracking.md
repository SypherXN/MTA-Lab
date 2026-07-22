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

Dashboard stats aggregate `cursor_usage.cost_usd` into `total_cursor_cost_usd`. The **Cost Dashboard** section shows daily spend and breakdowns by model and run type.

See [dashboard/README.md](../dashboard/README.md).
