// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────
async function fetchJson(url, options = {}) {
  const resp = await fetch(url, {
    headers: { Accept: "application/json" },
    ...options,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body?.detail?.message ?? body?.detail ?? detail;
    } catch { /* ignore parse failure */ }
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }
  return resp.json();
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function formatDuration(s) {
  if (!Number.isFinite(s) || s < 60) return `${Math.max(0, Math.round(s))}s`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function setStatusPill(id, configured) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = configured ? "Configured" : "Missing";
  el.classList.toggle("is-healthy", configured);
  el.classList.toggle("is-degraded", !configured);
}

function showToast(msg, type = "info") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = `toast toast-${type} show`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 3800);
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab system
// ─────────────────────────────────────────────────────────────────────────────
const tabCallbacks = {};

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const name = btn.dataset.tab;
    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.classList.toggle("active", b === btn);
      b.setAttribute("aria-selected", b === btn ? "true" : "false");
    });
    document.querySelectorAll(".tab-panel").forEach((p) => {
      p.classList.toggle("hidden", p.id !== `tab-${name}`);
    });
    tabCallbacks[name]?.();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Overview tab — polls /api/v1/system/overview
// ─────────────────────────────────────────────────────────────────────────────
function renderRoutes(routes, total) {
  const c = document.getElementById("topRoutes");
  c.replaceChildren();
  if (!routes.length) {
    const e = document.createElement("div");
    e.className = "empty-state";
    e.textContent = "Route activity will appear here after the API receives traffic.";
    c.append(e);
    return;
  }
  for (const r of routes) {
    const share = total > 0 ? (r.requests / total) * 100 : 0;
    const row = document.createElement("div");
    row.className = "route-row";
    row.innerHTML = `
      <div class="route-meta">
        <span class="route-path">${r.path}</span>
        <span class="route-count">${r.requests.toLocaleString()} req</span>
      </div>
      <div class="route-bar"><div class="route-fill" style="width:${Math.max(8, share)}%"></div></div>`;
    c.append(row);
  }
}

async function loadOverview() {
  try {
    const o = await fetchJson("/api/v1/system/overview");
    const { service, security, oauth, links, traffic } = o;

    const sc = document.getElementById("serviceStatus");
    sc.textContent = "Healthy";
    sc.className = "status-chip is-healthy";

    setText("environmentValue", service.environment);
    setText("uptimeValue", formatDuration(service.uptime_seconds));
    setText("apiModeValue", service.debug ? "debug" : "production");
    const prov = [oauth.google_configured, oauth.github_configured].filter(Boolean).length;
    setText("oauthSummaryValue", prov === 2 ? "all ready" : prov === 1 ? "partial" : "none configured");

    setText("totalRequestsValue", traffic.total_requests.toLocaleString());
    setText("latencyValue", `${traffic.average_latency_ms} ms`);
    setText("exceptionValue", traffic.exception_count.toLocaleString());
    setText("clientErrorsValue", traffic.client_error_responses.toLocaleString());
    setText("serverErrorsValue", traffic.server_error_responses.toLocaleString());
    setText("accessTtlValue", `${security.access_token_expire_minutes} min`);
    setText("refreshTtlValue", `${security.refresh_token_expire_days} days`);
    setText("rateLimitValue", `${security.rate_limit_auth_requests} / ${security.rate_limit_auth_window_seconds}s`);
    setText("corsCountValue", `${security.cors_origins.length} origin(s)`);

    setStatusPill("googleOauthState", oauth.google_configured);
    setStatusPill("githubOauthState", oauth.github_configured);

    function setLink(id, href) {
      const el = document.getElementById(id);
      if (!el) return;
      if (href) { el.href = href; el.removeAttribute("aria-disabled"); }
      else { el.removeAttribute("href"); el.setAttribute("aria-disabled", "true"); }
    }
    setLink("linkPrometheus", links.prometheus);
    setLink("linkGrafana", links.grafana);

    // stash for monitoring tab
    window._links = links;

    renderRoutes(traffic.top_routes, traffic.total_requests);
    setText("lastUpdatedValue", `synced ${new Date().toLocaleTimeString()}`);
  } catch {
    const sc = document.getElementById("serviceStatus");
    sc.textContent = "Degraded";
    sc.className = "status-chip is-degraded";
    setText("lastUpdatedValue", "sync failed");
  }
}

loadOverview();
setInterval(loadOverview, 15000);

