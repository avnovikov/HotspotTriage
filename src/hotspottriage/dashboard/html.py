"""Embedded single-file dashboard HTML."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HotspotTriage Dashboard</title>
  <style>
    :root {
      --bg: #fcfcfa;
      --fg: #1f2937;
      --panel: #ffffff;
      --muted: #6b7280;
      --accent: #0f766e;
      --border: #d1d5db;
      --error: #b91c1c;
      --warn: #b45309;
      --ok: #047857;
      --debug: #475569;
      --shadow: rgba(15, 23, 42, 0.08);
    }
    body.dark {
      --bg: #0f172a;
      --fg: #e5e7eb;
      --panel: #111827;
      --muted: #9ca3af;
      --accent: #2dd4bf;
      --border: #374151;
      --error: #f87171;
      --warn: #fbbf24;
      --ok: #34d399;
      --debug: #cbd5e1;
      --shadow: rgba(0, 0, 0, 0.35);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--fg);
      min-height: 100vh;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      background: var(--bg);
      z-index: 5;
    }
    h1 { font-size: 1rem; margin: 0; letter-spacing: 0.02em; }
    .toolbar { display: flex; align-items: center; gap: 0.5rem; }
    button {
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      color: var(--fg);
      padding: 0.35rem 0.6rem;
      cursor: pointer;
    }
    button:hover { border-color: var(--accent); }
    .badge {
      border-radius: 999px;
      padding: 0.2rem 0.55rem;
      border: 1px solid var(--border);
      font-size: 0.8rem;
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      background: var(--panel);
    }
    .dot { width: 0.5rem; height: 0.5rem; border-radius: 50%; background: var(--ok); }
    .dot.dead { background: var(--error); }
    main {
      padding: 0.8rem;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 0.8rem;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      box-shadow: 0 2px 10px var(--shadow);
      padding: 0.75rem;
      min-height: 150px;
    }
    section h2 {
      margin: 0 0 0.6rem;
      font-size: 0.95rem;
      color: var(--accent);
    }
    .stack { display: grid; gap: 0.4rem; }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.8rem;
      white-space: pre-wrap;
      word-break: break-word;
      background: rgba(127, 127, 127, 0.08);
      padding: 0.5rem;
      border-radius: 8px;
      border: 1px solid var(--border);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.8rem;
    }
    th, td {
      border-bottom: 1px solid var(--border);
      padding: 0.35rem;
      text-align: left;
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 600; }
    #logs {
      max-height: 320px;
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.5rem;
      background: rgba(127, 127, 127, 0.06);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.78rem;
      line-height: 1.35;
    }
    .log-line { margin: 0 0 0.2rem; white-space: pre-wrap; word-break: break-word; }
    .lvl-error { color: var(--error); }
    .lvl-warning { color: var(--warn); }
    .lvl-info { color: var(--fg); }
    .lvl-debug { color: var(--debug); }
    .muted { color: var(--muted); font-size: 0.78rem; }
    .wide { grid-column: span 2; }
    @media (max-width: 860px) {
      main { grid-template-columns: 1fr; }
      .wide { grid-column: span 1; }
    }
  </style>
</head>
<body>
  <header>
    <h1>HotspotTriage Dashboard</h1>
    <div class="toolbar">
      <span id="healthBadge" class="badge"><span id="healthDot" class="dot"></span><span id="healthText">Alive</span></span>
      <button id="themeToggle" type="button">Toggle Theme</button>
    </div>
  </header>

  <main>
    <section>
      <h2>Config Overview</h2>
      <div id="configPanel" class="stack">
        <div class="muted">Loading config…</div>
      </div>
    </section>

    <section>
      <h2>Tool Call Statistics</h2>
      <div class="toolbar" style="margin-bottom: 0.5rem;">
        <button id="clearStatsBtn" type="button">Clear Stats</button>
        <span class="muted">Refreshes every 5s</span>
      </div>
      <div id="statsPanel" class="muted">No tool activity yet.</div>
    </section>

    <section class="wide">
      <h2>Log Viewer</h2>
      <div class="toolbar" style="margin-bottom: 0.5rem;">
        <button id="clearLogsBtn" type="button">Clear Logs</button>
        <button id="pauseLogsBtn" type="button">Pause Scroll: Off</button>
        <span class="muted">Live via SSE</span>
      </div>
      <div id="logs"></div>
    </section>
  </main>

  <script>
    const state = {
      lastLogIdx: 0,
      pauseScroll: false,
      healthFailures: 0,
    };

    function $(id) { return document.getElementById(id); }

    function pretty(v) {
      if (v === null || v === undefined) return "n/a";
      if (typeof v === "object") return JSON.stringify(v, null, 2);
      return String(v);
    }

    function setTheme(dark) {
      document.body.classList.toggle("dark", dark);
      localStorage.setItem("ht-dashboard-theme", dark ? "dark" : "light");
    }

    async function loadConfig() {
      const panel = $("configPanel");
      try {
        const res = await fetch("/api/config");
        if (!res.ok) throw new Error("config request failed");
        const cfg = await res.json();
        const project = cfg.project || {};
        const dashboard = cfg.dashboard || {};
        panel.innerHTML = "";
        const items = [
          ["Project Path", project.path],
          ["Granularity", cfg.granularity],
          ["Score Metrics", cfg.score_metrics || []],
          ["Score Weights", cfg.score_aggregation || {}],
          ["Normalization Thresholds", cfg.metric_normalization || {}],
          ["Decay Half-life", cfg.decay_half_life],
          ["Similarity Enabled", cfg.similarity_enabled],
          ["Dashboard", dashboard],
          ["Version", cfg.version],
        ];
        for (const [k, v] of items) {
          const wrap = document.createElement("div");
          wrap.innerHTML = `<strong>${k}</strong><div class="mono">${pretty(v)}</div>`;
          panel.appendChild(wrap);
        }
      } catch (err) {
        panel.innerHTML = `<div class="muted">Failed to load config: ${String(err)}</div>`;
      }
    }

    function renderStats(data) {
      const panel = $("statsPanel");
      const tools = Object.keys(data || {});
      if (tools.length === 0) {
        panel.innerHTML = '<div class="muted">No tool activity yet.</div>';
        return;
      }
      const rows = tools.sort().map((tool) => {
        const s = data[tool] || {};
        return `<tr>
          <td>${tool}</td>
          <td>${s.num_calls ?? 0}</td>
          <td>${s.num_errors ?? 0}</td>
          <td>${s.avg_duration_ms ?? 0}</td>
          <td>${s.last_called_at ?? "n/a"}</td>
        </tr>`;
      }).join("");
      panel.innerHTML = `<table>
        <thead><tr><th>Tool</th><th>Calls</th><th>Errors</th><th>Avg ms</th><th>Last called</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
    }

    async function refreshStats() {
      try {
        const res = await fetch("/api/stats");
        if (!res.ok) throw new Error("stats request failed");
        renderStats(await res.json());
      } catch (err) {
        $("statsPanel").innerHTML = `<div class="muted">Failed to load stats: ${String(err)}</div>`;
      }
    }

    function levelClass(msg) {
      const m = String(msg || "");
      if (m.includes("[ERROR]")) return "lvl-error";
      if (m.includes("[WARNING]")) return "lvl-warning";
      if (m.includes("[DEBUG]")) return "lvl-debug";
      return "lvl-info";
    }

    function appendLogs(messages) {
      const box = $("logs");
      for (const msg of messages) {
        const line = document.createElement("div");
        line.className = `log-line ${levelClass(msg)}`;
        line.textContent = msg;
        box.appendChild(line);
      }
      if (!state.pauseScroll) box.scrollTop = box.scrollHeight;
    }

    function connectLogStream() {
      const es = new EventSource("/api/logs/stream");
      es.onmessage = (ev) => {
        try {
          const message = JSON.parse(ev.data);
          appendLogs([message]);
          state.lastLogIdx += 1;
        } catch (_) {
          appendLogs([ev.data]);
          state.lastLogIdx += 1;
        }
      };
      es.onerror = () => {
        es.close();
        setTimeout(connectLogStream, 1500);
      };
    }

    async function refreshHealth() {
      try {
        const res = await fetch("/api/health");
        if (!res.ok) throw new Error("health request failed");
        const data = await res.json();
        state.healthFailures = 0;
        $("healthDot").classList.remove("dead");
        $("healthText").textContent = `Alive · ${data.uptime_s ?? "?"}s`;
      } catch (_) {
        state.healthFailures += 1;
        if (state.healthFailures >= 3) {
          $("healthDot").classList.add("dead");
          $("healthText").textContent = "Unavailable";
        }
      }
    }

    async function clearStats() {
      await fetch("/api/stats/clear", { method: "POST" });
      await refreshStats();
    }

    function clearLogs() {
      $("logs").innerHTML = "";
      state.lastLogIdx = 0;
    }

    function initEvents() {
      $("themeToggle").addEventListener("click", () => {
        setTheme(!document.body.classList.contains("dark"));
      });
      $("clearStatsBtn").addEventListener("click", clearStats);
      $("clearLogsBtn").addEventListener("click", clearLogs);
      $("pauseLogsBtn").addEventListener("click", () => {
        state.pauseScroll = !state.pauseScroll;
        $("pauseLogsBtn").textContent = `Pause Scroll: ${state.pauseScroll ? "On" : "Off"}`;
      });
    }

    async function init() {
      const saved = localStorage.getItem("ht-dashboard-theme");
      setTheme(saved === "dark");
      initEvents();
      await loadConfig();
      await refreshStats();
      await refreshHealth();
      connectLogStream();
      setInterval(refreshStats, 5000);
      setInterval(refreshHealth, 10000);
    }

    init();
  </script>
</body>
</html>
"""
