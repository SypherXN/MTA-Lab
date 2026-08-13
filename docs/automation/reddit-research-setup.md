# Reddit Research Lane Setup

One automation + one API lane that researches **public Reddit finance listings** through the MTA API (no login scrape).

| Piece | Name | Purpose |
|-------|------|---------|
| **Lane** | `reddit-research` | Isolated paper portfolio, plan **v5** |
| **Automation** | `mta-reddit` | Weekdays — ingest Reddit mentions, confirm with quotes, paper trades |
| **Optional cron** | `ingest_reddit.py` | Pre-fetch listings before the automation (VM) |

Main lanes stay on news/technicals. This lane is a social-sentiment challenger, still compared vs SPY on the dashboard.

---

## Phase 1 — Deploy repo artifacts

After `plans/v5.json` and the Reddit API endpoints are on `main`:

```bash
ssh ubuntu@YOUR_VM_IP
cd ~/MTA-Lab
./scripts/mta update --force
sudo systemctl restart mta-lab-api
```

Confirm plan v5 exists after sync (the setup script also syncs):

```bash
curl -sS -X POST "$API/api/admin/plans/sync-from-repo" \
  -H "X-API-Key: $WRITE_KEY"
```

---

## Phase 2 — Bootstrap lane (one command)

On the VM (write key already in `api/.env`):

```bash
cd ~/MTA-Lab
set -a && source api/.env && set +a
export MTA_API_BASE=https://mta-api.matthewgtran.com
export MTA_WRITE_API_KEY="$MTA_WRITE_API_KEY"
./api/scripts/setup_reddit_lane.sh
```

The script:

1. Syncs plans from the repo (creates **v5**)
2. Forks a strategy with a wider liquid symbol list + discovery
3. Creates lane **`reddit-research`** (or updates it if it already exists)

Re-running is safe.

---

## Phase 3 — Cursor automation

1. Create automation **`mta-reddit`**
2. Paste [reddit-prompt.md](./reddit-prompt.md)
3. Set `{REDDIT_LANE_ID}` from the setup output
4. Schedule offset from other lanes (example: weekdays 11:00)
5. Tools: Robinhood MCP + HTTP to the API

On OCI micro with `MTA_SEQUENTIAL_LANES=true`, this automation can share a similar cron — it exits early when `lane_turn.granted` is false.

---

## Optional VM pre-ingest

```cron
30 14 * * 1-5 cd /home/ubuntu/MTA-Lab/api && .venv/bin/python3 scripts/ingest_reddit.py >> data/reddit-ingest.log 2>&1
```

Or append `api/deploy/reddit-ingest.cron.example`. The automation still calls `POST /api/admin/reddit/ingest` so this is only a warmup.

---

## What the API does

| Endpoint | Role |
|----------|------|
| `GET /api/automation/reddit` | Fetch public `hot.json` listings, extract `$TICKER` / allowed-symbol mentions |
| `POST /api/admin/reddit/ingest` | Same fetch + store as news events (`source=reddit`) |
| `GET /api/automation/news?source=reddit` | Read stored mention summaries |

User-Agent is `MTA_REDDIT_USER_AGENT` (default identifies MTA-Lab). Default subs: `MTA_REDDIT_SUBREDDITS`. If `reddit.com` blocks the VM (common from cloud IPs), the API falls back to the public Arctic Shift archive.

**Out of scope:** logging into Reddit, scraping user inboxes, NSFW/CSAM, or browser automation.

---

## Checklist

| Check | Where |
|-------|--------|
| Lane exists | Dashboard → Lanes → `reddit-research` |
| Plan is v5 | Lane card / Agent Plans |
| Ingest works | `POST /api/admin/reddit/ingest` returns `mentions` |
| Automation logs `lane_id` | Dashboard runs for that lane |
| Vs SPY | Lane Comparison after a few completed runs |