// ─────────────────────────────────────────────────────────────────────────────
// Auth Lab tab
// ─────────────────────────────────────────────────────────────────────────────
let session = { accessToken: null, refreshToken: null, expiresAt: null, user: null };

// Rate limit tracking (client-side mirror of server state)
let rlUsed = 0;
let rlWindowStart = Date.now();
const RL_MAX = 5;
const RL_WINDOW_MS = 60000;

function rlIncrement() {
  const now = Date.now();
  if (now - rlWindowStart > RL_WINDOW_MS) { rlUsed = 0; rlWindowStart = now; }
  rlUsed = Math.min(rlUsed + 1, RL_MAX);
  updateRlBar();
}

function updateRlBar() {
  const pct = Math.min(100, (rlUsed / RL_MAX) * 100);
  const bar = document.getElementById("rlBar");
  if (bar) {
    bar.style.width = `${pct}%`;
    bar.className = `rl-bar${pct >= 100 ? " rl-full" : pct >= 60 ? " rl-warn" : ""}`;
  }
  setText("rlUsed", `${rlUsed} used`);
  setText("rlLimit", `of ${RL_MAX} per ${RL_WINDOW_MS / 1000}s`);
}

setInterval(() => {
  const remaining = Math.max(0, Math.ceil((rlWindowStart + RL_WINDOW_MS - Date.now()) / 1000));
  setText("rlCountdown", `${remaining}s`);
  if (remaining === 0) { rlUsed = 0; rlWindowStart = Date.now(); updateRlBar(); }
}, 500);

function showSession() {
  document.getElementById("noSession").classList.add("hidden");
  document.getElementById("sessionData").classList.remove("hidden");
  document.getElementById("logoutBtn").disabled = false;
  const u = session.user;
  document.getElementById("userBanner").innerHTML = `
    <span class="user-avatar">${(u.full_name || u.email)[0].toUpperCase()}</span>
    <div>
      <strong>${u.full_name || "—"}</strong>
      <p class="muted small">${u.email}</p>
    </div>`;
  const tok = session.accessToken;
  document.getElementById("accessTokenDisplay").textContent =
    `${tok.slice(0, 40)}…${tok.slice(-12)}`;
  updateTokenExpiry();
  setText("meId", `${u.id?.slice(0, 8)}…`);
  setText("meVerified", u.email_verified ? "Yes" : "No");
  setText("meActive", u.is_active ? "Yes" : "No");
  setText("meCreated", u.created_at ? new Date(u.created_at).toLocaleDateString() : "—");
}

function updateTokenExpiry() {
  if (!session.expiresAt) return;
  const secs = Math.round((session.expiresAt - Date.now()) / 1000);
  setText("tokenExpiry", secs > 0 ? `expires in ${formatDuration(secs)}` : "expired");
}
setInterval(updateTokenExpiry, 5000);

function clearSession() {
  session = { accessToken: null, refreshToken: null, expiresAt: null, user: null };
  document.getElementById("noSession")?.classList.remove("hidden");
  document.getElementById("sessionData")?.classList.add("hidden");
  const lb = document.getElementById("logoutBtn");
  if (lb) lb.disabled = true;
}

// Register
document.getElementById("registerForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const btn = document.getElementById("registerBtn");
  btn.disabled = true; btn.textContent = "Creating…";
  rlIncrement();
  try {
    const user = await fetchJson("/api/v1/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(fd)),
    });
    showToast(`Account created for ${user.email}. Now login below.`, "success");
    e.target.reset();
  } catch (err) {
    showToast(err.message || "Registration failed", "error");
  } finally {
    btn.disabled = false; btn.textContent = "Create Account";
  }
});

// Login
document.getElementById("loginForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const btn = document.getElementById("loginBtn");
  btn.disabled = true; btn.textContent = "Signing in…";
  rlIncrement();
  try {
    const data = await fetchJson("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(fd)),
    });
    session.accessToken = data.access_token;
    session.refreshToken = data.refresh_token;
    session.expiresAt = Date.now() + data.expires_in * 1000;
    session.user = data.user;
    showSession();
    showToast(`Welcome back, ${data.user.full_name || data.user.email}!`, "success");
    e.target.reset();
  } catch (err) {
    showToast(err.message || "Login failed", "error");
  } finally {
    btn.disabled = false; btn.textContent = "Sign In";
  }
});

