#!/usr/bin/env bash
# Bootstrap ticker-explorer lane + discovery-enabled strategy on the MTA-Lab API.
#
# Usage:
#   export MTA_API_BASE=https://mta-api.matthewgtran.com
#   export MTA_WRITE_API_KEY=...
#   ./api/scripts/setup_explorer_lane.sh
#
# Safe to re-run: skips lane creation if ticker-explorer already exists.
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

EXPLORER_RULES="$(STRATEGY_JSON="${STRATEGY_JSON}" python3 - <<'PY'
import json, os
ctx = json.loads(os.environ["STRATEGY_JSON"])
rules = ctx["strategy"]["rules"]
anchors = ["SPY", "QQQ"]
seed = [
    "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "AMD", "NFLX", "JPM", "XOM", "UNH", "COST", "DIS", "CRM", "INTC", "AVGO",
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
    "max_order_usd": rules.get("max_order_usd", 500),
    "max_daily_trades": max(rules.get("max_daily_trades", 3), 5),
    "max_daily_notional_usd": max(rules.get("max_daily_notional_usd", 1500), 2500),
    "require_review_before_place": rules.get("require_review_before_place", True),
    "symbol_cooldown_hours": rules.get("symbol_cooldown_hours", 24),
}
print(json.dumps({"rules": rules_out}))
PY
)"

echo "==> Create explorer strategy version (fork active strategy)"
NEW_STRATEGY="$(curl -fsS -X PATCH "${API_BASE}/api/automation/strategy" "${auth[@]}" -d "${EXPLORER_RULES}")"
STRATEGY_VERSION="$(python3 -c "import json,sys; print(json.load(sys.stdin)['version'])" <<<"${NEW_STRATEGY}")"
echo "    strategy_version=${STRATEGY_VERSION}"

echo "==> Check for existing ticker-explorer lane"
LANES_JSON="$(curl -fsS "${API_BASE}/api/admin/lanes" "${auth[@]}")"
EXISTING_ID="$(LANES_JSON="${LANES_JSON}" python3 - <<'PY'
import json, os
lanes = json.loads(os.environ["LANES_JSON"])
for lane in lanes:
    if lane.get("name") == "ticker-explorer":
        print(lane["id"])
        break
PY
)"

if [[ -n "${EXISTING_ID}" ]]; then
  EXPLORER_LANE_ID="${EXISTING_ID}"
  echo "==> Lane ticker-explorer already exists (id=${EXPLORER_LANE_ID}); updating strategy + plan"
  curl -fsS -X PATCH "${API_BASE}/api/admin/lanes/${EXPLORER_LANE_ID}" "${auth[@]}" \
    -d "{\"strategy_version\":\"${STRATEGY_VERSION}\",\"plan_version\":\"v4\"}" | python3 -m json.tool
else
  echo "==> Create lane ticker-explorer (plan v4)"
  LANE_JSON="$(curl -fsS -X POST "${API_BASE}/api/admin/lanes" "${auth[@]}" -d "{
    \"name\": \"ticker-explorer\",
    \"strategy_version\": \"${STRATEGY_VERSION}\",
    \"plan_version\": \"v4\",
    \"lane_role\": \"research\"
  }")"
  EXPLORER_LANE_ID="$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"${LANE_JSON}")"
  echo "${LANE_JSON}" | python3 -m json.tool
fi

DISCOVERY="$(curl -fsS "${API_BASE}/api/automation/context?lane_id=${EXPLORER_LANE_ID}" "${auth[@]}")"
DISCOVERY="${DISCOVERY}" python3 - <<'PY'
import json, os
ctx = json.loads(os.environ["DISCOVERY"])
sd = ctx.get("symbol_discovery") or {}
print("==> Explorer lane discovery policy")
print(f"    enabled={sd.get('enabled')}")
print(f"    max_per_run={sd.get('max_per_run')}")
print(f"    core_watchlist={sd.get('core_watchlist')}")
print(f"    candidate_pool_count={len(sd.get('candidate_pool') or [])}")
PY

cat <<EOF

==> Setup complete

Explorer lane id: ${EXPLORER_LANE_ID}
Strategy version: ${STRATEGY_VERSION}
Plan: v4

Next steps (see docs/automation/ticker-exploration-setup.md):

1. Create Cursor automation mta-explorer
   - Paste docs/automation/explorer-prompt.md
   - Set EXPLORER_LANE_ID=${EXPLORER_LANE_ID}

2. Create Cursor automation mta-ticker-scout (weekly)
   - Paste docs/automation/ticker-scout-prompt.md
   - Use update_lanes: false on auto-promote

3. After each scout run, point explorer at the new strategy:
   curl -sS -X PATCH "${API_BASE}/api/admin/lanes/${EXPLORER_LANE_ID}" \\
     -H "X-API-Key: \$MTA_WRITE_API_KEY" \\
     -H "Content-Type: application/json" \\
     -d '{"strategy_version":"NEW_VERSION_FROM_SCOUT_RESPONSE"}'

EOF
