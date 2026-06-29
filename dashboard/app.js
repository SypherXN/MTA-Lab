const API_BASE = window.MTA_CONFIG?.API_BASE_URL || "http://localhost:8000";
const API_READ_KEY = window.MTA_CONFIG?.API_READ_KEY;
const SESSION_KEY = "mta_session_token";

function getSessionToken() {
  return localStorage.getItem(SESSION_KEY);
}

function setSessionToken(token) {
  if (token) {
    localStorage.setItem(SESSION_KEY, token);
  } else {
    localStorage.removeItem(SESSION_KEY);
  }
}

function apiHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (API_READ_KEY) {
    headers["X-API-Key"] = API_READ_KEY;
  }
  const token = getSessionToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

function apiHeadersReadOnly() {
  const headers = {};
  if (API_READ_KEY) {
    headers["X-API-Key"] = API_READ_KEY;
  }
  const token = getSessionToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function patchJson(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: apiHeaders(),
    body: JSON.stringify(body),
  });
  if (response.status === 401) {
    showLoginScreen();
    throw new Error("Authentication required");
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `${path} failed with ${response.status}`);
  }
  return response.json();
}

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...apiHeadersReadOnly(), ...(options.headers || {}) },
  });
  if (response.status === 401) {
    const needsLogin = !API_READ_KEY && !getSessionToken();
    if (needsLogin || path !== "/api/auth/login") {
      showLoginScreen();
      throw new Error("Authentication required");
    }
  }
  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function showLoginScreen() {
  document.getElementById("login-screen").hidden = false;
  document.getElementById("app-shell").hidden = true;
}

function showAppShell() {
  document.getElementById("login-screen").hidden = true;
  document.getElementById("app-shell").hidden = false;
}

