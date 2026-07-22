const API_BASE = window.MTA_CONFIG?.API_BASE_URL || "http://localhost:8000";
const API_READ_KEY = window.MTA_CONFIG?.API_READ_KEY;
const SESSION_KEY = "mta_session_token";
const DASHBOARD_VIEWS = {
  overview: {
    title: "Overview",
    subtitle: "Live deployment and lane performance at a glance.",
  },
  lanes: {
    title: "Lanes",
    subtitle: "Compare plan performance, portfolios, and pinned agent instructions.",
  },
  operations: {
    title: "Operations",
    subtitle: "Strategy controls, data readiness, reconciliation, and alerts.",
  },
  activity: {
    title: "Activity",
    subtitle: "The complete audit trail from agent runs to orders and decisions.",
  },
};
const HASH_VIEW_MAP = {
  overview: "overview",
  lanes: "lanes",
  "lane-comparison": "lanes",
  "lane-portfolio": "lanes",
  "lane-plans": "lanes",
  operations: "operations",
  "risk-controls": "operations",
  "system-health": "operations",
  "alert-inbox": "operations",
  activity: "activity",
  "activity-timeline": "activity",
  "activity-runs": "activity",
  "activity-decisions": "activity",
};

let activeDashboardView = "overview";
let symbolReturnHash = "#overview";