// Logout
document.getElementById("logoutBtn")?.addEventListener("click", async () => {
  if (!session.refreshToken) { clearSession(); return; }
  try {
    await fetchJson("/api/v1/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.accessToken}` },
      body: JSON.stringify({ refresh_token: session.refreshToken }),
    });
    showToast("Logged out successfully.", "info");
  } catch {
    showToast("Server logout failed — cleared locally.", "error");
  }
  clearSession();
});

// Copy token
document.getElementById("copyTokenBtn")?.addEventListener("click", () => {
  if (!session.accessToken) return;
  navigator.clipboard.writeText(session.accessToken)
    .then(() => showToast("Full token copied to clipboard!", "success"))
    .catch(() => showToast("Clipboard access denied.", "error"));
});

// Quick-fill seed credentials
document.querySelectorAll(".seed-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const form = document.getElementById("loginForm");
    form.elements.email.value = btn.dataset.email;
    form.elements.password.value = btn.dataset.pw;
    showToast(`Login form filled — click Sign In.`, "info");
  });
});

// API Tester
document.getElementById("testerMethod")?.addEventListener("change", function () {
  document.getElementById("testerBodyRow").style.display =
    this.value === "POST" ? "block" : "none";
});

document.getElementById("testerSendBtn")?.addEventListener("click", async () => {
  const method = document.getElementById("testerMethod").value;
  const path = document.getElementById("testerPath").value.trim() || "/api/v1/auth/me";
  const bodyText = document.getElementById("testerBody").value.trim();
  const out = document.getElementById("testerOut");
  out.textContent = "Sending…";
  out.classList.remove("hidden", "out-ok", "out-err");

  const opts = {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
  };
  if (session.accessToken) opts.headers.Authorization = `Bearer ${session.accessToken}`;
  if (method !== "GET" && bodyText) opts.body = bodyText;

  try {
    const resp = await fetch(path, opts);
    let body;
    try { body = await resp.json(); } catch { body = await resp.text(); }
    out.className = `tester-out ${resp.ok ? "out-ok" : "out-err"}`;
    out.textContent = `HTTP ${resp.status} ${resp.statusText}\n\n${JSON.stringify(body, null, 2)}`;
  } catch (err) {
    out.className = "tester-out out-err";
    out.textContent = `Network error: ${err.message}`;
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// Live Charts tab — Chart.js + Prometheus proxy
// ─────────────────────────────────────────────────────────────────────────────
const PROM_PROXY = "/api/v1/system/prometheus-query";

async function queryProm(query, start, end, step = "30s") {
  const p = new URLSearchParams({ query, start, end, step });
  const data = await fetchJson(`${PROM_PROXY}?${p}`);
  return data?.data?.result ?? [];
}

const CHART_COLORS = ["#76e4ff", "#86efac", "#b79cff", "#ffbf69", "#ff7f7f"];
const ERR_COLORS   = ["#ff7f7f", "#ff5555", "#ffbf69"];

function promToDatasets(results, colors, transform = null) {
  if (!results.length) return { labels: [], datasets: [] };
  const labels = results[0].values.map(([ts]) =>
    new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  );
  const datasets = results.map((series, i) => {
    const label = Object.entries(series.metric)
      .filter(([k]) => ["path", "method", "status"].includes(k))
      .map(([k, v]) => `${k}=${v}`).join(" ") || "total";
    const data = series.values.map(([, v]) => {
      const n = parseFloat(v) || 0;
      return transform ? transform(n) : n;
    });
    return {
      label,
      data,
      borderColor: colors[i % colors.length],
      backgroundColor: colors[i % colors.length] + "15",
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.3,
      fill: true,
    };
  });
  return { labels, datasets };
}

function makeChart(canvasId, ylabel) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  return new window.Chart(ctx, {
    type: "line",
    data: { labels: [], datasets: [] },
    options: {
      responsive: true,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: { color: "#8fa4b8", font: { family: "Plus Jakarta Sans", size: 11 }, boxWidth: 12 },
        },
        tooltip: {
          backgroundColor: "#0b1823",
          borderColor: "rgba(154,176,194,0.2)",
          borderWidth: 1,
          titleColor: "#edf4fb",
          bodyColor: "#8fa4b8",
        },
      },
      scales: {
        x: {
          ticks: { color: "#8fa4b8", maxTicksLimit: 8, font: { size: 10 } },
          grid: { color: "rgba(255,255,255,0.04)" },
        },
        y: {
          beginAtZero: true,
          ticks: { color: "#8fa4b8", font: { size: 10 } },
          grid: { color: "rgba(255,255,255,0.04)" },
          title: { display: !!ylabel, text: ylabel, color: "#8fa4b8", font: { size: 10 } },
        },
      },
    },
  });
}

