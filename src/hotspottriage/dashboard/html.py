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
    input {
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      color: var(--fg);
      padding: 0.35rem 0.5rem;
      min-width: 140px;
    }
    .status-box {
      margin-top: 0.5rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.45rem;
      font-size: 0.78rem;
      min-height: 2.2rem;
      background: rgba(127, 127, 127, 0.06);
    }
    .progress-wrap {
      margin-top: 0.45rem;
      width: 100%;
      height: 10px;
      border: 1px solid var(--border);
      border-radius: 999px;
      overflow: hidden;
      background: rgba(127, 127, 127, 0.12);
    }
    .progress-bar {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent), #14b8a6);
      transition: width 0.25s ease;
    }
    .progress-bar.done { background: linear-gradient(90deg, var(--ok), #22c55e); }
    .progress-bar.err { background: linear-gradient(90deg, var(--error), #ef4444); }
    .wide { grid-column: span 2; }
    .heatmap-wrap { overflow-x: auto; }
    .heatmap-toolbar { display: flex; gap: 0.4rem; margin-bottom: 0.5rem; }
    .heatmap-table th[data-sort-key] { cursor: pointer; }
    .heatmap-table .heatmap-name { min-width: 280px; }
    .heatmap-label { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
    .heatmap-indent-1 { padding-left: 1.2rem; }
    .heatmap-indent-2 { padding-left: 2.2rem; }
    .heatmap-toggle, .heatmap-toggle-placeholder {
      width: 1.2rem;
      margin-right: 0.2rem;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 0;
      background: transparent;
      color: var(--fg);
    }
    .heatmap-toggle { cursor: pointer; }
    .heatmap-hidden { display: none; }
    .heatmap-score-bar {
      position: relative;
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      min-width: 76px;
      text-align: center;
      font-variant-numeric: tabular-nums;
    }
    .heatmap-score-fill {
      position: absolute;
      inset: 0 auto 0 0;
      opacity: 0.5;
    }
    .heatmap-score-bar span:last-child {
      position: relative;
      z-index: 1;
    }
    .heatmap-drawer {
      margin-top: 0.7rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.5rem;
      background: rgba(127, 127, 127, 0.06);
    }
    .heatmap-drawer h3 { margin: 0 0 0.4rem; font-size: 0.88rem; color: var(--accent); }
    .heatmap-drawer-body { margin: 0; white-space: pre-wrap; font-size: 0.75rem; }
    .heatmap-empty { color: var(--muted); }
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

      <h2 style="margin-top: 0.9rem;">Cache Actions</h2>
      <div class="toolbar" style="flex-wrap: wrap;">
        <input id="cacheTargetInput" type="text" placeholder="../LexVox" />
        <input id="cacheFilterInput" type="text" placeholder="filter (optional)" />
        <input id="cacheScoreInput" type="text" placeholder="score metrics (optional)" value="" />
        <button id="checkCacheBtn" type="button">Check Cache</button>
        <button id="rebuildHeatmapBtn" type="button">Rebuild Heatmap</button>
        <button id="generateCacheBtn" type="button">Generate Cache</button>
      </div>
      <div id="cacheContextPanel" class="mono" style="margin-top: 0.45rem;">
Path: n/a
Cache Status: unknown
Build Parameters: filter=<none>, score_metrics=<default>
      </div>
      <div id="cacheStatus" class="status-box muted">Idle</div>
      <div class="progress-wrap"><div id="cacheProgress" class="progress-bar"></div></div>
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

    <section class="wide">
      <h2>Heatmap</h2>
      <div id="heatmapContainer" class="heatmap-wrap muted">Loading heatmap…</div>
    </section>
  </main>

  <script>
    const state = {
      lastLogIdx: 0,
      pauseScroll: false,
      healthFailures: 0,
      activeCacheJobId: null,
    };

    function $(id) { return document.getElementById(id); }

    function updateCacheContext(statusText) {
      const target = $("cacheTargetInput").value.trim() || "n/a";
      const filter = $("cacheFilterInput").value.trim() || "<none>";
      const score = $("cacheScoreInput").value.trim() || "<default>";
      $("cacheContextPanel").textContent =
`Path: ${target}
Cache Status: ${statusText}
Build Parameters: filter=${filter}, score_metrics=${score}`;
    }

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
        if (dashboard.default_target && !$("cacheTargetInput").value.trim()) {
          $("cacheTargetInput").value = String(dashboard.default_target);
        }
        updateCacheContext("unknown");
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

    async function loadCacheContext() {
      try {
        const res = await fetch("/api/cache/context");
        if (!res.ok) return;
        const ctx = await res.json();
        if (!$("cacheTargetInput").value.trim() && ctx.last_target) {
          $("cacheTargetInput").value = String(ctx.last_target);
        }
        if (!$("cacheFilterInput").value.trim() && ctx.last_filter) {
          $("cacheFilterInput").value = String(ctx.last_filter);
        }
        if (ctx.last_score_metrics) {
          $("cacheScoreInput").value = String(ctx.last_score_metrics);
        }
        updateCacheContext(ctx.last_target ? "restored" : "unknown");
      } catch (_) {
        // no-op: context restore is best-effort
      }
    }

    async function saveCacheContext() {
      const payload = {
        target: $("cacheTargetInput").value.trim(),
        filter: $("cacheFilterInput").value.trim(),
        score_metrics: $("cacheScoreInput").value.trim(),
      };
      try {
        await fetch("/api/cache/context", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } catch (_) {
        // no-op
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

    async function generateCache() {
      const target = $("cacheTargetInput").value.trim();
      const filter = $("cacheFilterInput").value.trim();
      const score = $("cacheScoreInput").value.trim();
      const box = $("cacheStatus");
      const bar = $("cacheProgress");
      if (!target) {
        box.textContent = "Target path is required.";
        updateCacheContext("invalid target");
        bar.classList.remove("done");
        bar.classList.add("err");
        bar.style.width = "100%";
        return;
      }
      box.textContent = "Starting cache generation…";
      bar.classList.remove("done", "err");
      bar.style.width = "8%";
      try {
        const startRes = await fetch("/api/cache/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target,
            filter: filter || null,
            score_metrics: score || null
          }),
        });
        const started = await startRes.json();
        if (!startRes.ok) {
          const msg = started?.detail || started?.error || "cache generation failed";
          box.textContent = `Error: ${msg}`;
          updateCacheContext(`error (${msg})`);
          bar.classList.remove("done");
          bar.classList.add("err");
          bar.style.width = "100%";
          return;
        }
        if (started.target) {
          $("cacheTargetInput").value = String(started.target);
        }
        state.activeCacheJobId = started.job_id;
        updateCacheContext(`running (job ${state.activeCacheJobId.slice(0, 8)})`);
        await pollCacheJob(state.activeCacheJobId);
      } catch (err) {
        box.textContent = `Error: ${String(err)}`;
        updateCacheContext(`error (${String(err)})`);
        bar.classList.remove("done");
        bar.classList.add("err");
        bar.style.width = "100%";
      }
    }

    async function checkCacheStatus() {
      const target = $("cacheTargetInput").value.trim();
      const box = $("cacheStatus");
      const bar = $("cacheProgress");
      if (!target) {
        box.textContent = "Target path is required.";
        updateCacheContext("invalid target");
        bar.classList.remove("done");
        bar.classList.add("err");
        bar.style.width = "100%";
        return;
      }
      box.textContent = "Checking cache…";
      bar.classList.remove("done", "err");
      bar.style.width = "25%";
      try {
        const res = await fetch("/api/cache/status", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target,
            filter: $("cacheFilterInput").value.trim() || null,
            score_metrics: $("cacheScoreInput").value.trim() || null
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          const msg = data?.detail || data?.error || "cache status failed";
          box.textContent = `Error: ${msg}`;
          updateCacheContext(`error (${msg})`);
          bar.classList.remove("done");
          bar.classList.add("err");
          bar.style.width = "100%";
          return;
        }
        if (data.target) {
          $("cacheTargetInput").value = String(data.target);
        }
        if (!data.exists) {
          box.textContent = `No cache yet at ${data.cache_dir}`;
          updateCacheContext(`missing (${data.cache_dir})`);
          bar.classList.remove("done");
          bar.classList.add("err");
          bar.style.width = "100%";
          return;
        }
        box.textContent = `Cache exists: entries=${data.entries}, size=${data.size_bytes} bytes, dir=${data.cache_dir}`;
        updateCacheContext(`ready (entries=${data.entries}, size=${data.size_bytes})`);
        bar.classList.remove("err");
        bar.classList.add("done");
        bar.style.width = "100%";
      } catch (err) {
        box.textContent = `Error: ${String(err)}`;
        updateCacheContext(`error (${String(err)})`);
        bar.classList.remove("done");
        bar.classList.add("err");
        bar.style.width = "100%";
      }
    }

    async function rebuildHeatmap() {
      const target = $("cacheTargetInput").value.trim();
      const box = $("cacheStatus");
      const bar = $("cacheProgress");
      if (!target) {
        box.textContent = "Target path is required.";
        updateCacheContext("invalid target");
        bar.classList.remove("done");
        bar.classList.add("err");
        bar.style.width = "100%";
        return;
      }
      box.textContent = "Rebuilding heatmap from cache…";
      bar.classList.remove("done", "err");
      bar.style.width = "40%";
      try {
        const res = await fetch("/api/heatmap/rebuild", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target,
            filter: $("cacheFilterInput").value.trim() || null,
            score_metrics: $("cacheScoreInput").value.trim() || null
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          const msg = data?.detail || data?.error || "heatmap rebuild failed";
          box.textContent = `Error: ${msg}`;
          updateCacheContext(`error (${msg})`);
          bar.classList.remove("done");
          bar.classList.add("err");
          bar.style.width = "100%";
          return;
        }
        if (data.target) {
          $("cacheTargetInput").value = String(data.target);
        }
        if (!data.exists) {
          const msg = data.heatmap_error || "cache file not found";
          box.textContent = `Cannot rebuild heatmap: ${msg}`;
          updateCacheContext(`missing (${msg})`);
          bar.classList.remove("done");
          bar.classList.add("err");
          bar.style.width = "100%";
          return;
        }
        if (!data.heatmap_updated) {
          const msg = data.heatmap_error || "unknown error";
          box.textContent = `Heatmap rebuild failed: ${msg}`;
          updateCacheContext(`error (${msg})`);
          bar.classList.remove("done");
          bar.classList.add("err");
          bar.style.width = "100%";
          return;
        }
        await loadHeatmapFragment();
        box.textContent = `Heatmap rebuilt from cache (${data.heatmap_rows ?? "?"} rows).`;
        updateCacheContext("heatmap rebuilt");
        bar.classList.remove("err");
        bar.classList.add("done");
        bar.style.width = "100%";
      } catch (err) {
        box.textContent = `Error: ${String(err)}`;
        updateCacheContext(`error (${String(err)})`);
        bar.classList.remove("done");
        bar.classList.add("err");
        bar.style.width = "100%";
      }
    }

    async function pollCacheJob(jobId) {
      const box = $("cacheStatus");
      const bar = $("cacheProgress");
      while (true) {
        const res = await fetch(`/api/cache/jobs/${jobId}`);
        const data = await res.json();
        if (!res.ok) {
          const msg = data?.detail || data?.error || "cache job status failed";
          box.textContent = `Error: ${msg}`;
          updateCacheContext(`error (${msg})`);
          bar.classList.remove("done");
          bar.classList.add("err");
          bar.style.width = "100%";
          return;
        }
        const p = Math.max(0, Math.min(100, Number(data.progress || 0)));
        bar.style.width = `${p}%`;
        box.textContent = data.message || "Running cache job...";
        if (data.status === "running") {
          await new Promise((r) => setTimeout(r, 900));
          continue;
        }
        if (data.status === "error") {
          box.textContent = `Error: ${data.error || "cache generation failed"}`;
          updateCacheContext(`error (${data.error || "cache generation failed"})`);
          bar.classList.remove("done");
          bar.classList.add("err");
          bar.style.width = "100%";
          return;
        }
        const result = data.result || {};
        const meta = result.metadata || {};
        const entries = result.cache_status?.entries ?? 0;
        const blockErr = result.blocks?.error;
        if (blockErr) {
          box.textContent = `Completed with warning: ${blockErr}`;
          updateCacheContext(`warning (${blockErr})`);
          bar.classList.remove("done");
          bar.classList.add("err");
          bar.style.width = "100%";
          return;
        }
        box.textContent =
          `Done: blocks=${meta.blocks_cached ?? 0}, classes=${meta.classes_indexed ?? 0}, cache entries=${entries}`;
        updateCacheContext(`ready (entries=${entries})`);
        bar.classList.remove("err");
        bar.classList.add("done");
        bar.style.width = "100%";
        await loadHeatmapFragment();
        return;
      }
    }

    function thresholdForFilter(filterName) {
      if (filterName === "critical") return 0.8;
      if (filterName === "high") return 0.6;
      return 0.0;
    }

    function applyHeatmapVisibility(root, filterName) {
      const threshold = thresholdForFilter(filterName);
      const rows = Array.from(root.querySelectorAll("tbody tr.heatmap-row"));
      const map = new Map(rows.map((row) => [row.dataset.rowId, row]));
      for (const row of rows) {
        const score = Number(row.dataset.score || 0);
        const selfVisible = score >= threshold;
        let ancestorVisible = true;
        let parent = row.dataset.parent;
        while (parent) {
          const parentRow = map.get(parent);
          if (!parentRow || parentRow.dataset.expanded !== "true" || parentRow.dataset.filteredOut === "true") {
            ancestorVisible = false;
            break;
          }
          parent = parentRow.dataset.parent || "";
        }
        row.dataset.filteredOut = selfVisible ? "false" : "true";
        row.classList.toggle("heatmap-hidden", !(selfVisible && ancestorVisible));
      }
    }

    function toggleHeatmapRow(root, rowId) {
      const row = root.querySelector(`tr[data-row-id="${rowId}"]`);
      if (!row) return;
      const nextExpanded = row.dataset.expanded !== "true";
      row.dataset.expanded = nextExpanded ? "true" : "false";
      const toggle = row.querySelector(".heatmap-toggle");
      if (toggle) toggle.textContent = nextExpanded ? "v" : ">";
      const filterName = root.dataset.filter || "all";
      applyHeatmapVisibility(root, filterName);
    }

    function compareRowsByKey(a, b, key) {
      if (key === "name") {
        const an = (a.querySelector(".heatmap-label")?.textContent || "").toLowerCase();
        const bn = (b.querySelector(".heatmap-label")?.textContent || "").toLowerCase();
        return an.localeCompare(bn);
      }
      const av = Number(a.dataset[key] || 0);
      const bv = Number(b.dataset[key] || 0);
      return bv - av;
    }

    function reorderHeatmapRows(root, key) {
      const body = root.querySelector("tbody");
      if (!body) return;
      const rows = Array.from(body.querySelectorAll("tr.heatmap-row"));
      const byParent = new Map();
      for (const row of rows) {
        const parent = row.dataset.parent || "__root__";
        if (!byParent.has(parent)) byParent.set(parent, []);
        byParent.get(parent).push(row);
      }
      for (const group of byParent.values()) {
        group.sort((a, b) => compareRowsByKey(a, b, key));
      }
      const ordered = [];
      const appendGroup = (parentId) => {
        const group = byParent.get(parentId) || [];
        for (const row of group) {
          ordered.push(row);
          appendGroup(row.dataset.rowId || "");
        }
      };
      appendGroup("__root__");
      for (const row of ordered) body.appendChild(row);
      applyHeatmapVisibility(root, root.dataset.filter || "all");
    }

    function showHeatmapDetail(root, row) {
      const drawer = root.querySelector(".heatmap-drawer");
      const body = root.querySelector(".heatmap-drawer-body");
      if (!drawer || !body) return;
      const detail = row.dataset.detail ? JSON.parse(row.dataset.detail) : {
        path: row.querySelector(".heatmap-label")?.textContent || "",
        score: Number(row.dataset.score || 0),
        score_band: row.dataset.scoreBand || "n/a",
      };
      body.textContent = JSON.stringify(detail, null, 2);
      drawer.hidden = false;
    }

    function initHeatmapInteractions() {
      const root = $("heatmapContainer").querySelector(".heatmap");
      if (!root) return;
      root.dataset.filter = root.dataset.filter || "all";
      root.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;
        const filterBtn = target.closest(".heatmap-filter");
        if (filterBtn) {
          const filter = filterBtn.dataset.filter || "all";
          root.dataset.filter = filter;
          root.querySelectorAll(".heatmap-filter").forEach((button) => {
            button.classList.toggle("is-active", button === filterBtn);
          });
          applyHeatmapVisibility(root, filter);
          return;
        }
        const header = target.closest("th[data-sort-key]");
        if (header) {
          reorderHeatmapRows(root, header.dataset.sortKey || "score");
          return;
        }
        const toggleBtn = target.closest(".heatmap-toggle");
        if (toggleBtn) {
          const row = toggleBtn.closest("tr.heatmap-row");
          if (row?.dataset.rowId) {
            toggleHeatmapRow(root, row.dataset.rowId);
          }
          return;
        }
        const row = target.closest("tr.heatmap-row");
        if (row) {
          showHeatmapDetail(root, row);
        }
      });
      applyHeatmapVisibility(root, "all");
    }

    async function loadHeatmapFragment() {
      const container = $("heatmapContainer");
      try {
        const res = await fetch(`/api/heatmap/fragment?ts=${Date.now()}`, { cache: "no-store" });
        if (!res.ok) throw new Error("heatmap request failed");
        container.innerHTML = await res.text();
        initHeatmapInteractions();
      } catch (err) {
        container.innerHTML = `<div class="heatmap-empty">Failed to load heatmap: ${String(err)}</div>`;
      }
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
      $("checkCacheBtn").addEventListener("click", checkCacheStatus);
      $("rebuildHeatmapBtn").addEventListener("click", rebuildHeatmap);
      $("generateCacheBtn").addEventListener("click", generateCache);
      ["cacheTargetInput", "cacheFilterInput", "cacheScoreInput"].forEach((id) => {
        $(id).addEventListener("input", () => {
          updateCacheContext("pending");
          saveCacheContext();
        });
      });
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
      await loadCacheContext();
      await refreshStats();
      await refreshHealth();
      await loadHeatmapFragment();
      connectLogStream();
      setInterval(refreshStats, 5000);
      setInterval(refreshHealth, 10000);
    }

    init();
  </script>
</body>
</html>
"""
