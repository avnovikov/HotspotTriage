// Config screen: normalization, weight, and band editor functions

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
    <text x="${pad.l}" y="${H - 6}" font-size="10" fill="var(--muted)">raw \u2192</text>
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
  ensureFinalWeights();
  host.innerHTML = "<strong>Score aggregation weights</strong>";
  WEIGHT_GROUPS.forEach((gk) => {
    const wg = document.createElement("div");
    wg.className = "weight-group";
    wg.dataset.weightGroup = gk;
    const title = gk === "final_weights"
      ? "top composite parameters (must sum to 1.0)"
      : gk.replace(/_/g, " ");
    const weights = state.editorSA[gk] || {};
    const keys = gk === "final_weights"
      ? FINAL_BURDEN_KEYS
      : Object.keys(weights).sort();
    const rows = keys
      .map((key) => {
        const v = Number(weights[key]);
        const shown = gk === "final_weights" ? v.toFixed(2) : String(v);
        return `<div class="weight-row" data-wkey="${key}">
          <label>${key}</label>
          <input type="range" min="0" max="1" step="0.01" data-role="w-slider" value="${v}" />
          <input type="number" step="0.01" min="0" data-role="w-num" class="norm-num-in" value="${shown}" />
        </div>`;
      })
      .join("");
    wg.innerHTML = `<h3>${title}</h3>${rows}<div class="weight-sum-badge ok" data-role="sum-badge">\u03A3 = 0</div>`;
    host.appendChild(wg);
    wg.querySelectorAll(".weight-row").forEach((row) => {
      const slider = row.querySelector('[data-role="w-slider"]');
      const num = row.querySelector('[data-role="w-num"]');
      const key = row.getAttribute("data-wkey");
      slider.addEventListener("input", () => {
        let val = Number(slider.value);
        if (!Number.isFinite(val) || val < 0) val = 0;
        val = Math.round(val * 100) / 100;
        slider.value = val.toFixed(2);
        if (gk === "final_weights") {
          setFinalWeight(key, val);
          renderScoreWeights();
          return;
        }
        num.value = val.toFixed(2);
        state.editorSA[gk][key] = val;
        updateWeightSumBadge(wg);
      });
      num.addEventListener("change", () => {
        let val = Number(num.value);
        if (!Number.isFinite(val) || val < 0) val = 0;
        val = Math.round(val * 100) / 100;
        if (gk === "final_weights") {
          setFinalWeight(key, val);
          renderScoreWeights();
          return;
        }
        slider.value = val.toFixed(2);
        num.value = val.toFixed(2);
        state.editorSA[gk][key] = val;
        updateWeightSumBadge(wg);
      });
    });
    updateWeightSumBadge(wg);
  });
}

function setFinalWeight(key, rawValue) {
  if (!state.editorSA) state.editorSA = {};
  if (!state.editorSA.final_weights || typeof state.editorSA.final_weights !== "object") {
    state.editorSA.final_weights = {};
  }
  const weights = { ...state.editorSA.final_weights };
  FINAL_BURDEN_KEYS.forEach((k) => {
    const v = Number(weights[k]);
    weights[k] = Number.isFinite(v) && v >= 0 ? v : 0;
  });
  const target = Math.max(0, Math.min(1, Number(rawValue) || 0));
  const otherKeys = FINAL_BURDEN_KEYS.filter((k) => k !== key);
  const otherSum = otherKeys.reduce((acc, k) => acc + Number(weights[k] || 0), 0);
  const remaining = 1 - target;
  if (otherKeys.length) {
    if (otherSum <= 1e-12) {
      const each = remaining / otherKeys.length;
      otherKeys.forEach((k) => {
        weights[k] = each;
      });
    } else {
      const factor = remaining / otherSum;
      otherKeys.forEach((k) => {
        weights[k] = Number(weights[k] || 0) * factor;
      });
    }
  }
  weights[key] = target;
  FINAL_BURDEN_KEYS.forEach((k) => {
    weights[k] = Math.round(weights[k] * 100) / 100;
  });
  const roundedSum = FINAL_BURDEN_KEYS.reduce((acc, k) => acc + weights[k], 0);
  const delta = Math.round((1 - roundedSum) * 100) / 100;
  if (Math.abs(delta) > 0 && Math.abs(delta) <= 0.02) {
    weights[key] = Math.max(0, Math.min(1, Math.round((weights[key] + delta) * 100) / 100));
  }
  state.editorSA.final_weights = weights;
}

