async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`Request failed for ${url}`);
  }
  return response.json();
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 60) {
    return `${Math.max(0, Math.round(seconds))}s`;
  }

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function setLink(id, href) {
  const element = document.getElementById(id);
  if (!href) {
    element.removeAttribute("href");
    element.setAttribute("aria-disabled", "true");
    return;
  }

  element.href = href;
  element.removeAttribute("aria-disabled");
}

function setStatusPill(id, configured) {
  const element = document.getElementById(id);
  element.textContent = configured ? "Configured" : "Missing";
  element.classList.toggle("is-healthy", configured);
  element.classList.toggle("is-degraded", !configured);
}

function renderRoutes(routes, totalRequests) {
  const container = document.getElementById("topRoutes");
  container.replaceChildren();

  if (!routes.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Route activity will appear here after the API receives traffic.";
    container.append(empty);
    return;
  }

  for (const route of routes) {
    const row = document.createElement("div");
    row.className = "route-row";
    const share = totalRequests > 0 ? (route.requests / totalRequests) * 100 : 0;

    row.innerHTML = `
      <div class="route-meta">
        <span class="route-path">${route.path}</span>
        <span class="route-count">${route.requests.toLocaleString()} requests</span>
      </div>
      <div class="route-bar">
        <div class="route-fill" style="width: ${Math.max(8, share)}%"></div>
      </div>
    `;
    container.append(row);
  }
}

function updateServiceStatus(label, healthy) {
  const element = document.getElementById("serviceStatus");
  element.textContent = label;
  element.classList.toggle("is-healthy", healthy);
  element.classList.toggle("is-degraded", !healthy);
}

function hydrateDashboard(overview) {
  const { service, security, oauth, links, traffic } = overview;

  updateServiceStatus("Healthy", true);
  setText("environmentValue", service.environment);
  setText("uptimeValue", formatDuration(service.uptime_seconds));
  setText("apiModeValue", service.debug ? "debug enabled" : "production-safe");
  setText(
    "oauthSummaryValue",
    [oauth.google_configured, oauth.github_configured].filter(Boolean).length === 2 ? "all providers ready" : "partial setup"
  );

  setText("totalRequestsValue", traffic.total_requests.toLocaleString());
  setText("latencyValue", `${traffic.average_latency_ms.toLocaleString()} ms`);
  setText("exceptionValue", traffic.exception_count.toLocaleString());
  setText("clientErrorsValue", traffic.client_error_responses.toLocaleString());
  setText("serverErrorsValue", traffic.server_error_responses.toLocaleString());

  setText("accessTtlValue", `${security.access_token_expire_minutes} minutes`);
  setText("refreshTtlValue", `${security.refresh_token_expire_days} days`);
  setText(
    "rateLimitValue",
    `${security.rate_limit_auth_requests} requests / ${security.rate_limit_auth_window_seconds}s`
  );
  setText("corsCountValue", `${security.cors_origins.length} allowed origin(s)`);

  setStatusPill("googleOauthState", oauth.google_configured);
  setStatusPill("githubOauthState", oauth.github_configured);

  setLink("linkDocs", links.docs);
  setLink("linkHealth", links.health);
  setLink("linkMetrics", links.metrics);
  setLink("linkPrometheus", links.prometheus);
  setLink("linkGrafana", links.grafana);

  renderRoutes(traffic.top_routes, traffic.total_requests);
  setText("lastUpdatedValue", `synced ${new Date().toLocaleTimeString()}`);
}

async function loadDashboard() {
  try {
    const overview = await fetchJson("/api/v1/system/overview");
    hydrateDashboard(overview);
  } catch {
    updateServiceStatus("Degraded", false);
    setText("environmentValue", "unavailable");
    setText("uptimeValue", "unavailable");
    setText("apiModeValue", "unavailable");
    setText("oauthSummaryValue", "unavailable");
    setText("lastUpdatedValue", "sync failed");
    renderRoutes([], 0);
  }
}

loadDashboard();
window.setInterval(loadDashboard, 15000);
