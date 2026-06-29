const API_BASE = window.MTA_CONFIG?.API_BASE_URL || "http://localhost:8000";
const API_READ_KEY = window.MTA_CONFIG?.API_READ_KEY;

function apiHeaders() {
  const headers = {};
  if (API_READ_KEY) {
    headers["X-API-Key"] = API_READ_KEY;
  }
  return headers;
}

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`, { headers: apiHeaders() });
  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`);
  }
  return response.json();
}

function badgeClass(mode) {
  if (mode === "live") return "badge live";
  return "badge research";
}

function formatMoney(value) {
  if (value == null) return "—";
  return `$${Number(value).toFixed(2)}`;
}

function renderStats(stats) {
  const items = [
    ["Runs", stats.total_runs],
    ["Completed", stats.completed_runs],
    ["Failed", stats.failed_runs],
    ["Decisions", stats.total_decisions],
    ["Simulated Trades", stats.simulated_trades],
    ["Live Trades", stats.live_trades],
    ["Holds / Skips", stats.holds_and_skips],
    ["Cursor Cost", formatMoney(stats.total_cursor_cost_usd)],
  ];

  document.getElementById("stats-grid").innerHTML = items
    .map(
      ([label, value]) => `
        <article class="card">
          <div class="stat-label">${label}</div>
          <div class="stat-value">${value}</div>
        </article>
      `
    )
    .join("");
}

function renderStrategy(context) {
  const strategy = context.strategy;
  const signals = context.market_signals?.length
    ? `<p><strong>Check needed:</strong> yes (${context.market_signals.length} signal(s))</p>`
    : `<p><strong>Check needed:</strong> no</p>`;
  document.getElementById("strategy-panel").innerHTML = `
    <p><span class="${badgeClass(strategy.mode)}">${strategy.mode}</span></p>
    <p><strong>${strategy.name}</strong> (${strategy.version})</p>
    <p>Trading enabled: ${strategy.trading_enabled ? "yes" : "no"}</p>
    <p>Kill switch: ${strategy.kill_switch ? "ON" : "off"}</p>
    <p>Allowed symbols: ${strategy.rules.allowed_symbols.join(", ")}</p>
    <p>Max order: ${formatMoney(strategy.rules.max_order_usd)}</p>
    <p>Watchlist: ${strategy.rules.watchlist.join(", ")}</p>
    ${signals}
  `;
}

