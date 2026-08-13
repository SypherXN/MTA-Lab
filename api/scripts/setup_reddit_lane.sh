#!/usr/bin/env bash
# Bootstrap reddit-research lane + social-discovery strategy on the MTA-Lab API.
#
# Usage:
#   export MTA_API_BASE=https://mta-api.matthewgtran.com
#   export MTA_WRITE_API_KEY=...
#   ./api/scripts/setup_reddit_lane.sh
#
# Safe to re-run: updates reddit-research if it already exists.
set -euo pipefail

API_BASE="${MTA_API_BASE:-https://mta-api.matthewgtran.com}"
API_BASE="${API_BASE%/}"
KEY="${MTA_WRITE_API_KEY:?Set MTA_WRITE_API_KEY}"

auth=(-H "X-API-Key: ${KEY}" -H "Content-Type: application/json")

echo "==> API: ${API_BASE}"

echo "==> Sync agent plans from repo"
curl -fsS -X POST "${API_BASE}/api/admin/plans/sync-from-repo" "${auth[@]}" | python3 -m json.tool || true

echo "==> Load active strategy"
STRATEGY_JSON="$(curl -fsS "${API_BASE}/api/automation/context?lane_id=1" "${auth[@]}")"

REDDIT_RULES="$(STRATEGY_JSON="${STRATEGY_JSON}" python3 - <<'PY'
import json, os
ctx = json.loads(os.environ["STRATEGY_JSON"])
rules = ctx["strategy"]["rules"]
anchors = ["SPY", "QQQ"]
seed = [
    "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "AMD", "NFLX", "JPM", "XOM", "UNH", "COST", "DIS", "CRM", "INTC", "AVGO",
    "PLTR", "SOFI", "COIN", "HOOD", "SMCI", "ARM", "GME", "MSTR", "RKLB",
    "TSM", "MU", "ORCL", "NOW", "CRWD", "PANW", "UBER", "SHOP", "BA",
]
allowed = []
seen = set()
for s in seed:
    u = s.upper()
    if u not in seen:
        allowed.append(u)
        seen.add(u)
watchset = {s.upper() for s in anchors}
pool = [s for s in allowed if s not in watchset]
rules_out = {
    "allowed_symbols": allowed,
    "watchlist": anchors,
    "discovery_pool": pool,
    "symbol_discovery_enabled": True,
    "discovery_max_per_run": 8,
    "max_order_usd": min(float(rules.get("max_order_usd", 500)), 400),
    "max_daily_trades": max(int(rules.get("max_daily_trades", 3)), 6),
    "max_daily_notional_usd": max(float(rules.get("max_daily_notional_usd", 1500)), 2000),
    "require_review_before_place": rules.get("require_review_before_place", True),
    "symbol_cooldown_hours": rules.get("symbol_cooldown_hours", 24),
}
print(json.dumps({"rules": rules_out}))
PY
)"

echo "==> Create reddit strategy version (fork active strategy)"
NEW_STRATEGY="$(curl -fsS -X PATCH "${API_BASE}/api/automation/strategy" "${auth[@]}" -d "${REDDIT_RULES}")"
STRATEGY_VERSION="$(python3 -c "import json,sys; print(json.load(sys.stdin)['version'])" <<<"${NEW_STRATEGY}")"
echo "    strategy_version=${STRATEGY_VERSION}"

echo "==> Check for existing reddit-research lane"
LANES_JSON="$(curl -fsS "${API_BASE}/api/admin/lanes" "${auth[@]}")"
EXISTING_ID="$(LANES_JSON="${LANES_JSON}" python3 - <<'PY'
import json, os
lanes = json.loads(os.environ["LANES_JSON"])
for lane in lanes:
    if lane.get("name") == "reddit-research":
        print(lane["id"])
        break
PY
)"

if [[ -n "${EXISTING_ID}" ]]; then
  REDDIT_LANE_ID="${EXISTING_ID}"
  echo "==> Lane reddit-research already exists (id=${REDDIT_LANE_ID}); updating strategy + plan"
  curl -fsS -X PATCH "${API_BASE}/api/admin/lanes/${REDDIT_LANE_ID}" "${auth[@]}" \
    -d "{\"strategy_version\":\"${STRATEGY_VERSION}\",\"plan_version\":\"v5\"}" | python3 -m json.tool
else
  echo "==> Create lane reddit-research (plan v5)"
  LANE_JSON="$(curl -fsS -X POST "${API_BASE}/api/admin/lanes" "${auth[@]}" -d "{
    \"name\": \"reddit-research\",
    \"strategy_version\": \"${STRATEGY_VERSION}\",
    \"plan_version\": \"v5\",
    \"lane_role\": \"research\"
  }")"
  REDDIT_LANE_ID="$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"${LANE_JSON}")"
  echo "${LANE_JSON}" | python3 -m json.tool
fi

PLAN="$(curl -fsS "${API_BASE}/api/automation/plan?lane_id=${REDDIT_LANE_ID}" "${auth[@]}")"
PLAN="${PLAN}" python3 - <<'PY'
import json, os
plan = json.loads(os.environ["PLAN"])
print("==> Reddit lane plan")
print(f"    version={plan.get('version')}")
print(f"    name={plan.get('name')}")
print(f"    has_reddit_step={'ingest_reddit' in [s.get('action') for s in plan.get('run_order') or []]}")
PY

cat <<EOF

==> Setup complete

Reddit lane id: ${REDDIT_LANE_ID}
Strategy version: ${STRATEGY_VERSION}
Plan: v5

Next steps (see docs/automation/reddit-research-setup.md):

1. Create Cursor automation mta-reddit
   - Paste docs/automation/reddit-prompt.md
   - Set REDDIT_LANE_ID=${REDDIT_LANE_ID}

2. Optional VM warmup:
   python3 api/scripts/ingest_reddit.py

EOF