let charts = {};
let chartInterval = null;
let chartsReady = false;

function updateChart(chart, labels, datasets) {
  if (!chart) return;
  chart.data.labels = labels;
  chart.data.datasets = datasets;
  chart.update("none");
}

async function loadCharts() {
  if (!window.Chart) return;

  if (!chartsReady) {
    charts.rate = makeChart("chartRequestRate", "req/s");
    charts.lat  = makeChart("chartLatency", "ms");
    charts.err  = makeChart("chartErrors", "errors/s");
    chartsReady = true;
  }

  const now   = Math.floor(Date.now() / 1000);
  const start = now - 3600;
  const step  = "30s";

  const ps = document.getElementById("promStatus");
  try {
    // Request rate per-route
    const rateRes = await queryProm(`rate(smart_auth_http_requests_total[1m])`, start, now, step);
    const { labels: rl, datasets: rd } = promToDatasets(rateRes, CHART_COLORS);
    updateChart(charts.rate, rl, rd);

    // p95 latency → convert seconds to ms
    const latRes = await queryProm(
      `histogram_quantile(0.95, rate(smart_auth_http_request_duration_seconds_bucket[5m]))`,
      start, now, step
    );
    const { labels: ll, datasets: ld } = promToDatasets(latRes, ["#ffbf69", "#ffa94d"], (v) => +(v * 1000).toFixed(2));
    updateChart(charts.lat, ll, ld);

    // Error rate
    const errRes = await queryProm(
      `rate(smart_auth_http_requests_total{status=~"4..|5.."}[1m])`,
      start, now, step
    );
    const { labels: el, datasets: ed } = promToDatasets(errRes, ERR_COLORS);
    updateChart(charts.err, el, ed);

    // Instant totals
    const totRes = await queryProm(`smart_auth_http_requests_total`, now - 15, now, "15s");
    let grand = 0, success = 0;
    for (const s of totRes) {
      const v = parseFloat(s.values?.at(-1)?.[1] || 0);
      grand += v;
      if ((s.metric.status || "").startsWith("2")) success += v;
    }
    setText("instTotal", Math.round(grand).toLocaleString());

    const excRes = await queryProm(`smart_auth_http_exceptions_total`, now - 15, now, "15s");
    const exc = excRes.reduce((a, s) => a + parseFloat(s.values?.at(-1)?.[1] || 0), 0);
    setText("instExc", Math.round(exc).toLocaleString());
    setText("instSuccess", grand > 0 ? `${Math.round((success / grand) * 100)}%` : "—");

    if (ps) { ps.textContent = "Connected"; ps.className = "status-chip is-healthy"; }
  } catch (err) {
    if (ps) { ps.textContent = "Unavailable"; ps.className = "status-chip is-degraded"; }
    console.warn("Prometheus chart error:", err.message);
  }
}

tabCallbacks.charts = () => {
  loadCharts();
  if (!chartInterval) chartInterval = setInterval(loadCharts, 30000);
};

document.getElementById("chartsRefreshBtn")?.addEventListener("click", loadCharts);

// ─────────────────────────────────────────────────────────────────────────────
// Monitoring tab — embed Grafana panels via iframe
// ─────────────────────────────────────────────────────────────────────────────
let monitoringLoaded = false;

tabCallbacks.monitoring = () => {
  if (monitoringLoaded) return;
  monitoringLoaded = true;

  // Wait for overview to have populated links; fall back to default ports
  const base = window._links?.grafana || "http://localhost:13000";
  const uid  = "smart-auth-observability";
  const qs   = `orgId=1&from=now-1h&to=now&refresh=30s&theme=dark`;

  document.getElementById("grafanaPanel3").src = `${base}/d-solo/${uid}?panelId=3&${qs}`;
  document.getElementById("grafanaPanel1").src = `${base}/d-solo/${uid}?panelId=1&${qs}`;
  document.getElementById("grafanaPanel4").src = `${base}/d-solo/${uid}?panelId=4&${qs}`;

  const full = document.getElementById("grafanaFullLink");
  const prom = document.getElementById("prometheusLink");
  if (full) full.href = `${base}/d/${uid}`;
  if (prom) prom.href = window._links?.prometheus || "http://localhost:19090";
};

