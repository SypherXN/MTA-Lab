#!/usr/bin/env bash
# Bootstrap four paper DTE option lanes (0DTE index, 0DTE reddit, 1DTE news, 1DTE reddit-loose).
#
# Usage:
#   export MTA_API_BASE=https://mta-api.matthewgtran.com
#   export MTA_WRITE_API_KEY=...
#   ./api/scripts/setup_dte_lanes.sh
#
# Requires options-research (lane 6) to already exist. Safe to re-run: updates
# matching lane names in place and does not reset paper books.
# Restores the pre-script active strategy rules afterward so global active
# is not left on a DTE variant.
set -euo pipefail

API_BASE="${MTA_API_BASE:-https://mta-api.matthewgtran.com}"
API_BASE="${API_BASE%/}"
KEY="${MTA_WRITE_API_KEY:?Set MTA_WRITE_API_KEY}"
auth=(-H "X-API-Key: ${KEY}" -H "Content-Type: application/json")

echo "==> API: ${API_BASE}"

echo "==> Sync agent plans from repo"
curl -fsS -X POST "${API_BASE}/api/admin/plans/sync-from-repo" "${auth[@]}" | python3 -m json.tool

echo "==> Load options-research (lane 6) as the options-enabled template"
LANES_JSON="$(curl -fsS "${API_BASE}/api/admin/lanes" "${auth[@]}")"
OPTIONS_ID="$(LANES_JSON="${LANES_JSON}" python3 - <<'PY'
import json, os
for lane in json.loads(os.environ["LANES_JSON"]):
    if lane.get("name") == "options-research" and lane.get("status") != "archived":
        print(lane["id"])
        break
PY
)"
if [[ -z "${OPTIONS_ID}" ]]; then
  echo "error: options-research lane not found. Run ./api/scripts/setup_options_lane.sh first." >&2
  exit 1
fi

TEMPLATE="$(curl -fsS "${API_BASE}/api/automation/context?lane_id=${OPTIONS_ID}" "${auth[@]}")"
RESTORE_RULES="$(TEMPLATE="${TEMPLATE}" python3 - <<'PY'
import json, os
print(json.dumps({"rules": json.loads(os.environ["TEMPLATE"])["strategy"]["rules"]}))
PY
)"

python3 - <<'PY' > /tmp/mta-dte-lane-specs.json
import json
anchors = ["SPY", "QQQ"]
seed = [
    "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "AMD", "NFLX", "JPM", "XOM", "UNH", "COST", "DIS", "CRM", "INTC", "AVGO",
    "PLTR", "SOFI", "COIN", "HOOD", "SMCI", "ARM", "GME", "MSTR", "RKLB",
    "TSM", "MU", "ORCL", "CRWD", "PANW", "UBER", "SHOP", "BA", "NKE",
]
wide = []
seen = set()
for symbol in seed:
    upper = symbol.upper()
    if upper not in seen:
        wide.append(upper)
        seen.add(upper)
watchset = {s.upper() for s in anchors}
wide_pool = [s for s in wide if s not in watchset]
specs = [
    {
        "name": "odte-index",
        "plan_version": "v7",
        "cron_utc": "15 15 * * 1-5",
        "automation": "mta-odte-index",
        "allowed_symbols": ["SPY", "QQQ"],
        "watchlist": ["SPY", "QQQ"],
        "discovery_pool": [],
        "symbol_discovery_enabled": False,
        "discovery_max_per_run": 0,
        "max_order_usd": 150,
        "max_daily_trades": 4,
        "max_daily_notional_usd": 1500,
        "symbol_cooldown_hours": 4,
        "max_option_contracts": 1,
        "max_option_debit_usd": 150,
        "max_csp_notional_usd": 0,
        "min_option_dte": 0,
        "max_option_dte": 0,
    },
    {
        "name": "odte-reddit",
        "plan_version": "v8",
        "cron_utc": "15 16 * * 1-5",
        "automation": "mta-odte-reddit",
        "allowed_symbols": wide,
        "watchlist": anchors,
        "discovery_pool": wide_pool,
        "symbol_discovery_enabled": True,
        "discovery_max_per_run": 8,
        "max_order_usd": 150,
        "max_daily_trades": 4,
        "max_daily_notional_usd": 1500,
        "symbol_cooldown_hours": 4,
        "max_option_contracts": 1,
        "max_option_debit_usd": 150,
        "max_csp_notional_usd": 0,
        "min_option_dte": 0,
        "max_option_dte": 0,
    },
    {
        "name": "1dte-news",
        "plan_version": "v9",
        "cron_utc": "15 17 * * 1-5",
        "automation": "mta-1dte-news",
        "allowed_symbols": wide,
        "watchlist": anchors,
        "discovery_pool": wide_pool,
        "symbol_discovery_enabled": True,
        "discovery_max_per_run": 8,
        "max_order_usd": 150,
        "max_daily_trades": 4,
        "max_daily_notional_usd": 1500,
        "symbol_cooldown_hours": 4,
        "max_option_contracts": 1,
        "max_option_debit_usd": 150,
        "max_csp_notional_usd": 0,
        "min_option_dte": 1,
        "max_option_dte": 1,
    },
    {
        "name": "1dte-reddit-loose",
        "plan_version": "v10",
        "cron_utc": "15 18 * * 1-5",
        "automation": "mta-1dte-reddit",
        "allowed_symbols": wide,
        "watchlist": anchors,
        "discovery_pool": wide_pool,
        "symbol_discovery_enabled": True,
        "discovery_max_per_run": 8,
        "max_order_usd": 400,
        "max_daily_trades": 8,
        "max_daily_notional_usd": 5000,
        "symbol_cooldown_hours": 8,
        "max_option_contracts": 2,
        "max_option_debit_usd": 400,
        "max_csp_notional_usd": 0,
        "min_option_dte": 1,
        "max_option_dte": 1,
    },
]
print(json.dumps(specs))
PY