async function tryLogin(password) {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Login failed (${response.status})`);
  }
  const data = await response.json();
  setSessionToken(data.token);
  return data;
}

async function logout() {
  const token = getSessionToken();
  if (token) {
    try {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {
      /* ignore */
    }
  }
  setSessionToken(null);
  showLoginScreen();
}

function badgeClass(mode) {
  if (mode === "live") return "badge live";
  return "badge research";
}

function formatMoney(value) {
  if (value == null) return "—";
  return `$${Number(value).toFixed(2)}`;
}

function formatScore(value) {
  if (value == null) return null;
  return Number(value);
}

function formatScores(scores) {
  if (!scores) return "—";
  return `T ${formatScore(scores.technical)?.toFixed(2) ?? "—"} · N ${formatScore(scores.news)?.toFixed(2) ?? "—"} · R ${formatScore(scores.risk)?.toFixed(2) ?? "—"} · C ${formatScore(scores.confidence)?.toFixed(2) ?? "—"}`;
}

function renderScoreBars(scores) {
  if (!scores) {
    return `<p class="muted">No structured scores recorded.</p>`;
  }
  const items = [
    ["Technical", scores.technical],
    ["News", scores.news],
    ["Risk", scores.risk],
    ["Confidence", scores.confidence],
  ];
  return `
    <div class="score-bars">
      ${items
        .map(([label, value]) => {
          const pct = value == null ? 0 : Math.round(Number(value) * 100);
          return `
            <div class="score-row">
              <span class="score-label">${label}</span>
              <div class="score-track"><div class="score-fill" style="width:${pct}%"></div></div>
              <span class="score-value">${value == null ? "—" : Number(value).toFixed(2)}</span>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderExplainability(decision) {
  return `
    <div class="explain-block">
      ${renderScoreBars(decision.scores)}
      <p><strong>Action:</strong> ${decision.action}</p>
      <p><strong>Reason:</strong> ${decision.reason}</p>
      <p><strong>Rationale:</strong> ${decision.action_rationale || "—"}</p>
      ${decision.review_output ? `<p><strong>Review:</strong> ${decision.review_output}</p>` : ""}
    </div>
  `;
}

function severityClass(severity) {
  if (severity === "critical") return "bad";
  if (severity === "high") return "warn";
  return "muted";
}

async function updateAlertStatus(alertId, status) {
  await patchJson(`/api/dashboard/alerts/${alertId}`, { status });
  await loadDashboard();
}

function renderAlerts(alerts) {
  const panel = document.getElementById("alerts-panel");
  if (!alerts?.length) {
    panel.innerHTML = "<p class='good'>No alerts recorded.</p>";
    return;
  }
  const rows = alerts
    .map(
      (a) => `
        <tr data-alert-id="${a.id}">
          <td><span class="${severityClass(a.severity)}">${a.severity}</span></td>
          <td>${a.alert_type}</td>
          <td>${a.title}</td>
          <td>${a.status}</td>
          <td>${a.created_at}</td>
          <td>
            ${
              a.run_id
                ? `<button type="button" class="link-btn" data-run-id="${a.run_id}">Run #${a.run_id}</button>`
                : a.entity_id || "—"
            }
          </td>
          <td class="alert-actions">
            ${
              a.status === "open"
                ? `<button type="button" class="secondary alert-ack" data-id="${a.id}">Ack</button>`
                : ""
            }
            ${
              a.status !== "resolved"
                ? `<button type="button" class="secondary alert-resolve" data-id="${a.id}">Resolve</button>`
                : ""
            }
          </td>
        </tr>
        <tr><td colspan="7" class="reason">${a.message}</td></tr>
      `
    )
    .join("");
  panel.innerHTML = `
    <table>
      <thead><tr><th>Severity</th><th>Type</th><th>Title</th><th>Status</th><th>Created</th><th>Link</th><th>Actions</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
  panel.querySelectorAll(".alert-ack").forEach((btn) => {
    btn.addEventListener("click", () => updateAlertStatus(Number(btn.dataset.id), "acknowledged"));
  });
  panel.querySelectorAll(".alert-resolve").forEach((btn) => {
    btn.addEventListener("click", () => updateAlertStatus(Number(btn.dataset.id), "resolved"));
  });
  panel.querySelectorAll("[data-run-id]").forEach((btn) => {
    btn.addEventListener("click", () => openRunModal(Number(btn.dataset.runId)));
  });
}

function renderStrategyCompare(compare) {
  const panel = document.getElementById("strategy-compare-panel");
  if (!compare?.strategy_versions?.length) {
    panel.innerHTML = "<p class='muted'>No strategy versions with runs yet.</p>";
    return;
  }
  const rows = compare.strategy_versions
    .map(
      (v) => `
        <tr>
          <td>${v.key}</td>
          <td>${v.run_count}</td>
          <td>${v.decision_count}</td>
          <td>${v.simulated_trades}</td>
          <td>${v.avg_confidence != null ? Number(v.avg_confidence).toFixed(2) : "—"}</td>
          <td>${formatMoney(v.equity_change_usd)}</td>
          <td>${formatMoney(v.total_cost_usd)}</td>
        </tr>
      `
    )
    .join("");
  panel.innerHTML = `
    <table>
      <thead><tr><th>Strategy</th><th>Runs</th><th>Decisions</th><th>Sim trades</th><th>Avg conf</th><th>Equity Δ</th><th>Cost</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderMobileStatus(status) {
  const bar = document.getElementById("mobile-status-bar");
  if (!status) {
    bar.hidden = true;
    return;
  }
  bar.hidden = false;
  bar.innerHTML = `
    <span class="${badgeClass(status.strategy_mode)}">${status.strategy_mode}</span>
    <span>Equity ${formatMoney(status.total_equity_usd)}</span>
    <span>Alerts ${status.open_alerts}</span>
    <span>Kill ${status.kill_switch ? "ON" : "off"}</span>
    <span class="${status.budget_ok ? "good" : "bad"}">Budget ${status.budget_ok ? "ok" : "exceeded"}</span>
    <span class="muted">${status.last_run_at ? `Last run ${status.last_run_status}` : "No runs"}</span>
  `;
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
  const intervention = context.intervention_status;
  const signals = context.market_signals?.length
    ? `<p><strong>Check needed:</strong> yes (${context.market_signals.length} signal(s))</p>`
    : `<p><strong>Check needed:</strong> no</p>`;
  const interventionBlock = intervention?.triggers?.length
    ? `<ul class="freshness-warnings">${intervention.triggers
        .map((t) => `<li class="${t.severity === "critical" ? "bad" : "warn"}">${t.code}: ${t.message}</li>`)
        .join("")}</ul>`
    : `<p class="good">No intervention triggers</p>`;
  document.getElementById("strategy-panel").innerHTML = `
    <p><span class="${badgeClass(strategy.mode)}">${strategy.mode}</span></p>
    <p><strong>${strategy.name}</strong> (${strategy.version})</p>
    <p>Trading enabled: ${strategy.trading_enabled ? "yes" : "no"}</p>
    <p>Kill switch: ${strategy.kill_switch ? "ON" : "off"}</p>
    <p>Allowed symbols: ${strategy.rules.allowed_symbols.join(", ")}</p>
    <p>Watchlist: ${strategy.rules.watchlist.join(", ")}</p>
    ${signals}
    <h3>Intervention</h3>
    ${interventionBlock}
    <p class="muted">${intervention?.recommended_action || ""}</p>
    ${
      context.usage_budget
        ? `<p>Budget: daily ${formatMoney(context.usage_budget.daily_spent_usd)} / ${formatMoney(context.usage_budget.daily_budget_usd)} · monthly ${formatMoney(context.usage_budget.monthly_spent_usd)} / ${formatMoney(context.usage_budget.monthly_budget_usd)}</p>`
        : ""
    }
  `;
}

function renderSafetyControls(context) {
  const strategy = context.strategy;
  const rules = strategy.rules;
  document.getElementById("safety-panel").innerHTML = `
    <form id="safety-form" class="safety-form">
      <label>Mode
        <select name="mode">
          <option value="research" ${strategy.mode === "research" ? "selected" : ""}>research</option>
          <option value="paper" ${strategy.mode === "paper" ? "selected" : ""}>paper</option>
          <option value="live" ${strategy.mode === "live" ? "selected" : ""}>live</option>
        </select>
      </label>
      <label><input type="checkbox" name="trading_enabled" ${strategy.trading_enabled ? "checked" : ""} /> Trading enabled</label>
      <label><input type="checkbox" name="kill_switch" ${strategy.kill_switch ? "checked" : ""} /> Kill switch</label>
      <label>Max order (USD)<input type="number" name="max_order_usd" min="0" step="1" value="${rules.max_order_usd}" /></label>
      <label>Max daily trades<input type="number" name="max_daily_trades" min="0" step="1" value="${rules.max_daily_trades}" /></label>
      <label>Max daily notional (USD)<input type="number" name="max_daily_notional_usd" min="0" step="1" value="${rules.max_daily_notional_usd}" /></label>
      <button type="submit">Save safety settings</button>
    </form>
    <p id="safety-save-status" class="muted"></p>
    <p class="login-hint">Requires dashboard login or write API key. Creates a new strategy version on change.</p>
  `;
  document.getElementById("safety-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const status = document.getElementById("safety-save-status");
    status.textContent = "Saving...";
    try {
      const payload = {
        mode: form.mode.value,
        trading_enabled: form.trading_enabled.checked,
        kill_switch: form.kill_switch.checked,
        rules: {
          ...rules,
          max_order_usd: Number(form.max_order_usd.value),
          max_daily_trades: Number(form.max_daily_trades.value),
          max_daily_notional_usd: Number(form.max_daily_notional_usd.value),
        },
      };
      await patchJson("/api/dashboard/strategy", payload);
      status.textContent = "Saved.";
      await loadDashboard();
    } catch (error) {
      status.textContent = error.message;
    }
  });
}

function renderCostDashboard(summary) {
  if (!summary) {
    document.getElementById("cost-dashboard-panel").innerHTML = "<p>No usage data yet.</p>";
    return;
  }
  const days = summary.by_day || [];
  const width = 640;
  const height = 200;
  const padX = 48;
  const padY = 28;
  const costs = days.map((d) => d.cost_usd);
  const maxCost = Math.max(...costs, 0.01);
  const plotWidth = width - padX * 2;
  const plotHeight = height - padY * 2;
  const points = days
    .map((row, index) => {
      const x = padX + (index / Math.max(days.length - 1, 1)) * plotWidth;
      const y = padY + (1 - row.cost_usd / maxCost) * plotHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const modelRows = (summary.by_model || [])
    .map((row) => `<tr><td>${row.key}</td><td>${formatMoney(row.cost_usd)}</td><td>${row.row_count}</td></tr>`)
    .join("");
  const runTypeRows = (summary.by_run_type || [])
    .map((row) => `<tr><td>${row.key}</td><td>${formatMoney(row.cost_usd)}</td><td>${row.row_count}</td></tr>`)
    .join("");

  document.getElementById("cost-dashboard-panel").innerHTML = `
    <div class="equity-curve-meta">
      <span>Total: ${formatMoney(summary.total_cost_usd)}</span>
      <span>${summary.usage_row_count} usage rows</span>
      <span>Cost/decision: ${summary.cost_per_decision != null ? formatMoney(summary.cost_per_decision) : "—"}</span>
    </div>
    ${
      days.length
        ? `<svg class="equity-curve-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Cursor cost over time">
            <polyline points="${points}" class="chart-line" />
          </svg>`
        : "<p class='muted'>No daily cost data yet.</p>"
    }
    <div class="cost-breakdown-grid">
      <div>
        <h3>By model</h3>
        <table><thead><tr><th>Model</th><th>Cost</th><th>Rows</th></tr></thead><tbody>${modelRows || "<tr><td colspan='3'>—</td></tr>"}</tbody></table>
      </div>
      <div>
        <h3>By run type</h3>
        <table><thead><tr><th>Run type</th><th>Cost</th><th>Rows</th></tr></thead><tbody>${runTypeRows || "<tr><td colspan='3'>—</td></tr>"}</tbody></table>
      </div>
    </div>
  `;
}

function renderPortfolio(portfolio) {
  const rows = portfolio.positions
    .map(
      (position) => `
        <tr class="clickable-row" data-symbol="${position.symbol}" title="View ${position.symbol}">
          <td><a href="#symbol/${position.symbol}" class="symbol-link">${position.symbol}</a></td>
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

  document.querySelectorAll("[data-symbol]").forEach((row) => {
    row.addEventListener("click", () => openSymbolModal(row.dataset.symbol));
  });
}

function renderSnapshotSummary(summary) {
  if (!summary) {
    document.getElementById("snapshot-summary-panel").innerHTML =
      "<p>No portfolio snapshots yet. Snapshots are recorded after each completed run.</p>";
    return;
  }
  document.getElementById("snapshot-summary-panel").innerHTML = `
    <p><strong>${summary.snapshot_count}</strong> snapshots</p>
    <p>First: ${formatMoney(summary.first_equity_usd)} · Last: ${formatMoney(summary.last_equity_usd)}</p>
    <p>Change: ${formatMoney(summary.change_usd)} (${summary.change_pct.toFixed(2)}%)</p>
    <p>Range: ${formatMoney(summary.min_equity_usd)} – ${formatMoney(summary.max_equity_usd)}</p>
    <p class="muted">Last snapshot: ${summary.last_snapshot_at}</p>
  `;
}

function renderEquityCurve(snapshots) {
  const panel = document.getElementById("equity-curve-panel");
  if (!snapshots || snapshots.length === 0) {
    panel.innerHTML =
      "<p>No portfolio snapshots yet. Snapshots are recorded after each completed run.</p>";
    return;
  }

  const sorted = [...snapshots].sort((a, b) => a.snapshot_at.localeCompare(b.snapshot_at));
  const width = 640;
  const height = 220;
  const padX = 48;
  const padY = 28;
  const equities = sorted.map((row) => row.total_equity_usd);
  const minEquity = Math.min(...equities);
  const maxEquity = Math.max(...equities);
  const range = maxEquity - minEquity || 1;
  const plotWidth = width - padX * 2;
  const plotHeight = height - padY * 2;

  const points = sorted
    .map((row, index) => {
      const x =
        padX + (index / Math.max(sorted.length - 1, 1)) * plotWidth;
      const y =
        padY + (1 - (row.total_equity_usd - minEquity) / range) * plotHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  const change = last.total_equity_usd - first.total_equity_usd;
  const changePct =
    first.total_equity_usd !== 0
      ? (change / first.total_equity_usd) * 100
      : 0;

  panel.innerHTML = `
    <div class="equity-curve-meta">
      <span>${sorted.length} points</span>
      <span>${formatMoney(first.total_equity_usd)} → ${formatMoney(last.total_equity_usd)}</span>
      <span class="${change >= 0 ? "good" : "bad"}">${formatMoney(change)} (${changePct.toFixed(2)}%)</span>
    </div>
    <svg class="equity-curve-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Portfolio equity over time">
      <line x1="${padX}" y1="${height - padY}" x2="${width - padX}" y2="${height - padY}" class="chart-axis" />
      <line x1="${padX}" y1="${padY}" x2="${padX}" y2="${height - padY}" class="chart-axis" />
      <text x="${padX - 6}" y="${padY + 4}" class="chart-label">${formatMoney(maxEquity)}</text>
      <text x="${padX - 6}" y="${height - padY + 4}" class="chart-label">${formatMoney(minEquity)}</text>
      <polyline points="${points}" class="chart-line" />
      ${sorted
        .map((row, index) => {
          const x =
            padX + (index / Math.max(sorted.length - 1, 1)) * plotWidth;
          const y =
            padY + (1 - (row.total_equity_usd - minEquity) / range) * plotHeight;
          const title = `${row.snapshot_at}: ${formatMoney(row.total_equity_usd)}`;
          return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" class="chart-dot"><title>${title}</title></circle>`;
        })
        .join("")}
    </svg>
    <p class="muted">From portfolio snapshots (simulated equity marks after each run).</p>
  `;
}

function renderFreshness(checks) {
  const rows = checks?.sources || [];
  const ready = checks?.ready_for_analysis !== false;
  const warnings = checks?.warnings || [];

  const body = rows
    .map(
      (row) => `
        <tr class="${row.is_stale ? "freshness-stale" : ""}">
          <td>${row.source_key}</td>
          <td>${row.last_updated_at || "—"}</td>
          <td>${row.age_minutes != null ? `${row.age_minutes}m` : "—"} / ${row.max_age_minutes ?? "—"}m</td>
          <td>${row.is_stale ? '<span class="warn">stale</span>' : '<span class="good">ok</span>'}</td>
          <td>${row.detail || "—"}</td>
        </tr>
      `
    )
    .join("");

  const warningBlock =
    warnings.length > 0
      ? `<ul class="freshness-warnings">${warnings.map((w) => `<li class="warn">${w}</li>`).join("")}</ul>`
      : "";

  document.getElementById("freshness-panel").innerHTML = `
    <p class="freshness-banner ${ready ? "good" : "warn"}">
      ${ready ? "Ready for analysis" : "Inputs stale — review before trading"}
    </p>
    ${warningBlock}
    <table>
      <thead><tr><th>Source</th><th>Last updated</th><th>Age / max</th><th>Status</th><th>Detail</th></tr></thead>
      <tbody>${body || `<tr><td colspan="5">No freshness data yet.</td></tr>`}</tbody>
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

function timelineBadge(type) {
  return `timeline-badge timeline-${type}`;
}

function renderTimeline(events) {
  const rows = events
    .map((event) => {
      const runLink =
        event.run_id != null
          ? `<button type="button" class="link-btn" data-run-id="${event.run_id}">Run #${event.run_id}</button>`
          : "";
      const symbolLink = event.symbol
        ? `<button type="button" class="link-btn" data-symbol="${event.symbol}">${event.symbol}</button>`
        : "";
      return `
        <li class="timeline-item">
          <div class="timeline-meta">
            <span class="${timelineBadge(event.event_type)}">${event.event_type}</span>
            <time>${event.at}</time>
          </div>
          <div class="timeline-title">${event.title} ${symbolLink} ${runLink}</div>
          <div class="timeline-detail">${event.detail || ""}</div>
        </li>
      `;
    })
    .join("");

  const panel = document.getElementById("timeline-panel");
  panel.innerHTML = `<ul class="timeline">${rows || "<li>No activity yet.</li>"}</ul>`;
  panel.querySelectorAll("[data-run-id]").forEach((btn) => {
    btn.addEventListener("click", () => openRunModal(Number(btn.dataset.runId)));
  });
  panel.querySelectorAll("[data-symbol]").forEach((btn) => {
    btn.addEventListener("click", () => openSymbolModal(btn.dataset.symbol));
  });
}

function renderOrders(orders) {
  const rows = orders
    .map(
      (order) => `
        <tr>
          <td>${order.created_at}</td>
          <td><button type="button" class="link-btn" data-symbol="${order.symbol}">${order.symbol}</button></td>
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
          <th>Time</th><th>Symbol</th><th>Side</th><th>Status</th><th>Fill</th><th>Decision</th><th>Reconciliation</th>
        </tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="7">No Robinhood orders synced yet.</td></tr>`}</tbody>
    </table>
  `;
  document.querySelectorAll("#orders-table-wrap [data-symbol]").forEach((btn) => {
    btn.addEventListener("click", () => openSymbolModal(btn.dataset.symbol));
  });
}

function renderRuns(runs) {
  const rows = runs
    .map(
      (run) => `
        <tr class="clickable-row" data-run-id="${run.id}" title="View run #${run.id}">
          <td>${run.run_at}</td>
          <td>${run.automation_name || "—"}</td>
          <td>${run.run_type || "—"}</td>
          <td><span class="${badgeClass(run.mode)}">${run.mode || "—"}</span></td>
          <td>${run.status}</td>
          <td>${run.budget_exceeded ? '<span class="warn">budget</span> ' : ""}${run.market_summary || "—"}</td>
        </tr>
      `
    )
    .join("");

  document.getElementById("runs-table-wrap").innerHTML = `
    <table>
      <thead>
        <tr><th>Run At</th><th>Automation</th><th>Run Type</th><th>Mode</th><th>Status</th><th>Summary</th></tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="6">No runs logged yet.</td></tr>`}</tbody>
    </table>
  `;
  document.querySelectorAll("#runs-table-wrap [data-run-id]").forEach((row) => {
    row.addEventListener("click", () => openRunModal(Number(row.dataset.runId)));
  });
}

function renderRunDetail(run) {
  const errors =
    run.errors?.length > 0
      ? `<div class="modal-errors"><strong>Errors:</strong><ul>${run.errors.map((e) => `<li>${e}</li>`).join("")}</ul></div>`
      : "";
  const usage = run.usage
    ? `<p><strong>Usage:</strong> ${run.usage.model || "—"} · ${formatMoney(run.usage.cost_usd)} · in ${run.usage.input_tokens ?? "—"} / out ${run.usage.output_tokens ?? "—"} tokens</p>`
    : "";

  const audit = run.audit;
  const auditBlock = audit
    ? `
      <div class="modal-audit">
        <h3>Run audit</h3>
        <p>Preflight ready (current): ${audit.preflight_ready ? "yes" : "no"}</p>
        <p>Decisions: ${audit.inputs_summary?.decision_count ?? "—"} · Unmatched order IDs: ${(audit.unmatched_order_ids || []).join(", ") || "none"}</p>
        ${
          audit.linked_orders?.length
            ? `<table><thead><tr><th>Order</th><th>Symbol</th><th>Status</th><th>Linked</th></tr></thead><tbody>${audit.linked_orders
                .map(
                  (o) =>
                    `<tr><td>${o.order_id}</td><td>${o.symbol}</td><td>${o.status}</td><td>${o.linked ? "yes" : "no"}</td></tr>`
                )
                .join("")}</tbody></table>`
            : ""
        }
        ${
          audit.safety_snapshot
            ? `<p>Safety: trades ${audit.safety_snapshot.daily_trades_used}/${audit.safety_snapshot.daily_trades_remaining + audit.safety_snapshot.daily_trades_used} · notional ${formatMoney(audit.safety_snapshot.daily_notional_used)}</p>`
            : ""
        }
      </div>
    `
    : "";

  const decisions = (run.decisions || [])
    .map(
      (d) => `
        <tr>
          <td><button type="button" class="link-btn" data-symbol="${d.symbol}">${d.symbol}</button></td>
          <td>${d.action}</td>
          <td>${renderScoreBars(d.scores)}</td>
          <td>${formatMoney(d.amount_usd)}</td>
          <td>${d.order_id || "—"}</td>
          <td class="reason">${d.reason}</td>
        </tr>
      `
    )
    .join("");

  return `
    <div class="modal-meta">
      <p><strong>Run #${run.id}</strong> · ${run.run_at} · ${run.status} · ${run.run_type || "daily_research"}</p>
      <p>${run.market_summary || "No market summary."}</p>
      ${run.self_critique ? `<p><strong>Self-critique:</strong> ${run.self_critique}</p>` : ""}
      <p>Strategy: ${run.strategy_version || "—"} · Plan: ${run.plan_version || "—"} · Mode: ${run.mode || "—"}</p>
      ${
        run.budget_exceeded
          ? `<p class="warn"><strong>Budget exceeded:</strong> ${formatMoney(run.actual_cost_usd)} vs expected ${formatMoney(run.expected_budget_usd)}</p>`
          : run.expected_budget_usd != null
            ? `<p><strong>Run budget:</strong> ${formatMoney(run.actual_cost_usd)} / ${formatMoney(run.expected_budget_usd)}</p>`
            : ""
      }
      ${usage}
    </div>
    ${auditBlock}
    ${errors}
    <table>
      <thead><tr><th>Symbol</th><th>Action</th><th>Explainability</th><th>Amount</th><th>Order ID</th><th>Reason</th></tr></thead>
      <tbody>${decisions || `<tr><td colspan="6">No decisions.</td></tr>`}</tbody>
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
    body.querySelectorAll("[data-symbol]").forEach((btn) => {
      btn.addEventListener("click", () => openSymbolModal(btn.dataset.symbol));
    });
  } catch (error) {
    body.textContent = `Failed to load run: ${error.message}`;
  }
}

function renderSymbolDetail(memory) {
  const summary = memory.summary;
  const cooldown = memory.cooldown;
  const position = memory.position;

  const decisionRows = (memory.recent_decisions || [])
    .map(
      (d) => `
        <tr>
          <td>${d.created_at}</td>
          <td>${d.action}</td>
          <td>${renderExplainability(d)}</td>
        </tr>
      `
    )
    .join("");

  const signalRows = (memory.recent_signals || [])
    .map((s) => `<li>${s.created_at}: ${s.message}</li>`)
    .join("");

  const noteRows = (memory.related_notes || [])
    .map((n) => `<li>${n.content}</li>`)
    .join("");

  const newsRows = (memory.recent_news || [])
    .map(
      (n) =>
        `<li><time>${n.event_at}</time> [${n.source}] ${n.summary}${
          n.importance != null ? ` (importance ${n.importance.toFixed(2)})` : ""
        }</li>`
    )
    .join("");

  return `
    <div class="symbol-grid">
      <section>
        <h3>Summary</h3>
        <p>Last action: ${summary?.last_action || "—"}</p>
        <p>Trades: ${summary?.trade_count ?? 0} · Realized P&amp;L: ${formatMoney(summary?.realized_pnl_usd)}</p>
        <p>Unrealized P&amp;L: ${formatMoney(summary?.unrealized_pnl_usd ?? position?.unrealized_pnl)}</p>
        ${cooldown ? `<p class="warn">Cooldown until ${cooldown.blocked_until}: ${cooldown.reason}</p>` : ""}
      </section>
      <section>
        <h3>Position</h3>
        ${
          position
            ? `<p>Qty ${position.quantity.toFixed(4)} @ ${formatMoney(position.avg_cost)} · MV ${formatMoney(position.market_value)}</p>`
            : "<p>No simulated position.</p>"
        }
      </section>
    </div>
    ${signalRows ? `<h3>Recent signals</h3><ul>${signalRows}</ul>` : ""}
    ${newsRows ? `<h3>Recent news</h3><ul>${newsRows}</ul>` : ""}
    ${noteRows ? `<h3>Related notes</h3><ul>${noteRows}</ul>` : ""}
    <h3>Recent decisions</h3>
    <table>
      <thead><tr><th>Time</th><th>Action</th><th>Explainability</th></tr></thead>
      <tbody>${decisionRows || `<tr><td colspan="3">No decisions for this symbol.</td></tr>`}</tbody>
    </table>
  `;
}

async function openSymbolModal(symbol) {
  const modal = document.getElementById("symbol-modal");
  const body = document.getElementById("symbol-modal-body");
  modal.hidden = false;
  body.textContent = "Loading...";
  document.getElementById("symbol-modal-title").textContent = symbol.toUpperCase();
  window.location.hash = `symbol/${symbol.toUpperCase()}`;
  try {
    const memory = await fetchJson(`/api/automation/symbols/${encodeURIComponent(symbol)}/memory`);
    body.innerHTML = renderSymbolDetail(memory);
  } catch (error) {
    body.textContent = `Failed to load symbol: ${error.message}`;
  }
}

function closeRunModal() {
  document.getElementById("run-modal").hidden = true;
}

function closeSymbolModal() {
  document.getElementById("symbol-modal").hidden = true;
  if (window.location.hash.startsWith("#symbol/")) {
    history.replaceState(null, "", window.location.pathname);
  }
}

async function downloadExportJson() {
  const response = await fetch(`${API_BASE}/api/dashboard/export?format=json&type=all`, {
    headers: apiHeadersReadOnly(),
  });
  if (!response.ok) throw new Error(`export failed with ${response.status}`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "mta-lab-export.json";
  link.click();
  URL.revokeObjectURL(url);
}

async function downloadExport() {
  const response = await fetch(`${API_BASE}/api/dashboard/export?format=csv&type=all`, {
    headers: apiHeadersReadOnly(),
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

function renderDecisions(decisions) {
  const rows = decisions
    .map(
      (decision) => `
        <tr>
          <td>${decision.created_at}</td>
          <td><button type="button" class="link-btn" data-symbol="${decision.symbol}">${decision.symbol}</button></td>
          <td>${decision.action}</td>
          <td>${renderScoreBars(decision.scores)}</td>
          <td>${formatMoney(decision.amount_usd)}</td>
          <td class="reason">${decision.reason}</td>
          <td class="reason">${decision.action_rationale || "—"}</td>
        </tr>
      `
    )
    .join("");

  document.getElementById("decisions-table-wrap").innerHTML = `
    <table>
      <thead>
        <tr><th>Time</th><th>Symbol</th><th>Action</th><th>Explainability</th><th>Amount</th><th>Reason</th><th>Rationale</th></tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="7">No decisions logged yet.</td></tr>`}</tbody>
    </table>
  `;
  document.querySelectorAll("#decisions-table-wrap [data-symbol]").forEach((btn) => {
    btn.addEventListener("click", () => openSymbolModal(btn.dataset.symbol));
  });
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
        <tr><th>Time</th><th>Run ID</th><th>Model</th><th>Cost</th><th>Input</th><th>Output</th><th>Source</th></tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="7">No usage logged yet.</td></tr>`}</tbody>
    </table>
  `;
}

async function loadDashboard() {
  const errorBanner = document.getElementById("error-banner");
  errorBanner.hidden = true;

  try {
    const [
      stats,
      context,
      runs,
      decisions,
      portfolio,
      usage,
      usageSummary,
      orders,
      reconciliation,
      timeline,
      freshnessChecks,
      snapshotSummary,
      snapshots,
      alerts,
      compare,
      mobileStatus,
    ] = await Promise.all([
      fetchJson("/api/dashboard/stats"),
      fetchJson("/api/automation/context"),
      fetchJson("/api/dashboard/runs?limit=25"),
      fetchJson("/api/dashboard/decisions?limit=50"),
      fetchJson("/api/dashboard/portfolio"),
      fetchJson("/api/dashboard/usage?limit=25"),
      fetchJson("/api/dashboard/usage/summary").catch(() => null),
      fetchJson("/api/dashboard/orders?limit=25"),
      fetchJson("/api/dashboard/reconciliation"),
      fetchJson("/api/dashboard/timeline?limit=80"),
      fetchJson("/api/dashboard/freshness/check"),
      fetchJson("/api/dashboard/portfolio/snapshots/summary").catch(() => null),
      fetchJson("/api/dashboard/portfolio/snapshots?limit=200").catch(() => []),
      fetchJson("/api/dashboard/alerts?limit=50").catch(() => []),
      fetchJson("/api/dashboard/strategy/compare").catch(() => null),
      fetchJson("/api/dashboard/status/mobile").catch(() => null),
    ]);

    renderStats(stats);
    renderStrategy(context);
    renderSafetyControls(context);
    renderPortfolio(portfolio);
    renderSnapshotSummary(snapshotSummary);
    renderEquityCurve(snapshots);
    renderCostDashboard(usageSummary);
    renderFreshness(freshnessChecks);
    renderReconciliation(reconciliation);
    renderTimeline(timeline);
    renderOrders(orders);
    renderRuns(runs);
    renderUsage(usage);
    renderDecisions(decisions);
    renderAlerts(alerts);
    renderStrategyCompare(compare);
    renderMobileStatus(mobileStatus);
    showAppShell();
  } catch (error) {
    if (error.message === "Authentication required") {
      return;
    }
    errorBanner.hidden = false;
    errorBanner.textContent = `Failed to load dashboard: ${error.message}. Check config.js API_BASE_URL and CORS settings.`;
  }
}

async function bootstrap() {
  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorEl = document.getElementById("login-error");
    errorEl.hidden = true;
    try {
      await tryLogin(document.getElementById("login-password").value);
      showAppShell();
      await loadDashboard();
    } catch (error) {
      errorEl.hidden = false;
      errorEl.textContent = error.message;
    }
  });

  document.getElementById("refresh-btn").addEventListener("click", loadDashboard);
  document.getElementById("logout-btn").addEventListener("click", logout);
  document.getElementById("export-btn").addEventListener("click", () => {
    downloadExport().catch((error) => {
      const errorBanner = document.getElementById("error-banner");
      errorBanner.hidden = false;
      errorBanner.textContent = error.message;
    });
  });
  document.getElementById("export-json-btn").addEventListener("click", () => {
    downloadExportJson().catch((error) => {
      const errorBanner = document.getElementById("error-banner");
      errorBanner.hidden = false;
      errorBanner.textContent = error.message;
    });
  });

  document.querySelectorAll('[data-close-modal="run"]').forEach((el) => {
    el.addEventListener("click", closeRunModal);
  });
  document.querySelectorAll('[data-close-modal="symbol"]').forEach((el) => {
    el.addEventListener("click", closeSymbolModal);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeRunModal();
      closeSymbolModal();
    }
  });

  window.addEventListener("hashchange", () => {
    const match = window.location.hash.match(/^#symbol\/([A-Za-z.]+)$/);
    if (match) {
      openSymbolModal(match[1]);
    }
  });

  if (API_READ_KEY || getSessionToken()) {
    showAppShell();
    await loadDashboard();
  } else {
    try {
      await fetchJson("/api/dashboard/stats");
      showAppShell();
      await loadDashboard();
    } catch {
      showLoginScreen();
    }
  }

  const hashMatch = window.location.hash.match(/^#symbol\/([A-Za-z.]+)$/);
  if (hashMatch) {
    openSymbolModal(hashMatch[1]);
  }
}

bootstrap();
