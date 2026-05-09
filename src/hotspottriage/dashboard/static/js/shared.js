// Shared dashboard state and utilities
const state = {
  lastLogIdx: 0,
  pauseScroll: false,
  healthFailures: 0,
  activeCacheJobId: null,
  heatmapRows: [],
  heatmapColumns: [],
  heatmapColumnMaxima: {},
  editorMN: null,
  editorSA: null,
  editorPM: null,
  baselineMN: null,
  baselineSA: null,
  baselinePM: null,
  distributionCache: {},
  selectedBpIndex: {},
  normDrag: null,
};

const FINAL_BURDEN_KEYS = [
  "complexity_burden",
  "churn_burden",
  "maintainability_burden",
  "smell_burden",
  "similarity_burden",
];
const WEIGHT_GROUPS = [
  "final_weights",
  "complexity_weights",
  "churn_weights",
  "smell_weights",
  "similarity_weights",
];
const DEFAULT_BAND_EDGES = [0.30, 0.60, 0.80];
const DEFAULT_BAND_NAMES = ["low", "medium", "high", "critical"];

function clone(o) {
  return JSON.parse(JSON.stringify(o));
}

function $(id) { return document.getElementById(id); }

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, "&quot;");
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

function truncateLeftLabelToWidth(value, maxWidthPx = 168) {
  const text = String(value || "");
  const maxWidth = Number(maxWidthPx);
  if (!Number.isFinite(maxWidth) || maxWidth <= 0) return text;
  if (!truncateLeftLabelToWidth._ctx) {
    const canvas = document.createElement("canvas");
    truncateLeftLabelToWidth._ctx = canvas.getContext("2d");
  }
  const ctx = truncateLeftLabelToWidth._ctx;
  if (!ctx) return text;
  ctx.font = '0.74rem ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace';
  if (ctx.measureText(text).width <= maxWidth) return text;
  const ellipsis = "\u2026";
  let lo = 1;
  let hi = text.length;
  let best = ellipsis + text.slice(-1);
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    const candidate = ellipsis + text.slice(-mid);
    if (ctx.measureText(candidate).width <= maxWidth) {
      best = candidate;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return best;
}

async function refreshHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) throw new Error("health request failed");
    const data = await res.json();
    state.healthFailures = 0;
    $("healthDot").classList.remove("dead");
    $("healthText").textContent = `Alive \u00b7 ${data.uptime_s ?? "?"}s`;
  } catch (_) {
    state.healthFailures += 1;
    if (state.healthFailures >= 3) {
      $("healthDot").classList.add("dead");
      $("healthText").textContent = "Unavailable";
    }
  }
}

function renderOverviewSummary(cfg) {
  const el = $("overviewSummaryPanel");
  if (!el) return;
  const project = cfg.project || {};
  const lines = [
    ["Project path", project.path ?? "n/a"],
    ["Granularity", cfg.granularity ?? "n/a"],
  ];
  el.innerHTML = lines
    .map(([k, v]) => `<div><strong>${k}</strong>: ${pretty(v)}</div>`)
    .join("");
}

/** Repo directory from merged HotspotTriage config (``/api/config``): YAML + server snapshot. */
function directoryFromConfig(cfg) {
  if (!cfg || typeof cfg !== "object") return "";
  const dash = cfg.dashboard || {};
  const dt = String(dash.default_target || "").trim();
  if (dt) return dt;
  const proj = cfg.project || {};
  return String(proj.path || "").trim();
}

/** Mirror Overview's repo path into the Heatmap read-only display (multi-page safe). */
async function syncHeatmapRepoDisplay() {
  const el = $("heatmapRepoRootDisplay");
  if (!el) return;
  let v = "";
  try {
    const res = await fetch("/api/config");
    if (res.ok) {
      const cfg = await res.json();
      v = directoryFromConfig(cfg);
    }
  } catch (_) {
    /* best-effort */
  }
  if (!v) {
    const input = $("cacheTargetInput");
    v = input ? (input.value || "").trim() : "";
  }
  if (!v) {
    try {
      const res = await fetch("/api/cache/context");
      if (res.ok) {
        const ctx = await res.json();
        if (ctx.last_target) v = String(ctx.last_target).trim();
      }
    } catch (_) {
      /* best-effort */
    }
  }
  el.textContent = v || "\u2014";
}

async function loadConfigFull() {
  const panel = $("configPanel");
  try {
    const res = await fetch("/api/config");
    if (!res.ok) throw new Error("config request failed");
    const cfg = await res.json();
    const targetEl = $("cacheTargetInput");
    const dir = directoryFromConfig(cfg);
    if (targetEl && dir) {
      targetEl.value = dir;
    }
    if (typeof updateCacheContext === "function") updateCacheContext("unknown");
    await syncHeatmapRepoDisplay();
    state.editorMN = clone(cfg.metric_normalization || {});
    state.editorSA = clone(cfg.score_aggregation || {});
    state.editorPM = clone(cfg.proposed_models || {});
    state.baselineMN = clone(cfg.metric_normalization || {});
    state.baselineSA = clone(cfg.score_aggregation || {});
    state.baselinePM = clone(cfg.proposed_models || {});
    renderOverviewSummary(cfg);
    if (typeof renderNormEditors === "function") renderNormEditors();
    if (typeof renderProposedModels === "function") renderProposedModels();
    if (typeof renderScoreBands === "function") renderScoreBands();
    if (typeof renderScoreWeights === "function") renderScoreWeights();
    if (typeof renderConfigMeta === "function") renderConfigMeta(cfg);
    if (typeof refreshDistributionsOnly === "function") await refreshDistributionsOnly();
  } catch (err) {
    if (panel) panel.innerHTML = `<div class="muted">Failed to load config: ${String(err)}</div>`;
  }
}

async function loadConfig() {
  await loadConfigFull();
}

async function saveConfigPatch() {
  const status = $("configSaveStatus");
  if (status) status.textContent = "";
  try {
    const res = await fetch("/api/config/patch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        metric_normalization: state.editorMN,
        score_aggregation: state.editorSA,
        proposed_models: state.editorPM,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = data.detail;
      if (status) {
        status.textContent =
          typeof d === "string" ? d : Array.isArray(d) ? JSON.stringify(d) : "save failed";
      }
      return;
    }
    if (status) status.textContent = "Saved.";
    await loadConfigFull();
  } catch (e) {
    if (status) status.textContent = String(e);
  }
}

function initTheme() {
  const saved = localStorage.getItem("ht-dashboard-theme");
  setTheme(saved === "dark");
  const toggle = $("themeToggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      setTheme(!document.body.classList.contains("dark"));
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  refreshHealth();
  setInterval(refreshHealth, 10000);
});