function renderPortfolio(portfolio) {
  const rows = portfolio.positions
    .map(
      (position) => `
        <tr>
          <td>${position.symbol}</td>
          <td>${position.quantity.toFixed(4)}</td>
          <td>${formatMoney(position.avg_cost)}</td>
          <td>${formatMoney(position.last_price)}</td>
          <td>${formatMoney(position.market_value)}</td>
          <td>${formatMoney(position.unrealized_pnl)}</td>
        </tr>
      `
    )
    .join("");

  document.getElementById("portfolio-panel").innerHTML = `
    <p>Cash: ${formatMoney(portfolio.cash_usd)}</p>
    <p>Total equity: ${formatMoney(portfolio.total_equity)}</p>
    <p>Unrealized P&amp;L: ${formatMoney(portfolio.total_unrealized_pnl)}</p>
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Qty</th>
          <th>Avg Cost</th>
          <th>Last Price</th>
          <th>Value</th>
          <th>P&amp;L</th>
        </tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="6">No simulated positions yet.</td></tr>`}</tbody>
    </table>
  `;
}

function renderReconciliation(summary) {
  document.getElementById("reconciliation-panel").innerHTML = `
    <p>Robinhood orders: ${summary.total_orders}</p>
    <p>Linked to decisions: ${summary.linked_orders}</p>
    <p>Unmatched orders: ${summary.unmatched_orders}</p>
    <p>Decisions with order_id: ${summary.decisions_with_order_id}</p>
    <p>Unmatched decisions: ${summary.unmatched_decisions}</p>
  `;
}

function renderOrders(orders) {
  const rows = orders
    .map(
      (order) => `
        <tr>
          <td>${order.created_at}</td>
          <td>${order.symbol}</td>
          <td>${order.side}</td>
          <td>${order.status}</td>
          <td>${formatMoney(order.average_fill_price)}</td>
          <td>${order.decision_id ?? "—"}</td>
          <td>${order.reconciliation_status}</td>
        </tr>
      `
    )
    .join("");

  document.getElementById("orders-table-wrap").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Symbol</th>
          <th>Side</th>
          <th>Status</th>
          <th>Fill</th>
          <th>Decision</th>
          <th>Reconciliation</th>
        </tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="7">No Robinhood orders synced yet.</td></tr>`}</tbody>
    </table>
  `;
}

function renderRuns(runs) {
  const rows = runs
    .map(
      (run) => `
        <tr class="clickable-row" data-run-id="${run.id}" title="View run #${run.id}">
          <td>${run.run_at}</td>
          <td>${run.automation_name || "—"}</td>
          <td><span class="${badgeClass(run.mode)}">${run.mode || "—"}</span></td>
          <td>${run.status}</td>
          <td>${run.market_summary || "—"}</td>
        </tr>
      `
    )
    .join("");

  document.getElementById("runs-table-wrap").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Run At</th>
          <th>Automation</th>
          <th>Mode</th>
          <th>Status</th>
          <th>Summary</th>
        </tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="5">No runs logged yet.</td></tr>`}</tbody>
    </table>
  `;

  document.querySelectorAll("[data-run-id]").forEach((row) => {
    row.addEventListener("click", () => openRunModal(Number(row.dataset.runId)));
  });
}

function renderRunDetail(run) {
  const errors =
    run.errors?.length > 0
      ? `<div class="modal-errors"><strong>Errors:</strong><ul>${run.errors
          .map((e) => `<li>${e}</li>`)
          .join("")}</ul></div>`
      : "";

  const usage = run.usage
    ? `<p><strong>Usage:</strong> ${run.usage.model || "—"} · ${formatMoney(run.usage.cost_usd)}</p>`
    : "";

  const decisions = (run.decisions || [])
    .map(
      (d) => `
        <tr>
          <td>${d.symbol}</td>
          <td>${d.action}</td>
          <td>${formatScores(d.scores)}</td>
          <td>${formatMoney(d.amount_usd)}</td>
          <td>${d.order_id || "—"}</td>
          <td class="reason">${d.reason}</td>
          <td class="reason">${d.action_rationale || "—"}</td>
        </tr>
      `
    )
    .join("");

  return `
    <div class="modal-meta">
      <p><strong>Run #${run.id}</strong> · ${run.run_at} · ${run.status}</p>
      <p>${run.market_summary || "No market summary."}</p>
      <p>Strategy: ${run.strategy_version || "—"} · Mode: ${run.mode || "—"} · Cursor run: ${run.cursor_run_id || "—"}</p>
      ${usage}
    </div>
    ${errors}
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Action</th>
          <th>Scores (T/N/R/C)</th>
          <th>Amount</th>
          <th>Order ID</th>
          <th>Reason</th>
          <th>Rationale</th>
        </tr>
      </thead>
      <tbody>${decisions || `<tr><td colspan="7">No decisions.</td></tr>`}</tbody>
    </table>
  `;
}

async function openRunModal(runId) {
  const modal = document.getElementById("run-modal");
  const body = document.getElementById("run-modal-body");
  modal.hidden = false;
  body.textContent = "Loading...";
  try {
    const run = await fetchJson(`/api/automation/runs/${runId}`);
    document.getElementById("run-modal-title").textContent = `Run #${run.id}`;
    body.innerHTML = renderRunDetail(run);
  } catch (error) {
    body.textContent = `Failed to load run: ${error.message}`;
  }
}

function closeRunModal() {
  document.getElementById("run-modal").hidden = true;
}