function setDashboardView(viewName, { scrollToTop = false } = {}) {
  const view = DASHBOARD_VIEWS[viewName] ? viewName : "overview";
  activeDashboardView = view;
  document.querySelectorAll("[data-dashboard-view]").forEach((section) => {
    section.hidden = section.dataset.dashboardView !== view;
  });
  document.querySelectorAll("[data-view-target]").forEach((link) => {
    if (link.dataset.viewTarget === view) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
  const title = document.getElementById("view-title");
  const subtitle = document.getElementById("view-subtitle");
  if (title) title.textContent = DASHBOARD_VIEWS[view].title;
  if (subtitle) subtitle.textContent = DASHBOARD_VIEWS[view].subtitle;
  document.title = `${DASHBOARD_VIEWS[view].title} · MTA Lab`;
  if (scrollToTop) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function navigateToDashboardView(viewName) {
  if (!DASHBOARD_VIEWS[viewName]) return;
  const nextHash = `#${viewName}`;
  if (window.location.hash !== nextHash) {
    history.pushState(null, "", nextHash);
  }
  setDashboardView(viewName, { scrollToTop: false });
}

function routeDashboardHash() {
  const symbolMatch = window.location.hash.match(/^#symbol\/([A-Za-z.]+)$/);
  if (symbolMatch) {
    if (!document.getElementById("app-shell").hidden) {
      openSymbolModal(symbolMatch[1], { updateHash: false });
    }
    return;
  }

  document.getElementById("symbol-modal").hidden = true;
  const hash = window.location.hash.replace(/^#/, "");
  const view = HASH_VIEW_MAP[hash] || (DASHBOARD_VIEWS[hash] ? hash : "overview");
  setDashboardView(view, { scrollToTop: Boolean(hash && DASHBOARD_VIEWS[hash]) });
  if (hash && HASH_VIEW_MAP[hash] && !DASHBOARD_VIEWS[hash]) {
    requestAnimationFrame(() => {
      document.getElementById(hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
}

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

function apiHeaders({ json = true } = {}) {
  const headers = {};
  if (json) {
    headers["Content-Type"] = "application/json";
  }
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
    headers: { ...apiHeaders({ json: false }), ...(options.headers || {}) },
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
  const login = document.getElementById("login-screen");
  const app = document.getElementById("app-shell");
  login.hidden = false;
  login.style.display = "";
  app.hidden = true;
  app.style.display = "none";
}

function showAppShell() {
  const login = document.getElementById("login-screen");
  const app = document.getElementById("app-shell");
  login.hidden = true;
  login.style.display = "none";
  app.hidden = false;
  app.style.display = "";
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

function laneRoleBadge(role) {
  if (role === "live") return `<span class="lane-badge live">live</span>`;
  if (role === "shadow") return `<span class="lane-badge shadow">shadow</span>`;
  return `<span class="lane-badge research">research</span>`;
}

function laneRoleLabel(role) {
  if (role === "live") return "Live";
  if (role === "shadow") return "Shadow";
  return "Research";
}

function formatPeriodRange(startedAt, endedAt, isCurrent) {
  const start = startedAt?.slice(0, 10) || "—";
  if (isCurrent) return `${start} → now`;
  const end = endedAt?.slice(0, 10) || "—";
  return `${start} → ${end}`;
}

function renderLiveMoneyTrack(history, laneCompare) {
  const panel = document.getElementById("live-money-track");
  if (!history) {
    panel.innerHTML = "<p class='muted'>Live history unavailable.</p>";
    return;
  }

  const compareByLane = new Map((laneCompare?.lanes || []).map((row) => [row.lane_id, row]));
  const currentLine = history.current_live_lane_name
    ? `<p><strong>Current live lane:</strong> #${history.current_live_lane_id} ${history.current_live_lane_name} ${laneRoleBadge("live")}</p>`
    : `<p class='muted'><strong>No live lane yet.</strong> Promote a shadow or research lane when preflight passes.</p>`;

  const stats = `
    <div class="live-track-stats">
      <p><strong>Equity Δ:</strong> ${formatMoney(history.combined_equity_change_usd)}</p>
      <p><strong>Real orders:</strong> ${history.total_real_orders}</p>
      <p><strong>Live stints:</strong> ${history.periods.length}</p>
    </div>
  `;

  const periodRows =
    history.periods.length > 0
      ? history.periods
          .map((period) => {
            const compare = compareByLane.get(period.lane_id);
            return `
              <div class="live-period-row ${period.is_current ? "current" : ""}">
                <span>#${period.lane_id} <strong>${period.lane_name}</strong></span>
                ${period.is_current ? laneRoleBadge("live") : `<span class="lane-badge shadow">was live</span>`}
                <span class="muted">${formatPeriodRange(period.started_at, period.ended_at, period.is_current)}</span>
                <span>${period.strategy_version} + ${period.plan_version}</span>
                <span>Equity Δ ${formatMoney(period.equity_change_usd)}</span>
                <span>${period.run_count} runs · ${period.real_order_count} real orders</span>
                <button type="button" class="link-btn" data-view-lane="${period.lane_id}">View portfolio</button>
              </div>
            `;
          })
          .join("")
      : `<p class="muted">No lane has been live yet. Promote a shadow or research lane when preflight passes.</p>`;

  panel.innerHTML = `
    ${currentLine}
    ${stats}
    <h3>Live stint timeline</h3>
    <div class="live-period-timeline">${periodRows}</div>
    <div id="live-track-chart"></div>
  `;

  renderCombinedLiveEquityCurve(history.combined_snapshots);
  panel.querySelectorAll("[data-view-lane]").forEach((btn) => {
    btn.addEventListener("click", () => selectPortfolioLane(Number(btn.dataset.viewLane)));
  });
}

function renderCombinedLiveEquityCurve(snapshots) {
  const panel = document.getElementById("live-track-chart");
  if (!panel) return;
  if (!snapshots?.length) {
    panel.innerHTML =
      "<p class='muted'>Combined live equity curve will appear after live-lane runs record snapshots.</p>";
    return;
  }

  const width = 640;
  const height = 220;
  const padX = 48;
  const padY = 28;
  const plotWidth = width - padX * 2;
  const plotHeight = height - padY * 2;
  const equities = snapshots.map((row) => row.total_equity_usd);
  const minEquity = Math.min(...equities);
  const maxEquity = Math.max(...equities);
  const range = maxEquity - minEquity || 1;

  const points = snapshots
    .map((row, index) => {
      const x = padX + (index / Math.max(snapshots.length - 1, 1)) * plotWidth;
      const y = padY + (1 - (row.total_equity_usd - minEquity) / range) * plotHeight;
      return { x, y, row };
    });

  const polyline = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const handoffs = points
    .filter((p) => p.row.is_handoff)
    .map((p) => `<line x1="${p.x.toFixed(1)}" y1="${padY}" x2="${p.x.toFixed(1)}" y2="${height - padY}" class="chart-handoff" />`)
    .join("");

  const legend = [...new Set(snapshots.map((s) => `#${s.lane_id} ${s.lane_name}`))]
    .map((label) => `<span>${label}</span>`)
    .join(" · ");

  panel.innerHTML = `
    <div class="equity-curve-meta">${legend}</div>
    <svg class="equity-curve-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Combined live money equity curve">
      <line x1="${padX}" y1="${height - padY}" x2="${width - padX}" y2="${height - padY}" class="chart-axis" />
      <line x1="${padX}" y1="${padY}" x2="${padX}" y2="${height - padY}" class="chart-axis" />
      <text x="${padX - 6}" y="${padY + 4}" class="chart-label">${formatMoney(maxEquity)}</text>
      <text x="${padX - 6}" y="${height - padY + 4}" class="chart-label">${formatMoney(minEquity)}</text>
      ${handoffs}
      <polyline points="${polyline}" class="chart-line live-track" />
    </svg>
    <p class="muted">Dashed vertical lines mark handoffs when a new lane became live. Each lane keeps its own full history after demotion.</p>
  `;
}

function renderLaneCompare(compare) {
  const panel = document.getElementById("lane-compare-panel");
  if (!compare?.lanes?.length) {
    panel.innerHTML = "<p class='muted'>No simulation lanes yet.</p>";
    return;
  }
  const roleOrder = { live: 0, shadow: 1, research: 2 };
  const sorted = [...compare.lanes].sort(
    (a, b) => (roleOrder[a.lane_role] ?? 9) - (roleOrder[b.lane_role] ?? 9) || a.lane_id - b.lane_id
  );
  const rows = sorted
    .map(
      (lane) => `
        <tr class="${lane.lane_role === "live" ? "live-row" : ""}">
          <td>#${lane.lane_id} ${lane.name} ${laneRoleBadge(lane.lane_role)}</td>
          <td>${laneRoleLabel(lane.lane_role)}</td>
          <td>${lane.strategy_version}</td>
          <td>${lane.plan_version}</td>
          <td>${lane.run_count}</td>
          <td>${lane.simulated_trades}</td>
          <td>${lane.avg_confidence != null ? Number(lane.avg_confidence).toFixed(2) : "—"}</td>
          <td>${formatMoney(lane.equity_change_usd)}</td>
          <td>${formatMoney(lane.total_cost_usd)}</td>
          <td><button type="button" class="link-btn" data-view-lane="${lane.lane_id}">View</button></td>
        </tr>
      `
    )
    .join("");
  panel.innerHTML = `
    <table>
      <thead><tr><th>Lane</th><th>Type</th><th>Strategy</th><th>Plan</th><th>Runs</th><th>Sim trades</th><th>Avg conf</th><th>Equity Δ</th><th>Cost</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
  panel.querySelectorAll("[data-view-lane]").forEach((btn) => {
    btn.addEventListener("click", () => selectPortfolioLane(Number(btn.dataset.viewLane)));
  });
}

function renderLanesPanel(lanes, liveHistory) {
  const panel = document.getElementById("lanes-panel");
  if (!lanes?.length) {
    panel.innerHTML = "<p class='muted'>No lanes configured.</p>";
    return;
  }

  const periodsByLane = new Map();
  for (const period of liveHistory?.periods || []) {
    if (!periodsByLane.has(period.lane_id)) {
      periodsByLane.set(period.lane_id, []);
    }
    periodsByLane.get(period.lane_id).push(period);
  }

  const cards = lanes
    .map((lane) => {
      const periods = periodsByLane.get(lane.id) || [];
      const wasLive = periods.length > 0 && lane.lane_role !== "live";
      const liveHistoryLine =
        lane.lane_role === "live"
          ? `<p class="lane-card-meta">Currently deploying real money.</p>`
          : wasLive
            ? `<p class="lane-card-meta">Previously live (${periods.length} stint${periods.length === 1 ? "" : "s"}).</p>`
            : `<p class="lane-card-meta">${laneRoleLabel(lane.lane_role)}</p>`;
      return `
        <article class="lane-card ${lane.lane_role}">
          <h3>#${lane.id} ${lane.name} ${laneRoleBadge(lane.lane_role)}</h3>
          ${liveHistoryLine}
          <p class="lane-card-meta">Strategy ${lane.strategy_version} · Plan ${lane.plan_version}</p>
          <p class="lane-card-meta">Status ${lane.status} · Start ${formatMoney(lane.initial_cash_usd)}</p>
          <div class="lane-card-actions">
            <button type="button" class="link-btn" data-view-lane="${lane.id}">View portfolio</button>
            <button type="button" class="link-btn" data-view-plan="${lane.id}">View plan</button>
          </div>
        </article>
      `;
    })
    .join("");

  panel.innerHTML = `
    <div class="lane-cards">${cards}</div>
    <p class="muted">Each automation passes <code>lane_id</code> on context, plan, memory, and runs.</p>
  `;
  panel.querySelectorAll("[data-view-lane]").forEach((btn) => {
    btn.addEventListener("click", () => selectPortfolioLane(Number(btn.dataset.viewLane)));
  });
  panel.querySelectorAll("[data-view-plan]").forEach((btn) => {
    btn.addEventListener("click", () => openAgentPlanPanel(Number(btn.dataset.viewPlan)));
  });
}

function planGithubEditUrl(planVersion) {
  const base = window.MTA_CONFIG?.PLANS_REPO_URL;
  if (!base) {
    return null;
  }
  const branch = window.MTA_CONFIG?.PLANS_REPO_BRANCH || "main";
  const path = window.MTA_CONFIG?.PLANS_REPO_PATH || "plans";
  return `${base.replace(/\/$/, "")}/edit/${branch}/${path}/${encodeURIComponent(planVersion)}.json`;
}

const agentPlanCache = new Map();

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const activityData = { timeline: [], runs: [], decisions: [] };
const activityDayPage = { timeline: 0, runs: 0, decisions: 0 };

function parseActivityDay(iso) {
  if (!iso) return "unknown";
  const normalized = iso.includes("T") ? iso : iso.replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return String(iso).slice(0, 10);
  return date.toLocaleDateString("en-CA");
}

function formatActivityDayLabel(dayKey) {
  if (dayKey === "unknown") return "Unknown date";
  const date = new Date(`${dayKey}T12:00:00`);
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatActivityTime(iso) {
  if (!iso) return "—";
  const normalized = iso.includes("T") ? iso : iso.replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function groupRecordsByDay(records, field) {
  const groups = new Map();
  for (const record of records) {
    const key = parseActivityDay(record[field]);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  }
  return [...groups.entries()].sort(([a], [b]) => b.localeCompare(a));
}

function activityCountLabel(count, noun) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function renderActivityDayNav(section, dayGroups, items) {
  const totalDays = dayGroups.length;
  const page = totalDays ? Math.min(activityDayPage[section], totalDays - 1) : 0;
  activityDayPage[section] = page;
  const dayKey = dayGroups[page]?.[0];
  const label = dayKey ? formatActivityDayLabel(dayKey) : "No data";
  const nouns = { timeline: "event", runs: "run", decisions: "decision" };
  const newerDisabled = page <= 0 ? "disabled" : "";
  const olderDisabled = page >= totalDays - 1 ? "disabled" : "";
  const pageHint =
    totalDays > 1 ? `<span class="muted">· Day ${page + 1} of ${totalDays}</span>` : "";
  return `
    <div class="activity-day-nav">
      <button type="button" class="activity-day-btn" data-day-nav="${section}" data-direction="older" ${olderDisabled}>← Older</button>
      <div class="activity-day-label">
        <strong>${escapeHtml(label)}</strong>
        <span class="muted">${activityCountLabel(items.length, nouns[section])}</span>
        ${pageHint}
      </div>
      <button type="button" class="activity-day-btn" data-day-nav="${section}" data-direction="newer" ${newerDisabled}>Newer →</button>
    </div>
  `;
}

function shiftActivityDayPage(section, direction, dayCount) {
  if (dayCount <= 0) return;
  if (direction === "newer" && activityDayPage[section] > 0) activityDayPage[section] -= 1;
  if (direction === "older" && activityDayPage[section] < dayCount - 1) activityDayPage[section] += 1;
}

function bindActivityPanelLinks(container) {
  container.querySelectorAll("[data-run-id]").forEach((btn) => {
    btn.addEventListener("click", () => openRunModal(Number(btn.dataset.runId)));
  });
  container.querySelectorAll("[data-symbol]").forEach((btn) => {
    btn.addEventListener("click", () => openSymbolModal(btn.dataset.symbol));
  });
}

function renderPlanListTable(title, rows, columns) {
  if (!rows?.length) {
    return `<h3>${title}</h3><p class="muted">None configured.</p>`;
  }
  const head = columns.map((col) => `<th>${col.label}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((col) => {
          const raw = typeof col.render === "function" ? col.render(row) : row[col.key];
          const cls = col.wrap ? ' class="cell-wrap"' : "";
          return `<td${cls}>${escapeHtml(raw ?? "—")}</td>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  return `
    <h3>${title}</h3>
    <div class="table-wrap">
      <table class="data-table compact-table">
        <thead><tr>${head}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function renderAgentPlanBody(plan) {
  const githubUrl = planGithubEditUrl(plan.version);
  const meta = `
    <div class="agent-plan-meta">
      <p><strong>${escapeHtml(plan.name)}</strong> · version ${escapeHtml(plan.version)}</p>
      <p class="muted">Source: ${escapeHtml(plan.change_source)} · updated ${escapeHtml(plan.updated_at)}</p>
      ${
        githubUrl
          ? `<p><a href="${githubUrl}" target="_blank" rel="noopener noreferrer">Edit on GitHub</a></p>`
          : `<p class="muted">Plan edit links not configured (<code>MTA_PLANS_REPO_URL</code> variable or local <code>config.js</code>).</p>`
      }
    </div>
  `;

  const runOrder = renderPlanListTable("Run order", plan.run_order, [
    { key: "step", label: "Step" },
    { key: "action", label: "Action" },
    { key: "description", label: "Description", wrap: true },
    {
      label: "Endpoint / source",
      wrap: true,
      render: (row) => row.endpoint || row.source || "—",
    },
    { key: "required", label: "Required", render: (row) => (row.required ? "yes" : "no") },
  ]);

  const requiredInputs = renderPlanListTable("Required inputs", plan.required_inputs, [
    { key: "name", label: "Name" },
    { key: "source", label: "Source", wrap: true },
    { key: "description", label: "Description", wrap: true },
    { key: "required", label: "Required", render: (row) => (row.required ? "yes" : "no") },
  ]);

  const scoringRules = renderPlanListTable("Scoring rules", plan.scoring_rules, [
    { key: "id", label: "ID" },
    { key: "priority", label: "Priority" },
    { key: "rule", label: "Rule", wrap: true },
  ]);

  const dataSources = renderPlanListTable("Data sources", plan.data_sources, [
    { key: "name", label: "Name" },
    { key: "type", label: "Type" },
    { key: "description", label: "Description", wrap: true },
    { key: "url", label: "URL", wrap: true },
    {
      label: "Tools",
      wrap: true,
      render: (row) => (row.tools?.length ? row.tools.join(", ") : "—"),
    },
  ]);

  const stopConditions = renderPlanListTable("Stop conditions", plan.stop_conditions, [
    { key: "condition", label: "Condition" },
    { key: "action", label: "Action" },
    { key: "description", label: "Description", wrap: true },
  ]);

  return `${meta}${runOrder}${requiredInputs}${scoringRules}${dataSources}${stopConditions}`;
}

async function loadAgentPlanForLane(laneId) {
  if (agentPlanCache.has(laneId)) {
    return agentPlanCache.get(laneId);
  }
  const plan = await fetchJson(`/api/automation/plan?lane_id=${laneId}`);
  agentPlanCache.set(laneId, plan);
  return plan;
}

async function hydrateAgentPlanPanel(laneId) {
  const panel = document.querySelector(`#plan-lane-${laneId} .agent-plan-body`);
  if (!panel || panel.dataset.loaded === "true") {
    return;
  }
  panel.textContent = "Loading plan...";
  try {
    const plan = await loadAgentPlanForLane(laneId);
    panel.innerHTML = renderAgentPlanBody(plan);
    panel.dataset.loaded = "true";
  } catch (error) {
    panel.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
  }
}

function openAgentPlanPanel(laneId) {
  const details = document.getElementById(`plan-lane-${laneId}`);
  if (!details) {
    return;
  }
  navigateToDashboardView("lanes");
  details.open = true;
  hydrateAgentPlanPanel(laneId);
  requestAnimationFrame(() => {
    details.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function renderAgentPlansPanel(lanes) {
  const panel = document.getElementById("agent-plans-panel");
  if (!lanes?.length) {
    panel.innerHTML = "<p class='muted'>No lanes configured.</p>";
    return;
  }

  agentPlanCache.clear();
  const roleOrder = { live: 0, shadow: 1, research: 2 };
  const sorted = [...lanes].sort(
    (a, b) => (roleOrder[a.lane_role] ?? 9) - (roleOrder[b.lane_role] ?? 9) || a.id - b.id
  );

  panel.innerHTML = sorted
    .map(
      (lane) => `
        <details class="agent-plan-panel" id="plan-lane-${lane.id}" data-lane-id="${lane.id}">
          <summary class="agent-plan-summary">
            <span>#${lane.id} ${escapeHtml(lane.name)} ${laneRoleBadge(lane.lane_role)}</span>
            <span class="muted plan-meta-line">Plan ${escapeHtml(lane.plan_version)} · Strategy ${escapeHtml(lane.strategy_version)}</span>
          </summary>
          <div class="agent-plan-body muted">Expand to load plan details.</div>
        </details>
      `
    )
    .join("");

  panel.querySelectorAll(".agent-plan-panel").forEach((details) => {
    details.addEventListener("toggle", () => {
      if (details.open) {
        hydrateAgentPlanPanel(Number(details.dataset.laneId));
      }
    });
  });
}

// Distinct hues per lane (colorblind-friendly on the green dashboard background).
const LANE_CHART_PALETTE = [
  "#1e6f4a", // lane 1 — forest green
  "#1d4ed8", // lane 2 — blue
  "#c2410c", // lane 3 — orange
  "#7c3aed", // lane 4 — violet
  "#0891b2", // lane 5 — cyan
  "#be185d", // lane 6 — rose
];

function getLaneChartColor(laneId, fallbackIndex = 0) {
  if (laneId != null && laneId >= 1 && laneId <= LANE_CHART_PALETTE.length) {
    return LANE_CHART_PALETTE[laneId - 1];
  }
  return LANE_CHART_PALETTE[fallbackIndex % LANE_CHART_PALETTE.length];
}

function renderEquityLaneControls(lanes, selectedIds, onChange) {
  const panel = document.getElementById("equity-lane-controls");
  if (!lanes?.length) {
    panel.innerHTML = "";
    return;
  }
  panel.innerHTML = lanes
    .map(
      (lane, index) => `
        <label class="lane-chip">
          <input type="checkbox" data-lane-id="${lane.id}" ${selectedIds.has(lane.id) ? "checked" : ""} />
          <span style="color:${getLaneChartColor(lane.id, index)}">#${lane.id} ${lane.name}</span>
        </label>
      `
    )
    .join("");
  panel.querySelectorAll("input[data-lane-id]").forEach((input) => {
    input.addEventListener("change", () => onChange());
  });
}

function renderMultiEquityCurve(laneSeries) {
  const panel = document.getElementById("equity-curve-panel");
  const seriesList = laneSeries.filter((s) => s.snapshots?.length);
  if (!seriesList.length) {
    panel.innerHTML =
      "<p>No portfolio snapshots yet. Snapshots are recorded per lane after each completed run.</p>";
    return;
  }

  const width = 640;
  const height = 220;
  const padX = 48;
  const padY = 28;
  const plotWidth = width - padX * 2;
  const plotHeight = height - padY * 2;

  let minEquity = Infinity;
  let maxEquity = -Infinity;
  seriesList.forEach((series) => {
    series.snapshots.forEach((row) => {
      minEquity = Math.min(minEquity, row.total_equity_usd);
      maxEquity = Math.max(maxEquity, row.total_equity_usd);
    });
  });
  const range = maxEquity - minEquity || 1;

  const polylines = seriesList
    .map((series, seriesIndex) => {
      const sorted = [...series.snapshots].sort((a, b) =>
        a.snapshot_at.localeCompare(b.snapshot_at)
      );
      const points = sorted
        .map((row, index) => {
          const x = padX + (index / Math.max(sorted.length - 1, 1)) * plotWidth;
          const y = padY + (1 - (row.total_equity_usd - minEquity) / range) * plotHeight;
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(" ");
      const color = getLaneChartColor(series.laneId, seriesIndex);
      return `<polyline points="${points}" class="chart-line lane-line" style="stroke:${color}" />`;
    })
    .join("");

  const legend = seriesList
    .map(
      (series, index) =>
        `<span style="color:${getLaneChartColor(series.laneId, index)}">#${series.laneId} ${series.name}</span>`
    )
    .join(" · ");

  panel.innerHTML = `
    <div class="equity-curve-meta">${legend}</div>
    <svg class="equity-curve-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Multi-lane equity curves">
      <line x1="${padX}" y1="${height - padY}" x2="${width - padX}" y2="${height - padY}" class="chart-axis" />
      <line x1="${padX}" y1="${padY}" x2="${padX}" y2="${height - padY}" class="chart-axis" />
      <text x="${padX - 6}" y="${padY + 4}" class="chart-label">${formatMoney(maxEquity)}</text>
      <text x="${padX - 6}" y="${height - padY + 4}" class="chart-label">${formatMoney(minEquity)}</text>
      ${polylines}
    </svg>
    <p class="muted">Overlay per-lane snapshot equity (select lanes above).</p>
  `;
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
  const modeStatus = document.getElementById("sidebar-mode-status");
  const runStatus = document.getElementById("sidebar-run-status");
  const statusDot = document.getElementById("sidebar-status-dot");
  if (!status) {
    bar.hidden = true;
    if (modeStatus) modeStatus.textContent = "Status unavailable";
    if (runStatus) runStatus.textContent = "Dashboard API did not return a summary";
    if (statusDot) statusDot.className = "status-dot warn";
    return;
  }
  bar.hidden = false;
  bar.innerHTML = `
    <span class="${badgeClass(status.strategy_mode)}">${status.strategy_mode}</span>
    <span>Equity ${formatMoney(status.total_equity_usd)}</span>
    ${status.live_lane_name ? `<span>Live lane: ${status.live_lane_name}</span>` : ""}
    <span>Alerts ${status.open_alerts}</span>
    <span>Kill ${status.kill_switch ? "ON" : "off"}</span>
    <span class="${status.budget_ok ? "good" : "bad"}">Budget ${status.budget_ok ? "ok" : "exceeded"}</span>
    <span class="muted">${status.last_run_at ? `Last run ${status.last_run_status}` : "No runs"}</span>
  `;
  if (modeStatus) {
    modeStatus.textContent = `${status.strategy_mode} · ${status.live_lane_name || "no live lane"}`;
  }
  if (runStatus) {
    runStatus.textContent = status.last_run_at
      ? `Last run ${status.last_run_status} · ${status.open_alerts} open alert${status.open_alerts === 1 ? "" : "s"}`
      : `No runs yet · ${status.open_alerts} open alert${status.open_alerts === 1 ? "" : "s"}`;
  }
  if (statusDot) {
    const statusClass = status.kill_switch || !status.budget_ok ? "bad" : status.open_alerts > 0 ? "warn" : "good";
    statusDot.className = `status-dot ${statusClass}`;
  }
}

function renderStats(stats) {
  const items = [
    ["Runs", stats.total_runs],
    ["Completed", stats.completed_runs],
    ["Failed", stats.failed_runs],
    ["Decisions", stats.total_decisions],
    ["Sim trades", stats.simulated_trades],
    ["Live trades", stats.live_trades],
    ["Holds", stats.holds_and_skips],
    ["Cursor cost", formatMoney(stats.total_cursor_cost_usd)],
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

function renderCostPeriodCard(label, period) {
  if (!period) return "";
  const detail = [
    period.row_count != null ? `${period.row_count} rows` : null,
    period.run_count != null ? `${period.run_count} runs` : null,
    period.cost_per_run_usd != null ? `${formatMoney(period.cost_per_run_usd)}/run` : null,
    period.avg_per_day_usd != null ? `${formatMoney(period.avg_per_day_usd)}/day` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return `
    <div class="cost-period-card">
      <span>${label}</span>
      <strong>${formatMoney(period.cost_usd)}</strong>
      ${detail ? `<span>${detail}</span>` : ""}
    </div>
  `;
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
  const laneRows = (summary.by_lane || [])
    .map((row) => `<tr><td>${row.key}</td><td>${formatMoney(row.cost_usd)}</td><td>${row.row_count}</td></tr>`)
    .join("");

  const projections = summary.projections;
  const projectionHtml = projections
    ? `<div class="cost-period-grid">
        <div class="cost-period-card">
          <span>Projected weekly (all automations)</span>
          <strong>${formatMoney(projections.projected_weekly_usd)}</strong>
          <span>${formatMoney(projections.avg_daily_usd)}/day avg · ${projections.active_lane_count} active lanes</span>
        </div>
        <div class="cost-period-card">
          <span>Projected monthly (all automations)</span>
          <strong>${formatMoney(projections.projected_monthly_usd)}</strong>
          <span>Based on trailing 7-day daily average</span>
        </div>
        ${
          projections.projected_weekly_per_lane_usd != null
            ? `<div class="cost-period-card">
                <span>Projected weekly per lane</span>
                <strong>${formatMoney(projections.projected_weekly_per_lane_usd)}</strong>
                <span>Even split across ${projections.active_lane_count} lanes</span>
              </div>`
            : ""
        }
      </div>`
    : "";

  document.getElementById("cost-dashboard-panel").innerHTML = `
    <div class="equity-curve-meta">
      <span>Effective total: ${formatMoney(summary.total_effective_cost_usd ?? summary.total_cost_usd)}</span>
      <span>Billed: ${formatMoney(summary.total_cost_usd)}</span>
      <span>Est. (tokens): ${formatMoney(summary.total_estimated_cost_usd ?? 0)}</span>
      <span>${summary.usage_row_count} usage rows</span>
      <span>Cost/decision: ${summary.estimated_cost_per_decision != null ? formatMoney(summary.estimated_cost_per_decision) : summary.cost_per_decision != null ? formatMoney(summary.cost_per_decision) : "—"}</span>
    </div>
    <div class="cost-period-grid">
      ${renderCostPeriodCard("This week", summary.this_week)}
      ${renderCostPeriodCard("This month", summary.this_month)}
      ${renderCostPeriodCard("Last 7 days", summary.last_7_days)}
      ${renderCostPeriodCard("Last 30 days", summary.last_30_days)}
    </div>
    ${projectionHtml}
    ${
      days.length
        ? `<svg class="equity-curve-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Cursor cost over time">
            <polyline points="${points}" class="chart-line" />
          </svg>`
        : "<p class='muted'>No daily cost data yet.</p>"
    }
    <div class="cost-breakdown-grid">
      <div>
        <h3>By lane</h3>
        <table><thead><tr><th>Lane</th><th>Cost</th><th>Rows</th></tr></thead><tbody>${laneRows || "<tr><td colspan='3'>—</td></tr>"}</tbody></table>
      </div>
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

function renderPortfolio(portfolio, laneMeta) {
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

  const laneLabel = laneMeta
    ? `<p class="muted">Showing lane #${laneMeta.id} <strong>${laneMeta.name}</strong> ${laneRoleBadge(laneMeta.lane_role)} · ${laneRoleLabel(laneMeta.lane_role)}</p>`
    : "";

  document.getElementById("portfolio-panel").innerHTML = `
    ${laneLabel}
    <p>Cash: ${formatMoney(portfolio.cash_usd)}</p>
    <p>Total equity: ${formatMoney(portfolio.total_equity)}</p>
    <p>Unrealized P&amp;L: ${formatMoney(portfolio.total_unrealized_pnl)}</p>
    <div class="table-wrap">
      <table class="data-table">
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
    </div>
  `;

  document.getElementById("portfolio-panel").querySelectorAll("[data-symbol]").forEach((row) => {
    row.addEventListener("click", (event) => {
      event.preventDefault();
      openSymbolModal(row.dataset.symbol);
    });
  });
}

function renderSnapshotSummary(summary, laneMeta) {
  const label = document.getElementById("snapshot-lane-label");
  if (label) {
    label.textContent = laneMeta ? `#${laneMeta.id} ${laneMeta.name}` : "";
  }
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
          <td class="cell-wrap">${row.detail || "—"}</td>
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
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>Source</th><th>Last updated</th><th>Age / max</th><th>Status</th><th>Detail</th></tr></thead>
        <tbody>${body || `<tr><td colspan="5">No freshness data yet.</td></tr>`}</tbody>
      </table>
    </div>
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
  const dayGroups = groupRecordsByDay(events, "at");
  const page = dayGroups.length
    ? Math.min(activityDayPage.timeline, dayGroups.length - 1)
    : 0;
  activityDayPage.timeline = page;
  const dayEvents = dayGroups[page]?.[1] || [];

  const rows = dayEvents
    .map((event) => {
      const runLink =
        event.run_id != null
          ? `<button type="button" class="link-btn" data-run-id="${event.run_id}">#${event.run_id}</button>`
          : "";
      const symbolLink = event.symbol
        ? `<button type="button" class="link-btn" data-symbol="${event.symbol}">${event.symbol}</button>`
        : "";
      return `
        <li class="timeline-item timeline-item-compact">
          <div class="timeline-row">
            <span class="${timelineBadge(event.event_type)}">${event.event_type}</span>
            <time>${formatActivityTime(event.at)}</time>
            <span class="timeline-title">${event.title}</span>
            ${symbolLink}
            ${runLink}
          </div>
        </li>
      `;
    })
    .join("");

  const panel = document.getElementById("timeline-panel");
  panel.innerHTML = `
    ${renderActivityDayNav("timeline", dayGroups, dayEvents)}
    <ul class="timeline timeline-compact">${rows || "<li class='muted'>No events on this day.</li>"}</ul>
  `;
  bindActivityPanelLinks(panel);
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
  const dayGroups = groupRecordsByDay(runs, "run_at");
  const page = dayGroups.length ? Math.min(activityDayPage.runs, dayGroups.length - 1) : 0;
  activityDayPage.runs = page;
  const dayRuns = dayGroups[page]?.[1] || [];

  const rows = dayRuns
    .map(
      (run) => `
        <tr class="clickable-row" data-run-id="${run.id}" title="View run #${run.id}">
          <td>${formatActivityTime(run.run_at)}</td>
          <td>${escapeHtml(run.automation_name || "—")}</td>
          <td>${run.lane_name ? `${laneRoleBadge(run.lane_role || "research")} ${escapeHtml(run.lane_name)}` : "—"}</td>
          <td>${escapeHtml(run.run_type || "—")}</td>
          <td>${run.status}</td>
          <td>${run.budget_exceeded ? '<span class="warn">budget</span>' : ""}</td>
        </tr>
      `
    )
    .join("");

  const wrap = document.getElementById("runs-table-wrap");
  wrap.innerHTML = `
    ${renderActivityDayNav("runs", dayGroups, dayRuns)}
    <table>
      <thead>
        <tr><th>Time</th><th>Automation</th><th>Lane</th><th>Run type</th><th>Status</th><th></th></tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="6">No runs on this day.</td></tr>`}</tbody>
    </table>
  `;
  wrap.querySelectorAll("[data-run-id]").forEach((row) => {
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
        run.lane_name
          ? `<p>Lane: #${run.lane_id} ${run.lane_name} ${laneRoleBadge(run.lane_role || "research")}</p>`
          : run.lane_id
            ? `<p>Lane: #${run.lane_id}</p>`
            : ""
      }
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

async function openSymbolModal(symbol, { updateHash = true } = {}) {
  const modal = document.getElementById("symbol-modal");
  const body = document.getElementById("symbol-modal-body");
  const normalizedSymbol = symbol.toUpperCase();
  modal.hidden = false;
  body.textContent = "Loading...";
  document.getElementById("symbol-modal-title").textContent = normalizedSymbol;
  if (updateHash) {
    symbolReturnHash = `#${activeDashboardView}`;
    history.pushState(null, "", `#symbol/${normalizedSymbol}`);
  }
  try {
    const memory = await fetchJson(`/api/automation/symbols/${encodeURIComponent(normalizedSymbol)}/memory`);
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
    history.replaceState(null, "", symbolReturnHash);
    setDashboardView(activeDashboardView);
  }
}

async function downloadExportJson() {
  const response = await fetch(`${API_BASE}/api/dashboard/export?format=json&type=all`, {
    headers: apiHeaders({ json: false }),
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
    headers: apiHeaders({ json: false }),
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

function renderDecisionLane(decision) {
  if (!decision.lane_name) return "—";
  const role = decision.lane_role || "research";
  return `${laneRoleBadge(role)} ${escapeHtml(decision.lane_name)}`;
}

function renderDecisions(decisions) {
  const dayGroups = groupRecordsByDay(decisions, "created_at");
  const page = dayGroups.length
    ? Math.min(activityDayPage.decisions, dayGroups.length - 1)
    : 0;
  activityDayPage.decisions = page;
  const dayDecisions = dayGroups[page]?.[1] || [];

  const rows = dayDecisions
    .map(
      (decision) => `
        <tr>
          <td>${formatActivityTime(decision.created_at)}</td>
          <td>${renderDecisionLane(decision)}</td>
          <td><button type="button" class="link-btn" data-symbol="${decision.symbol}">${decision.symbol}</button></td>
          <td>${decision.action}</td>
          <td>${renderScoreBars(decision.scores)}</td>
          <td>${formatMoney(decision.amount_usd)}</td>
        </tr>
      `
    )
    .join("");

  const wrap = document.getElementById("decisions-table-wrap");
  wrap.innerHTML = `
    ${renderActivityDayNav("decisions", dayGroups, dayDecisions)}
    <table>
      <thead>
        <tr><th>Time</th><th>Lane</th><th>Symbol</th><th>Action</th><th>Scores</th><th>Amount</th></tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="6">No decisions on this day.</td></tr>`}</tbody>
    </table>
    <p class="muted activity-hint">Open a symbol or run for full reason and rationale.</p>
  `;
  bindActivityPanelLinks(wrap);
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
          <td>${formatMoney(row.estimated_cost_usd)}</td>
          <td>${formatMoney(row.effective_cost_usd ?? row.cost_usd)}</td>
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
        <tr><th>Time</th><th>Run ID</th><th>Model</th><th>Billed</th><th>Est.</th><th>Effective</th><th>Input</th><th>Output</th><th>Source</th></tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="9">No usage logged yet.</td></tr>`}</tbody>
    </table>
  `;
}

let dashboardLanes = [];
let selectedPortfolioLaneId = null;
let selectedEquityLaneIds = null;
let liveTradingHistory = null;

function populatePortfolioLaneSelect(lanes, preferredLaneId) {
  const select = document.getElementById("portfolio-lane-select");
  if (!select) return preferredLaneId;
  const liveLane = lanes.find((lane) => lane.lane_role === "live" && lane.status === "active");
  const retainedLaneId = lanes.some((lane) => lane.id === selectedPortfolioLaneId)
    ? selectedPortfolioLaneId
    : null;
  const defaultId = retainedLaneId || preferredLaneId || liveLane?.id || lanes[0]?.id || 1;
  select.innerHTML = lanes
    .map(
      (lane) =>
        `<option value="${lane.id}" ${lane.id === defaultId ? "selected" : ""}>#${lane.id} ${lane.name} (${lane.lane_role})</option>`
    )
    .join("");
  select.onchange = () => selectPortfolioLane(Number(select.value));
  return defaultId;
}

function laneMetaForId(laneId) {
  return dashboardLanes.find((lane) => lane.id === laneId) || null;
}

async function selectPortfolioLane(laneId) {
  selectedPortfolioLaneId = laneId;
  navigateToDashboardView("lanes");
  const select = document.getElementById("portfolio-lane-select");
  if (select && Number(select.value) !== laneId) {
    select.value = String(laneId);
  }
  await loadPortfolioForLane(laneId);
  document.getElementById("portfolio-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function loadPortfolioForLane(laneId) {
  const [portfolio, snapshotSummary] = await Promise.all([
    fetchJson(`/api/dashboard/portfolio?lane_id=${laneId}`),
    fetchJson(`/api/dashboard/portfolio/snapshots/summary?lane_id=${laneId}`).catch(() => null),
  ]);
  const laneMeta = laneMetaForId(laneId);
  renderPortfolio(portfolio, laneMeta);
  renderSnapshotSummary(snapshotSummary, laneMeta);
}

async function loadEquityCurvesForLanes(lanes) {
  const selected = new Set(
    [...document.querySelectorAll("#equity-lane-controls input[data-lane-id]:checked")].map((el) =>
      Number(el.dataset.laneId)
    )
  );
  const activeIds =
    selected.size > 0 ? [...selected] : lanes.filter((l) => l.status === "active").map((l) => l.id);
  const series = await Promise.all(
    activeIds.map(async (laneId) => {
      const lane = lanes.find((l) => l.id === laneId);
      const snapshots = await fetchJson(`/api/dashboard/portfolio/snapshots?lane_id=${laneId}&limit=200`).catch(
        () => []
      );
      return { laneId, name: lane?.name || `lane-${laneId}`, snapshots };
    })
  );
  renderMultiEquityCurve(series);
}

async function loadDashboard() {
  const errorBanner = document.getElementById("error-banner");
  const loadingBar = document.getElementById("global-loading");
  const refreshButton = document.getElementById("refresh-btn");
  errorBanner.hidden = true;
  loadingBar.hidden = false;
  refreshButton.disabled = true;
  refreshButton.setAttribute("aria-busy", "true");

  try {
    const [
      stats,
      context,
      runs,
      decisions,
      usage,
      usageSummary,
      orders,
      reconciliation,
      timeline,
      freshnessChecks,
      alerts,
      compare,
      laneCompare,
      lanes,
      liveHistory,
      mobileStatus,
    ] = await Promise.all([
      fetchJson("/api/dashboard/stats"),
      fetchJson("/api/automation/context"),
      fetchJson("/api/dashboard/runs?limit=25"),
      fetchJson("/api/dashboard/decisions?limit=50"),
      fetchJson("/api/dashboard/usage?limit=25"),
      fetchJson("/api/dashboard/usage/summary").catch(() => null),
      fetchJson("/api/dashboard/orders?limit=25"),
      fetchJson("/api/dashboard/reconciliation"),
      fetchJson("/api/dashboard/timeline?limit=80"),
      fetchJson("/api/dashboard/freshness/check"),
      fetchJson("/api/dashboard/alerts?limit=50").catch(() => []),
      fetchJson("/api/dashboard/strategy/compare").catch(() => null),
      fetchJson("/api/dashboard/lanes/compare").catch(() => null),
      fetchJson("/api/dashboard/lanes").catch(() => []),
      fetchJson("/api/dashboard/lanes/live-history").catch(() => null),
      fetchJson("/api/dashboard/status/mobile").catch(() => null),
    ]);

    renderStats(stats);
    renderStrategy(context);
    renderSafetyControls(context);
    dashboardLanes = lanes || [];
    liveTradingHistory = liveHistory;
    selectedPortfolioLaneId = populatePortfolioLaneSelect(
      dashboardLanes,
      liveHistory?.current_live_lane_id || context.lane_id
    );
    await loadPortfolioForLane(selectedPortfolioLaneId);
    renderLiveMoneyTrack(liveHistory, laneCompare);
    renderLanesPanel(dashboardLanes, liveHistory);
    renderAgentPlansPanel(dashboardLanes);
    renderLaneCompare(laneCompare);
    const availableLaneIds = new Set(dashboardLanes.map((lane) => lane.id));
    if (selectedEquityLaneIds === null) {
      selectedEquityLaneIds = new Set(availableLaneIds);
    } else {
      selectedEquityLaneIds = new Set(
        [...selectedEquityLaneIds].filter((laneId) => availableLaneIds.has(laneId))
      );
    }
    renderEquityLaneControls(dashboardLanes, selectedEquityLaneIds, async () => {
      selectedEquityLaneIds = new Set(
        [...document.querySelectorAll("#equity-lane-controls input[data-lane-id]:checked")].map((input) =>
          Number(input.dataset.laneId)
        )
      );
      await loadEquityCurvesForLanes(dashboardLanes);
    });
    await loadEquityCurvesForLanes(dashboardLanes);
    renderCostDashboard(usageSummary);
    renderFreshness(freshnessChecks);
    renderReconciliation(reconciliation);
    activityData.timeline = timeline;
    activityData.runs = runs;
    activityData.decisions = decisions;
    activityDayPage.timeline = 0;
    activityDayPage.runs = 0;
    activityDayPage.decisions = 0;
    renderTimeline(timeline);
    renderOrders(orders);
    renderRuns(runs);
    renderUsage(usage);
    renderDecisions(decisions);
    renderAlerts(alerts);
    renderStrategyCompare(compare);
    renderMobileStatus(mobileStatus);
    const updatedAt = document.getElementById("dashboard-last-updated");
    if (updatedAt) {
      updatedAt.textContent = `Updated ${new Intl.DateTimeFormat(undefined, {
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
      }).format(new Date())}`;
    }
    showAppShell();
    routeDashboardHash();
  } catch (error) {
    if (error.message === "Authentication required") {
      return;
    }
    errorBanner.hidden = false;
    errorBanner.textContent = `Failed to load dashboard: ${error.message}. Check MTA_API_BASE_URL (GitHub variable or local config.js) and API CORS settings.`;
  } finally {
    loadingBar.hidden = true;
    refreshButton.disabled = false;
    refreshButton.removeAttribute("aria-busy");
  }
}

async function fetchAuthStatus() {
  const response = await fetch(`${API_BASE}/api/auth/status`);
  if (!response.ok) {
    throw new Error(`auth status failed with ${response.status}`);
  }
  return response.json();
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

  document.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-day-nav]");
    if (!btn) return;
    const section = btn.dataset.dayNav;
    const direction = btn.dataset.direction;
    if (section === "timeline") {
      shiftActivityDayPage("timeline", direction, groupRecordsByDay(activityData.timeline, "at").length);
      renderTimeline(activityData.timeline);
    } else if (section === "runs") {
      shiftActivityDayPage("runs", direction, groupRecordsByDay(activityData.runs, "run_at").length);
      renderRuns(activityData.runs);
    } else if (section === "decisions") {
      shiftActivityDayPage(
        "decisions",
        direction,
        groupRecordsByDay(activityData.decisions, "created_at").length
      );
      renderDecisions(activityData.decisions);
    }
  });

  window.addEventListener("hashchange", routeDashboardHash);

  if (API_READ_KEY) {
    showAppShell();
    await loadDashboard();
    return;
  }

  try {
    const authStatus = await fetchAuthStatus();
    if (!authStatus.dashboard_login_required && !authStatus.read_key_required) {
      setSessionToken(null);
      showAppShell();
      await loadDashboard();
      return;
    }
  } catch {
    document.getElementById("login-error").hidden = false;
    document.getElementById("login-error").textContent =
      "Cannot reach API. Start the API on port 8000 and open http://localhost:8080.";
    showLoginScreen();
    return;
  }

  if (getSessionToken()) {
    showAppShell();
    await loadDashboard();
    return;
  }

  showLoginScreen();
}

bootstrap();