RESULTS=()
while IFS= read -r spec; do
  NAME="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['name'])" "${spec}")"
  PLAN="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['plan_version'])" "${spec}")"
  AUTO="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['automation'])" "${spec}")"
  CRON="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['cron_utc'])" "${spec}")"
  echo "==> Fork strategy for ${NAME} (plan ${PLAN})"
  RULES="$(TEMPLATE="${TEMPLATE}" SPEC="${spec}" python3 - <<'PY'
import json, os
rules = dict(json.loads(os.environ["TEMPLATE"])["strategy"]["rules"])
spec = json.loads(os.environ["SPEC"])
for key in (
    "allowed_symbols", "watchlist", "discovery_pool", "symbol_discovery_enabled",
    "discovery_max_per_run", "max_order_usd", "max_daily_trades",
    "max_daily_notional_usd", "symbol_cooldown_hours", "max_option_contracts",
    "max_option_debit_usd", "max_csp_notional_usd", "min_option_dte", "max_option_dte",
):
    rules[key] = spec[key]
rules["options_enabled"] = True
rules["require_review_before_place"] = True
print(json.dumps({"rules": rules}))
PY
)"
  NEW_STRATEGY="$(curl -fsS -X PATCH "${API_BASE}/api/automation/strategy" "${auth[@]}" -d "${RULES}")"
  VERSION="$(python3 -c "import json,sys; print(json.load(sys.stdin)['version'])" <<<"${NEW_STRATEGY}")"
  echo "    strategy_version=${VERSION}"

  EXISTING="$(LANES_JSON="${LANES_JSON}" NAME="${NAME}" python3 - <<'PY'
import json, os
name = os.environ["NAME"]
for lane in json.loads(os.environ["LANES_JSON"]):
    if lane.get("name") == name and lane.get("status") != "archived":
        print(lane["id"])
        break
PY
)"
  if [[ -n "${EXISTING}" ]]; then
    echo "==> Update lane ${NAME} id=${EXISTING}"
    curl -fsS -X PATCH "${API_BASE}/api/admin/lanes/${EXISTING}" "${auth[@]}" \
      -d "{\"strategy_version\":\"${VERSION}\",\"plan_version\":\"${PLAN}\"}" | python3 -m json.tool
    LANE_ID="${EXISTING}"
  else
    echo "==> Create lane ${NAME} (plan ${PLAN}, \$5k paper)"
    LANE_JSON="$(curl -fsS -X POST "${API_BASE}/api/admin/lanes" "${auth[@]}" -d "{
      \"name\": \"${NAME}\",
      \"strategy_version\": \"${VERSION}\",
      \"plan_version\": \"${PLAN}\",
      \"lane_role\": \"research\",
      \"initial_cash_usd\": 5000
    }")"
    echo "${LANE_JSON}" | python3 -m json.tool
    LANE_ID="$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"${LANE_JSON}")"
    LANES_JSON="$(curl -fsS "${API_BASE}/api/admin/lanes" "${auth[@]}")"
  fi
  RESULTS+=("${NAME}|${LANE_ID}|${PLAN}|${VERSION}|${AUTO}|${CRON}")
done < <(python3 -c "import json; [print(json.dumps(s)) for s in json.load(open('/tmp/mta-dte-lane-specs.json'))]")

echo "==> Restore pre-DTE strategy rules as global active"
curl -fsS -X PATCH "${API_BASE}/api/automation/strategy" "${auth[@]}" -d "${RESTORE_RULES}" \
  | python3 -c "import json,sys; s=json.load(sys.stdin); print(f'    active strategy restored to {s[\"version\"]}')"

echo
echo "==> DTE lanes ready (paper only — never place_option_order)"
printf '%s\n' "Lane | id | plan | strategy | automation | cron UTC (EDT = UTC-4)"
for row in "${RESULTS[@]}"; do
  IFS='|' read -r name lid plan ver auto cron <<<"${row}"
  echo "${name} | ${lid} | ${plan} | ${ver} | ${auto} | ${cron}"
done

cat <<EOF

Next: create four Cursor automations. Paste docs/automation/dte-options-prompt.md
and fill API_BASE, WRITE_API_KEY, LANE_ID, AUTOMATION_NAME, PLAN_VERSION.

Model: Grok 4.6 xhigh. Repository: none. Robinhood MCP + HTTP.
Run after US cash open (crons above). Sequential lock is 45 minutes — do not
fire all four at once.

See docs/automation/dte-options-setup.md
EOF