function ensureFinalWeights() {
  if (!state.editorSA) state.editorSA = {};
  const source =
    state.editorSA.final_weights && typeof state.editorSA.final_weights === "object"
      ? state.editorSA.final_weights
      : {};
  const weights = {};
  FINAL_BURDEN_KEYS.forEach((k) => {
    const v = Number(source[k]);
    weights[k] = Number.isFinite(v) && v >= 0 ? v : 0;
  });
  const sum = FINAL_BURDEN_KEYS.reduce((acc, k) => acc + weights[k], 0);
  if (sum <= 1e-12) {
    const each = 1 / FINAL_BURDEN_KEYS.length;
    FINAL_BURDEN_KEYS.forEach((k) => {
      weights[k] = each;
    });
  } else {
    FINAL_BURDEN_KEYS.forEach((k) => {
      weights[k] = weights[k] / sum;
    });
  }
  state.editorSA.final_weights = weights;
}

function renderProposedModels() {
  const host = $("proposedModelsPanel");
  const models = state.editorPM || {};
  const bands = ["low", "medium", "high", "critical"];
  const rows = bands
    .map((band) => {
      const value = String(models[band] || "");
      return `<div class="weight-row" data-band="${band}">
        <label>${band}</label>
        <input type="text" data-role="model-text" value="${escapeAttr(value)}" style="grid-column: span 2;" />
      </div>`;
    })
    .join("");
  host.innerHTML = `<strong>Proposed models by risk band</strong>
    <div class="weight-group">
      ${rows}
    </div>`;
  host.querySelectorAll(".weight-row").forEach((row) => {
    const band = row.getAttribute("data-band");
    const input = row.querySelector('[data-role="model-text"]');
    input.addEventListener("input", () => {
      state.editorPM[band] = input.value;
    });
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
  if (gk === "final_weights") {
    badge.textContent = `\u03A3 = ${s.toFixed(3)} (must be 1.000)`;
    badge.classList.toggle("ok", Math.abs(s - 1.0) <= 1e-6);
    badge.classList.toggle("bad", Math.abs(s - 1.0) > 1e-6);
    return;
  }
  badge.textContent = `\u03A3 = ${s.toFixed(3)}`;
  badge.classList.toggle("ok", s <= 1.0 + 1e-6);
  badge.classList.toggle("bad", s > 1.0 + 1e-6);
}

function normalizedScoreBandConfig() {
  if (!state.editorSA) state.editorSA = {};
  const sa = state.editorSA || {};
  let edges = Array.isArray(sa.band_edges)
    ? sa.band_edges.map((x) => Number(x)).filter((x) => Number.isFinite(x))
    : [];
  if (!edges.length) edges = DEFAULT_BAND_EDGES.slice();
  edges = edges
    .map((x) => Math.max(0.001, Math.min(0.999, x)))
    .sort((a, b) => a - b);
  for (let i = 1; i < edges.length; i++) {
    if (edges[i] <= edges[i - 1]) edges[i] = Math.min(0.999, edges[i - 1] + 0.001);
  }
  let names = Array.isArray(sa.band_names) ? sa.band_names.map((x) => String(x)) : [];
  if (names.length !== edges.length + 1 || names.some((x) => !x.trim())) {
    names = DEFAULT_BAND_NAMES.slice(0, edges.length + 1);
  }
  state.editorSA.band_edges = edges;
  state.editorSA.band_names = names;
  return { edges, names };
}

function bandLabel(name) {
  const value = String(name || "");
  return value.toLowerCase() === "medium" ? "mid / medium" : value;
}

function bandDotClass(name) {
  const value = String(name || "").toLowerCase();
  if (value === "low") return "low";
  if (value === "medium" || value === "mid") return "medium";
  if (value === "high") return "high";
  if (value === "critical") return "critical";
  return "medium";
}

function setBandEdge(index, rawValue) {
  const { edges } = normalizedScoreBandConfig();
  const minGap = 0.001;
  const min = index > 0 ? edges[index - 1] + minGap : minGap;
  const max = index < edges.length - 1 ? edges[index + 1] - minGap : 1 - minGap;
  let value = Number(rawValue);
  if (!Number.isFinite(value)) value = edges[index];
  state.editorSA.band_edges[index] = Math.max(min, Math.min(max, value));
  renderScoreBands();
}

function renderScoreBands() {
  const host = $("scoreBandsPanel");
  const { edges, names } = normalizedScoreBandConfig();
  const lowName = names[0] || "low";
  const rows = edges
    .map((edge, idx) => {
      const name = names[idx + 1] || `band ${idx + 2}`;
      return `<div class="band-row" data-edge-idx="${idx}">
        <label class="band-chip"><span class="band-dot ${bandDotClass(name)}"></span>${escapeHtml(bandLabel(name))} starts at</label>
        <input type="range" min="0.01" max="0.99" step="0.01" data-role="band-slider" value="${edge}" />
        <input type="number" min="0.01" max="0.99" step="0.01" data-role="band-num" class="norm-num-in" value="${edge.toFixed(2)}" />
      </div>`;
    })
    .join("");
  host.innerHTML = `<strong>Score band thresholds</strong>
    <div class="band-editor">
      <h3>Risk band handles</h3>
      <div class="band-row low-band">
        <span class="band-chip"><span class="band-dot ${bandDotClass(lowName)}"></span>${escapeHtml(bandLabel(lowName))}: score &lt; ${edges[0].toFixed(2)}</span>
      </div>
      ${rows}
      <div class="muted" style="font-size:0.72rem;margin-top:0.2rem;">
        Thresholds must stay in ascending order between 0 and 1.
      </div>
    </div>`;
  host.querySelectorAll(".band-row[data-edge-idx]").forEach((row) => {
    const idx = Number(row.getAttribute("data-edge-idx"));
    const slider = row.querySelector('[data-role="band-slider"]');
    const num = row.querySelector('[data-role="band-num"]');
    slider.addEventListener("input", () => setBandEdge(idx, slider.value));
    num.addEventListener("change", () => setBandEdge(idx, num.value));
  });
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
    ["Project Path", project.path_display || project.path],
    ["Granularity", cfg.granularity],
    ["Decay Half-life", cfg.decay_half_life],
    ["Similarity Enabled", cfg.similarity_enabled],
    [
      "Dashboard default_target",
      dashboard.default_target_display || dashboard.default_target,
    ],
    ["Version", cfg.version],
  ];
  meta.innerHTML = lines
    .map(([k, v]) => `<div><strong>${k}</strong>: ${pretty(v)}</div>`)
    .join("");
}

let normResizeTimer = null;
function scheduleNormChartResize() {
  if (normResizeTimer) clearTimeout(normResizeTimer);
  normResizeTimer = setTimeout(() => {
    normResizeTimer = null;
    redrawAllNormMetrics();
  }, 150);
}

document.addEventListener("DOMContentLoaded", async () => {
  bindNormDragGlobal();
  window.addEventListener("resize", scheduleNormChartResize);
  const saveBtn = $("configSaveBtn");
  if (saveBtn) saveBtn.addEventListener("click", saveConfigPatch);
  const refreshBtn = $("configRefreshDataBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", async () => {
      $("configSaveStatus").textContent = "";
      await refreshDistributionsOnly();
    });
  }
  await loadConfig();
});