async function downloadExport() {
  const response = await fetch(`${API_BASE}/api/dashboard/export?format=csv&type=all`, {
    headers: apiHeaders(),
  });
  if (!response.ok) {
    throw new Error(`export failed with ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "mta-lab-export.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function formatScore(value) {
  if (value == null) return "—";
  return Number(value).toFixed(2);
}

function formatScores(scores) {
  if (!scores) return "—";
  return `T ${formatScore(scores.technical)} · N ${formatScore(scores.news)} · R ${formatScore(scores.risk)} · C ${formatScore(scores.confidence)}`;
}

function renderDecisions(decisions) {
  const rows = decisions
    .map(
      (decision) => `
        <tr>
          <td>${decision.created_at}</td>
          <td>${decision.symbol}</td>
          <td>${decision.action}</td>
          <td>${formatScores(decision.scores)}</td>
          <td>${formatMoney(decision.amount_usd)}</td>
          <td class="reason">${decision.reason}</td>
          <td class="reason">${decision.action_rationale || "—"}</td>
          <td class="reason">${decision.review_output || "—"}</td>
        </tr>
      `
    )
    .join("");

  document.getElementById("decisions-table-wrap").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Symbol</th>
          <th>Action</th>
          <th>Scores (T/N/R/C)</th>
          <th>Amount</th>
          <th>Reason</th>
          <th>Rationale</th>
          <th>Review</th>
        </tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="8">No decisions logged yet.</td></tr>`}</tbody>
    </table>
  `;
}

function renderUsage(usageRows) {
  const rows = usageRows
    .map(
      (row) => `
        <tr>
          <td>${row.created_at}</td>
          <td>${row.run_id ?? "—"}</td>
          <td>${row.model || "—"}</td>
          <td>${formatMoney(row.cost_usd)}</td>
          <td>${row.input_tokens ?? "—"}</td>
          <td>${row.output_tokens ?? "—"}</td>
          <td>${row.source}</td>
        </tr>
      `
    )
    .join("");

  document.getElementById("usage-table-wrap").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Run ID</th>
          <th>Model</th>
          <th>Cost</th>
          <th>Input Tokens</th>
          <th>Output Tokens</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="7">No usage logged yet.</td></tr>`}</tbody>
    </table>
  `;
}

async function loadDashboard() {
  const errorBanner = document.getElementById("error-banner");
  errorBanner.hidden = true;

  try {
    const [stats, context, runs, decisions, portfolio, usage, orders, reconciliation] =
      await Promise.all([
      fetchJson("/api/dashboard/stats"),
      fetchJson("/api/automation/context"),
      fetchJson("/api/dashboard/runs?limit=25"),
      fetchJson("/api/dashboard/decisions?limit=50"),
      fetchJson("/api/dashboard/portfolio"),
      fetchJson("/api/dashboard/usage?limit=25"),
      fetchJson("/api/dashboard/orders?limit=25"),
      fetchJson("/api/dashboard/reconciliation"),
    ]);

    renderStats(stats);
    renderStrategy(context);
    renderPortfolio(portfolio);
    renderReconciliation(reconciliation);
    renderOrders(orders);
    renderRuns(runs);
    renderUsage(usage);
    renderDecisions(decisions);
  } catch (error) {
    errorBanner.hidden = false;
    errorBanner.textContent = `Failed to load dashboard: ${error.message}. Check config.js API_BASE_URL and CORS settings.`;
  }
}

document.getElementById("refresh-btn").addEventListener("click", loadDashboard);
document.getElementById("export-btn").addEventListener("click", () => {
  downloadExport().catch((error) => {
    const errorBanner = document.getElementById("error-banner");
    errorBanner.hidden = false;
    errorBanner.textContent = error.message;
  });
});
document.querySelectorAll("[data-close-modal]").forEach((el) => {
  el.addEventListener("click", closeRunModal);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeRunModal();
});
loadDashboard();
