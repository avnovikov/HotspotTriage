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
      --heatmap-high: #ea580c;
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
      --heatmap-high: #fb923c;
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
      gap: 0.75rem;
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      background: var(--bg);
      z-index: 5;
      flex-wrap: wrap;
    }
    .header-left {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
    }
    h1 { font-size: 1rem; margin: 0; letter-spacing: 0.02em; }
    .top-nav {
      display: flex;
      align-items: center;
      gap: 0.25rem;
    }
    .nav-tab {
      text-decoration: none;
      color: var(--muted);
      padding: 0.3rem 0.5rem;
      border-radius: 8px;
      border: 1px solid transparent;
      font-size: 0.82rem;
    }
    .nav-tab:hover { color: var(--fg); border-color: var(--border); }
    .nav-tab.active {
      color: var(--accent);
      border-color: var(--accent);
      background: rgba(15, 118, 110, 0.07);
    }
    body.dark .nav-tab.active { background: rgba(45, 212, 191, 0.1); }
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
      max-width: 1100px;
      margin: 0 auto;
    }
    .view-section { display: none; }
    .view-section.active { display: block; }
    .section-grid {
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
    .cfg-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-bottom: 0.55rem; }
    details.norm-metric-card {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.45rem;
      background: rgba(127, 127, 127, 0.04);
    }
    details.norm-metric-card summary { cursor: pointer; font-weight: 600; color: var(--accent); }
    .norm-svg-wrap { position: relative; margin-top: 0.35rem; }
    .norm-svg-wrap svg { display: block; }
    #view-config .norm-svg-wrap {
      width: 50%;
      max-width: 100%;
      min-width: 200px;
    }
    #view-config .norm-svg-wrap svg[data-role="chart"] {
      width: 100%;
      height: auto;
      display: block;
    }
    .norm-tooltip {
      position: absolute;
      pointer-events: none;
      background: var(--panel);
      border: 1px solid var(--border);
      padding: 0.2rem 0.35rem;
      font-size: 0.72rem;
      border-radius: 4px;
      display: none;
      z-index: 10;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    .norm-controls {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      align-items: center;
      margin-top: 0.35rem;
      font-size: 0.78rem;
    }
    .norm-controls input.norm-num-in { min-width: 72px; width: 88px; }
    .dist-placeholder { color: var(--muted); font-size: 0.78rem; padding: 0.25rem 0; }
    .weight-group {
      margin-bottom: 0.55rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.45rem;
      background: rgba(127, 127, 127, 0.03);
    }
    .weight-group h3 { margin: 0 0 0.35rem; font-size: 0.82rem; color: var(--muted); }
    .weight-row {
      display: grid;
      grid-template-columns: 1fr minmax(100px, 140px) 74px;
      gap: 0.35rem;
      align-items: center;
      margin-bottom: 0.28rem;
    }
    .weight-sum-badge {
      font-size: 0.78rem;
      padding: 0.15rem 0.45rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      width: fit-content;
      margin-top: 0.15rem;
    }
    .weight-sum-badge.ok { border-color: var(--ok); color: var(--ok); }
    .weight-sum-badge.bad { border-color: var(--error); color: var(--error); }
    .heatmap-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-bottom: 0.55rem; }
    .heatmap-controls label { font-size: 0.78rem; color: var(--muted); display: inline-flex; align-items: center; gap: 0.3rem; }
    .heatmap-controls select { min-width: 140px; }
    .heatmap-list { display: flex; flex-direction: column; gap: 0.45rem; font-size: 0.78rem; }
    .heatmap-item { border-bottom: 1px solid var(--border); padding-bottom: 0.35rem; }
    .heatmap-item:last-child { border-bottom: none; }
    .heatmap-item-head {
      display: flex;
      justify-content: space-between;
      gap: 0.5rem;
      align-items: baseline;
      margin-bottom: 0.2rem;
    }
    #heatmapPanel table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 0.74rem;
    }
    #heatmapPanel th,
    #heatmapPanel td {
      border: 1px solid var(--border);
      padding: 0.22rem 0.38rem;
      vertical-align: middle;
    }
    #heatmapPanel thead th {
      text-align: left;
      background: rgba(127, 127, 127, 0.06);
      font-weight: 600;
      font-size: 0.7rem;
      color: var(--muted);
    }
    .heatmap-file-col,
    .heatmap-method-col {
      width: 180px;
      max-width: 180px;
      min-width: 0;
      box-sizing: border-box;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.74rem;
    }
    .heatmap-method-col .heatmap-method {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 100%;
    }
    .heatmap-metric-th {
      text-align: right;
      font-variant-numeric: tabular-nums;
      font-size: 0.66rem;
      line-height: 1.12;
      max-width: 5.25rem;
      min-width: 2.75rem;
      white-space: normal;
      word-spacing: 0;
      hyphens: manual;
    }
    .heatmap-metric-cell {
      font-variant-numeric: tabular-nums;
      text-align: right;
      color: var(--fg);
    }
    .heatmap-val { font-variant-numeric: tabular-nums; color: var(--muted); flex-shrink: 0; }
    .heatmap-bar-track {
      height: 8px;
      border-radius: 4px;
      background: rgba(127, 127, 127, 0.12);
      overflow: hidden;
    }
    .heatmap-bar-fill {
      height: 100%;
      border-radius: 4px;
      min-width: 2px;
      background: var(--accent);
      opacity: 0.85;
    }
    .heatmap-bar-fill.band-low { background: var(--ok); }
    .heatmap-bar-fill.band-medium { background: var(--warn); }
    .heatmap-bar-fill.band-high { background: var(--heatmap-high); }
    .heatmap-bar-fill.band-critical { background: var(--error); }
    @media (max-width: 860px) {
      .section-grid { grid-template-columns: 1fr; }
      .wide { grid-column: span 1; }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-left">
      <h1>HotspotTriage Dashboard</h1>
      <nav id="topNav" class="top-nav" aria-label="Primary">
        <a id="navOverview" class="nav-tab" href="#overview" data-route="overview">Overview</a>
        <a id="navHeatmap" class="nav-tab" href="#heatmap" data-route="heatmap">Heatmap</a>
        <a id="navConfig" class="nav-tab" href="#config" data-route="config">Config</a>
      </nav>
    </div>
    <div class="toolbar">
      <span id="healthBadge" class="badge"><span id="healthDot" class="dot"></span><span id="healthText">Alive</span></span>
      <button id="themeToggle" type="button">Toggle Theme</button>
    </div>
  </header>

  <main>
    <div id="view-overview" class="view-section active" data-view="overview">
      <div class="section-grid">
        <section class="wide">
          <h2>Summary</h2>
          <div id="overviewSummaryPanel" class="stack muted" style="font-size:0.82rem;">Loading…</div>
        </section>
        <section class="wide">
          <h2>Cache Actions</h2>
          <div class="toolbar" style="flex-wrap: wrap;">
            <input id="cacheTargetInput" type="text" placeholder="../LexVox" />
            <input id="cacheFilterInput" type="text" placeholder="filter (optional)" />
            <input id="cacheScoreInput" type="text" placeholder="score metrics" value="churn_per_sloc,cyclomatic" />
            <button id="checkCacheBtn" type="button">Check Cache</button>
            <button id="generateCacheBtn" type="button">Generate Cache</button>
          </div>
          <div id="cacheContextPanel" class="mono" style="margin-top: 0.45rem;">
Path: n/a
Cache Status: unknown
Build Parameters: filter=<none>, score_metrics=churn_per_sloc,cyclomatic
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
      </div>
    </div>

    <div id="view-heatmap" class="view-section" data-view="heatmap">
      <section class="wide">
        <h2>Heatmap</h2>
        <div class="heatmap-controls">
          <button id="heatmapUpdateBtn" type="button">Update Heatmap</button>
          <label>Limit
            <input id="heatmapLimitInput" type="number" min="1" max="500" value="500" style="width:5rem;min-width:0;" />
          </label>
          <span id="heatmapStatus" class="muted" style="font-size:0.78rem;"></span>
        </div>
        <div class="toolbar" style="margin-bottom:0.45rem;flex-wrap:wrap;">
          <input id="heatmapTargetInput" type="text" placeholder="../LexVox" />
          <input id="heatmapFilterInput" type="text" placeholder="filter (optional)" />
          <input id="heatmapScoreInput" type="text" placeholder="score metrics" value="churn_per_sloc,cyclomatic" />
        </div>
        <div id="heatmapPanel" class="muted">No heatmap rows yet.</div>
      </section>
    </div>

    <div id="view-config" class="view-section" data-view="config">
      <section class="wide">
        <h2>Configuration Editors</h2>
        <div class="cfg-toolbar">
          <button id="configRefreshDataBtn" type="button">Refresh data</button>
          <button id="configSaveBtn" type="button">Save config</button>
          <span id="configSaveStatus" class="muted"></span>
        </div>
        <div id="configPanel" class="stack">
          <div class="muted">Loading config…</div>
        </div>
        <div id="scoreWeightsPanel" class="stack" style="margin-top:0.55rem;"></div>
        <div id="configMetaPanel" class="stack muted" style="margin-top:0.55rem;font-size:0.78rem;"></div>
        <h2 style="margin-top: 0.9rem;">Tool Call Statistics</h2>
        <div class="toolbar" style="margin-bottom: 0.5rem;">
          <button id="clearStatsBtn" type="button">Clear Stats</button>
          <span class="muted">Refreshes every 5s</span>
        </div>
        <div id="statsPanel" class="muted">No tool activity yet.</div>
      </section>
    </div>
  </main>

  <script>
    const state = {
      lastLogIdx: 0,
      pauseScroll: false,
      healthFailures: 0,
      activeCacheJobId: null,
      editorMN: null,
      editorSA: null,
      baselineMN: null,
      baselineSA: null,
      distributionCache: {},
      selectedBpIndex: {},
      normDrag: null,
    };

    const WEIGHT_GROUPS = ["complexity_weights", "churn_weights", "smell_weights", "similarity_weights"];

    function clone(o) {
      return JSON.parse(JSON.stringify(o));
    }

    function knotsDisplay(method, bps) {
      const pts = (bps || []).map((p) => ({
        x: Number(p[0]),
        y: method === "inverse_piecewise" ? 1 - Number(p[1]) : Number(p[1]),
      }));
      pts.sort((a, b) => a.x - b.x);
      return pts;
    }

    function evalPiecewiseDisplay(x, method, bps) {
      const knots = knotsDisplay(method, bps);
      const xv = Number(x);
      if (!knots.length) return 0;
      if (xv <= knots[0].x) return knots[0].y;
      const last = knots[knots.length - 1];
      if (xv >= last.x) return last.y;
      for (let i = 0; i < knots.length - 1; i++) {
        const a = knots[i];
        const b = knots[i + 1];
        if (xv >= a.x && xv <= b.x) {
          if (b.x === a.x) return a.y;
          const t = (xv - a.x) / (b.x - a.x);
          return a.y + t * (b.y - a.y);
        }
      }
      return last.y;
    }

    function sortBreakpointPairs(bps) {
      return bps
        .map((p) => [Number(p[0]), Number(p[1])])
        .sort((a, b) => a[0] - b[0]);
    }

    function ensureMetricCard(metric) {
      return document.querySelector(`details.norm-metric-card[data-metric="${metric}"]`);
    }

    function normChartTabWidth() {
      const tab = document.getElementById("view-config");
      if (!tab) return 880;
      let w = tab.getBoundingClientRect().width || tab.clientWidth;
      if (w < 16) {
        const main = document.querySelector("main");
        w = main ? main.getBoundingClientRect().width || main.clientWidth : window.innerWidth - 32;
        if (!Number.isFinite(w) || w < 16) w = 880;
      }
      return w;
    }

    function normChartDimensions() {
      const tabW = normChartTabWidth();
      const W = Math.max(220, Math.floor(tabW * 0.5));
      const H = 120;
      return { W, H };
    }

    function normChartPointer(svg, ev, W, H) {
      const r = svg.getBoundingClientRect();
      const rw = Math.max(r.width, 1);
      const rh = Math.max(r.height, 1);
      return {
        x: ((ev.clientX - r.left) / rw) * W,
        y: ((ev.clientY - r.top) / rh) * H,
      };
    }

    function redrawAllNormMetrics() {
      if (!state.editorMN) return;
      Object.keys(state.editorMN).forEach((m) => redrawNormMetric(m));
    }

    function redrawNormMetric(metric) {
      const card = ensureMetricCard(metric);
      if (!card) return;
      const svg = card.querySelector('svg[data-role="chart"]');
      const tip = card.querySelector(".norm-tooltip");
      const msgEl = card.querySelector('[data-role="dist-msg"]');
      const mc = state.editorMN[metric];
      const method = mc.method;
      const bps = mc.breakpoints || [];
      const dist = state.distributionCache[metric];
      const { W, H } = normChartDimensions();
      const pad = { l: 30, r: 12, t: 12, b: 24 };
      const iw = W - pad.l - pad.r;
      const ih = H - pad.t - pad.b;
      let xMin = Infinity;
      let xMax = -Infinity;
      bps.forEach(([rx]) => {
        const x = Number(rx);
        if (Number.isFinite(x)) {
          xMin = Math.min(xMin, x);
          xMax = Math.max(xMax, x);
        }
      });
      const hasDist =
        dist &&
        Array.isArray(dist.counts) &&
        dist.counts.length &&
        dist.counts.some((c) => Number(c) > 0);
      if (hasDist && dist.buckets) {
        dist.buckets.forEach(([lo, hi]) => {
          xMin = Math.min(xMin, Number(lo));
          xMax = Math.max(xMax, Number(hi));
        });
      }
      if (!Number.isFinite(xMin)) {
        xMin = 0;
        xMax = 1;
      }
      if (xMin === xMax) xMax = xMin + 1e-9;
      const sx = (rx) => pad.l + ((rx - xMin) / (xMax - xMin)) * iw;
      const sy = (ny) => pad.t + (1 - ny) * ih;
      if (msgEl) {
        msgEl.style.display = hasDist ? "none" : "block";
        msgEl.textContent = "No data yet";
      }
      const knots = knotsDisplay(method, bps);
      let dPoly = "";
      knots.forEach((k, i) => {
        const px = sx(k.x);
        const py = sy(k.y);
        dPoly += (i === 0 ? "M " : " L ") + px + " " + py;
      });
      const histMaxH = ih * 0.38;
      let maxC = 1;
      if (hasDist) maxC = Math.max(1, ...dist.counts.map((c) => Number(c)));
      let histRects = "";
      if (hasDist) {
        dist.buckets.forEach(([lo, hi], idx) => {
          const c = Number(dist.counts[idx] || 0);
          const loN = Number(lo);
          const hiN = Number(hi);
          const bx = sx(loN);
          const bw = Math.max(1.5, sx(hiN) - sx(loN));
          const bh = (c / maxC) * histMaxH;
          const by = pad.t + ih - bh;
          histRects += `<rect x="${bx}" y="${by}" width="${bw}" height="${bh}" fill="var(--accent)" opacity="0.22" />`;
        });
      }
      let handles = "";
      knots.forEach((k, idx) => {
        handles += `<circle data-kidx="${idx}" cx="${sx(k.x)}" cy="${sy(
          k.y,
        )}" r="5" fill="var(--panel)" stroke="var(--accent)" stroke-width="2" style="cursor:grab" />`;
      });
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
      svg.setAttribute("preserveAspectRatio", "xMinYMin meet");
      svg.setAttribute("data-chart-w", String(W));
      svg.setAttribute("data-chart-h", String(H));
      svg.innerHTML = `
        <rect x="0" y="0" width="${W}" height="${H}" fill="transparent" />
        <line x1="${pad.l}" y1="${pad.t + ih}" x2="${pad.l + iw}" y2="${pad.t + ih}" stroke="var(--border)" stroke-width="1" />
        <line x1="${pad.l}" y1="${pad.t}" x2="${pad.l}" y2="${pad.t + ih}" stroke="var(--border)" stroke-width="1" />
        ${histRects}
        <path d="${dPoly}" fill="none" stroke="var(--accent)" stroke-width="2" />
        ${handles}
        <text x="${pad.l}" y="${H - 6}" font-size="10" fill="var(--muted)">raw →</text>
        <text x="4" y="${pad.t + 10}" font-size="9" fill="var(--muted)" transform="rotate(-90 4 ${pad.t + ih / 2})">norm</text>
      `;
      svg.onmousemove = (ev) => {
        if (state.normDrag) return;
        const { x } = normChartPointer(svg, ev, W, H);
        const rx = xMin + ((x - pad.l) / iw) * (xMax - xMin);
        if (x < pad.l || x > pad.l + iw) {
          tip.style.display = "none";
          return;
        }
        const ny = evalPiecewiseDisplay(rx, method, bps);
        tip.style.display = "block";
        tip.textContent = `raw=${rx.toPrecision(4)}, norm=${ny.toPrecision(4)}`;
        const r = svg.getBoundingClientRect();
        const xPx = ev.clientX - r.left;
        tip.style.left = Math.min(Math.max(0, r.width - 124), xPx + 8) + "px";
        tip.style.top = Math.max(4, ev.offsetY - 28) + "px";
      };
      svg.onmouseleave = () => {
        tip.style.display = "none";
      };
      svg.querySelectorAll("circle[data-kidx]").forEach((cir) => {
        cir.addEventListener("mousedown", (ev) => {
          ev.preventDefault();
          state.normDrag = { metric, idx: Number(cir.getAttribute("data-kidx")) };
        });
      });
      syncNormInputs(metric);
    }

    function syncNormInputs(metric) {
      const card = ensureMetricCard(metric);
      if (!card) return;
      const mc = state.editorMN[metric];
      const bps = sortBreakpointPairs(mc.breakpoints || []);
      mc.breakpoints = bps.map((p) => [p[0], p[1]]);
      let idx = state.selectedBpIndex[metric];
      if (idx == null || idx >= bps.length) idx = 0;
      state.selectedBpIndex[metric] = idx;
      const rawIn = card.querySelector('[data-role="raw-in"]');
      const normIn = card.querySelector('[data-role="norm-in"]');
      const pt = bps[idx];
      if (pt && rawIn && normIn) {
        rawIn.value = String(pt[0]);
        normIn.value = String(pt[1]);
      }
    }

    function wireNormCard(metric) {
      const card = ensureMetricCard(metric);
      if (!card) return;
      const rawIn = card.querySelector('[data-role="raw-in"]');
      const normIn = card.querySelector('[data-role="norm-in"]');
      const applyPt = () => {
        const mc = state.editorMN[metric];
        let bps = sortBreakpointPairs(mc.breakpoints || []);
        const idx = state.selectedBpIndex[metric] || 0;
        const rx = Number(rawIn.value);
        const ny = Number(normIn.value);
        if (!Number.isFinite(rx) || !Number.isFinite(ny)) return;
        if (bps[idx]) {
          bps[idx][0] = rx;
          bps[idx][1] = Math.max(0, Math.min(1, ny));
        }
        const seen = new Set();
        bps = bps.filter((p) => {
          const k = p[0].toFixed(8);
          if (seen.has(k)) return false;
          seen.add(k);
          return true;
        });
        bps.sort((a, b) => a[0] - b[0]);
        mc.breakpoints = bps;
        state.selectedBpIndex[metric] = Math.min(idx, bps.length - 1);
        redrawNormMetric(metric);
      };
      rawIn.addEventListener("change", applyPt);
      normIn.addEventListener("change", applyPt);
      card.querySelector('[data-action="add-point"]').addEventListener("click", () => {
        const mc = state.editorMN[metric];
        let bps = sortBreakpointPairs(mc.breakpoints || []);
        if (bps.length < 2) return;
        let best = -1;
        let mid = null;
        let ny = 0;
        for (let i = 0; i < bps.length - 1; i++) {
          const gap = bps[i + 1][0] - bps[i][0];
          if (gap > best) {
            best = gap;
            mid = (bps[i][0] + bps[i + 1][0]) / 2;
            ny = (bps[i][1] + bps[i + 1][1]) / 2;
          }
        }
        if (mid == null) return;
        bps.push([mid, ny]);
        bps = sortBreakpointPairs(bps);
        mc.breakpoints = bps;
        state.selectedBpIndex[metric] = bps.findIndex((p) => p[0] === mid);
        redrawNormMetric(metric);
      });
      card.querySelector('[data-action="reset-metric"]').addEventListener("click", () => {
        const base = state.baselineMN[metric];
        if (!base) return;
        state.editorMN[metric] = clone(base);
        state.selectedBpIndex[metric] = 0;
        redrawNormMetric(metric);
      });
    }

    function bindNormDragGlobal() {
      window.addEventListener("mousemove", (ev) => {
        if (!state.normDrag) return;
        const { metric, idx } = state.normDrag;
        const card = ensureMetricCard(metric);
        if (!card) return;
        const svg = card.querySelector('svg[data-role="chart"]');
        const W = Number(svg.getAttribute("data-chart-w")) || normChartDimensions().W;
        const H = Number(svg.getAttribute("data-chart-h")) || 120;
        const { x: px, y: py } = normChartPointer(svg, ev, W, H);
        const mc = state.editorMN[metric];
        const method = mc.method;
        const bps = sortBreakpointPairs(mc.breakpoints || []);
        if (idx < 0 || idx >= bps.length) return;
        const pad = { l: 30, r: 12, t: 12, b: 24 };
        const iw = W - pad.l - pad.r;
        const ih = H - pad.t - pad.b;
        let xMin = Infinity;
        let xMax = -Infinity;
        bps.forEach(([rx]) => {
          xMin = Math.min(xMin, rx);
          xMax = Math.max(xMax, rx);
        });
        const dist = state.distributionCache[metric];
        const hasDist =
          dist &&
          Array.isArray(dist.counts) &&
          dist.counts.some((c) => Number(c) > 0);
        if (hasDist && dist.buckets) {
          dist.buckets.forEach(([lo, hi]) => {
            xMin = Math.min(xMin, Number(lo));
            xMax = Math.max(xMax, Number(hi));
          });
        }
        if (!Number.isFinite(xMin)) {
          xMin = 0;
          xMax = 1;
        }
        if (xMin === xMax) xMax = xMin + 1e-9;
        const bpIdx = idx;
        const prev = bpIdx > 0 ? bps[bpIdx - 1][0] : xMin;
        const next = bpIdx < bps.length - 1 ? bps[bpIdx + 1][0] : xMax;
        let rx = xMin + ((px - pad.l) / iw) * (xMax - xMin);
        rx = Math.max(prev + 1e-12, Math.min(next - 1e-12, rx));
        let nyDisp = 1 - (py - pad.t) / ih;
        nyDisp = Math.max(0, Math.min(1, nyDisp));
        let nyCfg = method === "inverse_piecewise" ? 1 - nyDisp : nyDisp;
        nyCfg = Math.max(0, Math.min(1, nyCfg));
        bps[bpIdx][0] = rx;
        bps[bpIdx][1] = nyCfg;
        bps.sort((a, b) => a[0] - b[0]);
        mc.breakpoints = bps;
        let newIdx = bps.findIndex((p) => Math.abs(p[0] - rx) < 1e-9);
        if (newIdx < 0) newIdx = bpIdx;
        state.selectedBpIndex[metric] = newIdx;
        state.normDrag = { metric, idx: newIdx };
        redrawNormMetric(metric);
      });
      window.addEventListener("mouseup", () => {
        state.normDrag = null;
      });
    }

    function renderScoreWeights() {
      const host = $("scoreWeightsPanel");
      host.innerHTML = "<strong>Score aggregation weights</strong>";
      WEIGHT_GROUPS.forEach((gk) => {
        const wg = document.createElement("div");
        wg.className = "weight-group";
        wg.dataset.weightGroup = gk;
        const title = gk.replace(/_/g, " ");
        const weights = state.editorSA[gk] || {};
        const rows = Object.keys(weights)
          .sort()
          .map((key) => {
            const v = Number(weights[key]);
            return `<div class="weight-row" data-wkey="${key}">
              <label>${key}</label>
              <input type="range" min="0" max="1" step="0.01" data-role="w-slider" value="${v}" />
              <input type="number" step="0.01" min="0" data-role="w-num" class="norm-num-in" value="${v}" />
            </div>`;
          })
          .join("");
        wg.innerHTML = `<h3>${title}</h3>${rows}<div class="weight-sum-badge ok" data-role="sum-badge">Σ = 0</div>`;
        host.appendChild(wg);
        wg.querySelectorAll(".weight-row").forEach((row) => {
          const slider = row.querySelector('[data-role="w-slider"]');
          const num = row.querySelector('[data-role="w-num"]');
          const key = row.getAttribute("data-wkey");
          slider.addEventListener("input", () => {
            num.value = slider.value;
            state.editorSA[gk][key] = Number(slider.value);
            updateWeightSumBadge(wg);
          });
          num.addEventListener("change", () => {
            let val = Number(num.value);
            if (!Number.isFinite(val) || val < 0) val = 0;
            slider.value = String(val);
            state.editorSA[gk][key] = val;
            updateWeightSumBadge(wg);
          });
        });
        updateWeightSumBadge(wg);
      });
    }

    function updateWeightSumBadge(groupEl) {
      const gk = groupEl.dataset.weightGroup;
      const m = state.editorSA[gk] || {};
      let s = 0;
      Object.keys(m).forEach((k) => {
        const v = Number(m[k]);
        if (Number.isFinite(v)) s += v;
      });
      const badge = groupEl.querySelector('[data-role="sum-badge"]');
      badge.textContent = `Σ = ${s.toFixed(3)}`;
      badge.classList.toggle("ok", s <= 1.0 + 1e-6);
      badge.classList.toggle("bad", s > 1.0 + 1e-6);
    }

    async function refreshDistributionsOnly() {
      const mn = state.editorMN || {};
      const metrics = Object.keys(mn).filter((m) => {
        const method = mn[m].method;
        return method === "piecewise" || method === "inverse_piecewise";
      });
      await Promise.all(
        metrics.map(async (m) => {
          try {
            const res = await fetch(`/api/stats/distribution?metric=${encodeURIComponent(m)}`);
            if (!res.ok) return;
            const data = await res.json();
            state.distributionCache[m] = data;
          } catch (_) {
            state.distributionCache[m] = { buckets: [], counts: [] };
          }
        }),
      );
      metrics.forEach((m) => redrawNormMetric(m));
    }

    function renderOverviewSummary(cfg) {
      const el = $("overviewSummaryPanel");
      const project = cfg.project || {};
      const lines = [
        ["Project path", project.path ?? "n/a"],
        ["Granularity", cfg.granularity ?? "n/a"],
        ["Score metrics", cfg.score_metrics ?? []],
      ];
      el.innerHTML = lines
        .map(([k, v]) => `<div><strong>${k}</strong>: ${pretty(v)}</div>`)
        .join("");
    }

    function renderNormEditors() {
      const panel = $("configPanel");
      panel.innerHTML = "";
      const mn = state.editorMN || {};
      Object.keys(mn)
        .sort()
        .forEach((metric) => {
          const rule = mn[metric];
          const method = rule.method || "";
          const details = document.createElement("details");
          details.className = "norm-metric-card";
          details.dataset.metric = metric;
          if (method === "piecewise" || method === "inverse_piecewise") {
            details.innerHTML = `
<summary>${metric} <span class="muted">(${method})</span></summary>
<div class="dist-placeholder" data-role="dist-msg">No data yet</div>
<div class="norm-svg-wrap">
  <svg data-role="chart" viewBox="0 0 280 120" preserveAspectRatio="xMinYMin meet"></svg>
  <div class="norm-tooltip" data-role="tip"></div>
</div>
<div class="norm-controls">
  <span>Selected point</span>
  <label>raw <input class="norm-num-in" data-role="raw-in" type="number" step="any" /></label>
  <label>norm <input class="norm-num-in" data-role="norm-in" type="number" step="any" min="0" max="1" /></label>
  <button type="button" data-action="add-point">+ point</button>
  <button type="button" data-action="reset-metric">reset</button>
</div>
<div class="muted" data-role="inv-label" style="display:${method === "inverse_piecewise" ? "block" : "none"};font-size:0.72rem;margin-top:0.25rem;">
  inverse_piecewise: Y axis inverted vs stored YAML (higher upward = worse after mapping)
</div>`;
            panel.appendChild(details);
            state.selectedBpIndex[metric] = 0;
            wireNormCard(metric);
            redrawNormMetric(metric);
          } else {
            details.innerHTML = `<summary>${metric} <span class="muted">(${method})</span></summary><div class="mono">${pretty(rule)}</div>`;
            panel.appendChild(details);
          }
        });
    }

    function renderConfigMeta(cfg) {
      const meta = $("configMetaPanel");
      const project = cfg.project || {};
      const dashboard = cfg.dashboard || {};
      const lines = [
        ["Project Path", project.path],
        ["Granularity", cfg.granularity],
        ["Score Metrics", cfg.score_metrics || []],
        ["Decay Half-life", cfg.decay_half_life],
        ["Similarity Enabled", cfg.similarity_enabled],
        ["Dashboard default_target", dashboard.default_target],
        ["Version", cfg.version],
      ];
      meta.innerHTML = lines
        .map(([k, v]) => `<div><strong>${k}</strong>: ${pretty(v)}</div>`)
        .join("");
    }

    const ROUTES = ["overview", "heatmap", "config"];
    function normalizeRouteHash() {
      let h = (location.hash || "").replace(/^#/, "").trim().toLowerCase();
      if (!h || !ROUTES.includes(h)) return "overview";
      return h;
    }

    function applyRoute(route) {
      ROUTES.forEach((r) => {
        const sec = document.querySelector(`[data-view="${r}"]`);
        const tab = document.querySelector(`.nav-tab[data-route="${r}"]`);
        if (sec) sec.classList.toggle("active", r === route);
        if (tab) tab.classList.toggle("active", r === route);
      });
      if (route === "heatmap") refreshHeatmap();
      if (route === "config") {
        requestAnimationFrame(() => redrawAllNormMetrics());
      }
    }

    function initRouting() {
      const r = normalizeRouteHash();
      if ((location.hash || "").replace(/^#/, "").trim().toLowerCase() !== r) {
        history.replaceState(null, "", "#" + r);
      }
      applyRoute(r);
      window.addEventListener("hashchange", () => applyRoute(normalizeRouteHash()));
    }

    function escapeHtml(s) {
      return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    function escapeAttr(s) {
      return escapeHtml(s).replace(/"/g, "&quot;");
    }

    function heatmapBarBandClass(band) {
      const b = String(band || "").toLowerCase();
      if (b === "low") return "band-low";
      if (b === "medium") return "band-medium";
      if (b === "high") return "band-high";
      if (b === "critical") return "band-critical";
      return "";
    }

    /** RGBA heat ramp shared by all numeric heatmap columns (greens → red). */
    function heatColor(pct) {
      const p = Math.max(0, Math.min(1, Number(pct) || 0));
      if (p <= 0.33) return `rgba(34,197,94,${0.16 + p * 0.30})`;
      if (p <= 0.66) return `rgba(234,179,8,${0.20 + (p - 0.33) * 0.36})`;
      if (p <= 0.85) return `rgba(249,115,22,${0.22 + (p - 0.66) * 0.58})`;
      return `rgba(239,68,68,${0.35 + (p - 0.85) * 2.0})`;
    }

    /** Heatmap header: underscores → spaces; up to two lines (word-boundary split). */
    function heatmapColumnHeaderHtml(rawId) {
      const label = String(rawId || "")
        .replace(/_/g, " ")
        .split(" ")
        .filter(Boolean)
        .join(" ");
      const words = label.split(" ").filter(Boolean);
      if (words.length <= 1) return escapeHtml(label);
      const mid = Math.ceil(words.length / 2);
      const line1 = escapeHtml(words.slice(0, mid).join(" "));
      const line2 = escapeHtml(words.slice(mid).join(" "));
      return `${line1}<br>${line2}`;
    }

    function initHeatmapControls() {
      mirrorCacheInputs("cache");
      $("heatmapUpdateBtn").addEventListener("click", updateHeatmapData);
    }

    async function refreshHeatmap() {
      const panel = $("heatmapPanel");
      const status = $("heatmapStatus");
      let lim = Number($("heatmapLimitInput").value);
      if (!Number.isFinite(lim) || lim < 1) lim = 500;
      if (lim > 500) lim = 500;
      $("heatmapLimitInput").value = String(lim);
      status.textContent = "Loading…";
      try {
        const res = await fetch(`/api/stats/heatmap?limit=${encodeURIComponent(String(lim))}`);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const d = data.detail;
          status.textContent =
            typeof d === "string" ? d : Array.isArray(d) ? JSON.stringify(d) : "request failed";
          return;
        }
        const rows = data.rows || [];
        status.textContent = `${rows.length} row(s)`;
        if (!rows.length) {
          panel.className = "muted";
          panel.textContent = "No heatmap rows yet.";
          return;
        }
        const cols = Array.isArray(data.columns) ? data.columns : [];
        const serverMax =
          data.column_maxima && typeof data.column_maxima === "object"
            ? data.column_maxima
            : null;
        const maxima = {};
        cols.forEach((c) => {
          const sm = serverMax ? Number(serverMax[c]) : NaN;
          if (Number.isFinite(sm) && sm > 0) {
            maxima[c] = sm;
            return;
          }
          const eligible = rows.filter((r) => !String(r.path || "").startsWith("__"));
          const src = eligible.length ? eligible : rows;
          maxima[c] = Math.max(...src.map((r) => Number(r[c]) || 0), 1e-9);
        });
        const head = `<tr><th class="heatmap-file-col">file</th><th class="heatmap-method-col">method</th>${cols
          .map((c) => {
            const plain = String(c || "")
              .replace(/_/g, " ")
              .split(" ")
              .filter(Boolean)
              .join(" ");
            return `<th class="heatmap-metric-th" title="${escapeAttr(plain)}">${heatmapColumnHeaderHtml(c)}</th>`;
          })
          .join("")}<th>band</th></tr>`;
        const body = rows
          .map((r) => {
            const cells = cols
              .map((c) => {
                const v = Number(r[c]) || 0;
                const pct = Math.min(1, Math.max(0, v / (maxima[c] || 1)));
                return `<td class="heatmap-metric-cell" style="background:${heatColor(pct)};">${v.toFixed(3)}</td>`;
              })
              .join("");
            return `<tr>
  <td class="heatmap-file-col" title="${escapeAttr(r.file || "")}">${escapeHtml(r.file || "")}</td>
  <td class="heatmap-method-col" title="${escapeAttr(r.method || "")}"><span class="heatmap-method">${escapeHtml(r.method || "")}</span></td>
  ${cells}
  <td>${escapeHtml(r.score_band || "")}</td>
</tr>`;
          })
          .join("");
        panel.className = "";
        panel.innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
      } catch (e) {
        status.textContent = String(e);
      }
    }

    async function updateHeatmapData() {
      await generateCache("heatmap");
      await refreshHeatmap();
    }

    function $(id) { return document.getElementById(id); }

    function updateCacheContext(statusText) {
      const target = $("cacheTargetInput").value.trim() || "n/a";
      const filter = $("cacheFilterInput").value.trim() || "<none>";
      const score = $("cacheScoreInput").value.trim() || "churn_per_sloc,cyclomatic";
      $("cacheContextPanel").textContent =
`Path: ${target}
Cache Status: ${statusText}
Build Parameters: filter=${filter}, score_metrics=${score}`;
    }

    function mirrorCacheInputs(fromPrefix) {
      const fromHeatmap = fromPrefix === "heatmap";
      const srcTarget = $(fromHeatmap ? "heatmapTargetInput" : "cacheTargetInput");
      const srcFilter = $(fromHeatmap ? "heatmapFilterInput" : "cacheFilterInput");
      const srcScore = $(fromHeatmap ? "heatmapScoreInput" : "cacheScoreInput");
      const dstTarget = $(fromHeatmap ? "cacheTargetInput" : "heatmapTargetInput");
      const dstFilter = $(fromHeatmap ? "cacheFilterInput" : "heatmapFilterInput");
      const dstScore = $(fromHeatmap ? "cacheScoreInput" : "heatmapScoreInput");
      if (srcTarget && dstTarget) dstTarget.value = srcTarget.value;
      if (srcFilter && dstFilter) dstFilter.value = srcFilter.value;
      if (srcScore && dstScore) dstScore.value = srcScore.value;
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

    async function saveConfigPatch() {
      const status = $("configSaveStatus");
      status.textContent = "";
      try {
        const res = await fetch("/api/config/patch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            metric_normalization: state.editorMN,
            score_aggregation: state.editorSA,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const d = data.detail;
          status.textContent =
            typeof d === "string" ? d : Array.isArray(d) ? JSON.stringify(d) : "save failed";
          return;
        }
        status.textContent = "Saved.";
        await loadConfigFull();
      } catch (e) {
        status.textContent = String(e);
      }
    }

    async function loadConfigFull() {
      const panel = $("configPanel");
      try {
        const res = await fetch("/api/config");
        if (!res.ok) throw new Error("config request failed");
        const cfg = await res.json();
        const dashboard = cfg.dashboard || {};
        if (dashboard.default_target && !$("cacheTargetInput").value.trim()) {
          $("cacheTargetInput").value = String(dashboard.default_target);
        }
        updateCacheContext("unknown");
        state.editorMN = clone(cfg.metric_normalization || {});
        state.editorSA = clone(cfg.score_aggregation || {});
        state.baselineMN = clone(cfg.metric_normalization || {});
        state.baselineSA = clone(cfg.score_aggregation || {});
        renderOverviewSummary(cfg);
        renderNormEditors();
        renderScoreWeights();
        renderConfigMeta(cfg);
        await refreshDistributionsOnly();
      } catch (err) {
        panel.innerHTML = `<div class="muted">Failed to load config: ${String(err)}</div>`;
      }
    }

    async function loadConfig() {
      await loadConfigFull();
    }

    async function loadCacheContext(overwrite = false) {
      try {
        const res = await fetch("/api/cache/context");
        if (!res.ok) return;
        const ctx = await res.json();
        applyCacheContext(ctx, overwrite);
        updateCacheContext(ctx.last_target ? "restored" : "unknown");
      } catch (_) {
        // no-op: context restore is best-effort
      }
    }

    function applyCacheContext(ctx, overwrite) {
      if (!ctx || typeof ctx !== "object") return;
      const targetIds = ["cacheTargetInput", "heatmapTargetInput"];
      const filterIds = ["cacheFilterInput", "heatmapFilterInput"];
      const scoreIds = ["cacheScoreInput", "heatmapScoreInput"];
      targetIds.forEach((id) => {
        const el = $(id);
        if (!el) return;
        if ((overwrite || !el.value.trim()) && ctx.last_target) {
          el.value = String(ctx.last_target);
        }
      });
      filterIds.forEach((id) => {
        const el = $(id);
        if (!el) return;
        if ((overwrite || !el.value.trim()) && ctx.last_filter) {
          el.value = String(ctx.last_filter);
        }
      });
      scoreIds.forEach((id) => {
        const el = $(id);
        if (!el) return;
        if ((overwrite || !el.value.trim()) && ctx.last_score_metrics) {
          el.value = String(ctx.last_score_metrics);
        }
      });
    }

    async function saveCacheContext({ overwrite = true, statusText = null, sourcePrefix = "cache" } = {}) {
      const fromHeatmap = sourcePrefix === "heatmap";
      const payload = {
        target: $(fromHeatmap ? "heatmapTargetInput" : "cacheTargetInput").value.trim(),
        filter: $(fromHeatmap ? "heatmapFilterInput" : "cacheFilterInput").value.trim(),
        score_metrics: $(fromHeatmap ? "heatmapScoreInput" : "cacheScoreInput").value.trim() || "churn_per_sloc,cyclomatic",
      };
      try {
        const res = await fetch("/api/cache/context", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          const ctx = await res.json();
          applyCacheContext(ctx, overwrite);
          updateCacheContext(statusText || "saved");
          return ctx;
        }
      } catch (_) {
        // no-op
      }
      return null;
    }

    async function normalizeTargetForAction(sourcePrefix = "cache") {
      // Keep button actions responsive: best-effort normalization with short timeout.
      const normalizePromise = saveCacheContext({
        overwrite: true,
        statusText: "normalizing target",
        sourcePrefix,
      });
      const timeoutPromise = new Promise((resolve) => setTimeout(() => resolve(null), 700));
      await Promise.race([normalizePromise, timeoutPromise]);
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

    async function generateCache(sourcePrefix = "cache") {
      const fromHeatmap = sourcePrefix === "heatmap";
      const box = $("cacheStatus");
      const bar = $("cacheProgress");
      box.textContent = "Starting cache generation…";
      bar.classList.remove("done", "err");
      bar.style.width = "8%";
      await normalizeTargetForAction(sourcePrefix);
      const target = $(fromHeatmap ? "heatmapTargetInput" : "cacheTargetInput").value.trim();
      const filter = $(fromHeatmap ? "heatmapFilterInput" : "cacheFilterInput").value.trim();
      const score = $(fromHeatmap ? "heatmapScoreInput" : "cacheScoreInput").value.trim() || "churn_per_sloc,cyclomatic";
      if (!target) {
        box.textContent = "Target path is required.";
        updateCacheContext("invalid target");
        bar.classList.remove("done");
        bar.classList.add("err");
        bar.style.width = "100%";
        return;
      }
      try {
        const startRes = await fetch("/api/cache/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target,
            filter: filter || null,
            score_metrics: score
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
        state.activeCacheJobId = started.job_id;
        await loadCacheContext(true);
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

    async function checkCacheStatus(sourcePrefix = "cache") {
      const fromHeatmap = sourcePrefix === "heatmap";
      const box = $("cacheStatus");
      const bar = $("cacheProgress");
      box.textContent = "Checking cache…";
      bar.classList.remove("done", "err");
      bar.style.width = "25%";
      await normalizeTargetForAction(sourcePrefix);
      const target = $(fromHeatmap ? "heatmapTargetInput" : "cacheTargetInput").value.trim();
      if (!target) {
        box.textContent = "Target path is required.";
        updateCacheContext("invalid target");
        bar.classList.remove("done");
        bar.classList.add("err");
        bar.style.width = "100%";
        return;
      }
      try {
        const res = await fetch("/api/cache/status", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target,
            filter: $(fromHeatmap ? "heatmapFilterInput" : "cacheFilterInput").value.trim() || null,
            score_metrics: $(fromHeatmap ? "heatmapScoreInput" : "cacheScoreInput").value.trim() || "churn_per_sloc,cyclomatic"
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
        const runningFor = Number(data.running_for_s || 0);
        const animated = Math.min(95, Math.max(p, 30 + Math.floor(runningFor * 0.8)));
        bar.style.width = `${animated}%`;
        const baseMessage = data.message || "Running cache job...";
        box.textContent =
          data.status === "running"
            ? `${baseMessage} (${runningFor.toFixed(1)}s)`
            : baseMessage;
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
        return;
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
      $("generateCacheBtn").addEventListener("click", generateCache);
      ["cacheTargetInput", "cacheFilterInput", "cacheScoreInput"].forEach((id) => {
        $(id).addEventListener("input", () => {
          mirrorCacheInputs("cache");
          updateCacheContext("pending");
          saveCacheContext({ overwrite: false, statusText: "pending", sourcePrefix: "cache" });
        });
        $(id).addEventListener("blur", () => {
          saveCacheContext({ overwrite: true, statusText: "resolved", sourcePrefix: "cache" });
        });
        $(id).addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") {
            saveCacheContext({ overwrite: true, statusText: "resolved", sourcePrefix: "cache" });
          }
        });
      });
      ["heatmapTargetInput", "heatmapFilterInput", "heatmapScoreInput"].forEach((id) => {
        $(id).addEventListener("input", () => {
          mirrorCacheInputs("heatmap");
          updateCacheContext("pending");
          saveCacheContext({ overwrite: false, statusText: "pending", sourcePrefix: "heatmap" });
        });
        $(id).addEventListener("blur", () => {
          saveCacheContext({ overwrite: true, statusText: "resolved", sourcePrefix: "heatmap" });
        });
        $(id).addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") {
            saveCacheContext({ overwrite: true, statusText: "resolved", sourcePrefix: "heatmap" });
          }
        });
      });
      $("clearLogsBtn").addEventListener("click", clearLogs);
      $("pauseLogsBtn").addEventListener("click", () => {
        state.pauseScroll = !state.pauseScroll;
        $("pauseLogsBtn").textContent = `Pause Scroll: ${state.pauseScroll ? "On" : "Off"}`;
      });
      $("configSaveBtn").addEventListener("click", saveConfigPatch);
      $("configRefreshDataBtn").addEventListener("click", async () => {
        $("configSaveStatus").textContent = "";
        await refreshDistributionsOnly();
      });
    }

    let normResizeTimer = null;
    function scheduleNormChartResize() {
      if (normResizeTimer) clearTimeout(normResizeTimer);
      normResizeTimer = setTimeout(() => {
        normResizeTimer = null;
        redrawAllNormMetrics();
      }, 150);
    }

    async function init() {
      const saved = localStorage.getItem("ht-dashboard-theme");
      setTheme(saved === "dark");
      initEvents();
      bindNormDragGlobal();
      initHeatmapControls();
      window.addEventListener("resize", scheduleNormChartResize);
      initRouting();
      await loadConfig();
      await loadCacheContext();
      if ($("cacheTargetInput").value.trim()) {
        void checkCacheStatus("cache");
      }
      await refreshStats();
      await refreshHealth();
      connectLogStream();
      setInterval(refreshStats, 5000);
      setInterval(refreshHealth, 10000);
      setInterval(refreshDistributionsOnly, 30000);
    }

    init();
  </script>
</body>
</html>
"""
