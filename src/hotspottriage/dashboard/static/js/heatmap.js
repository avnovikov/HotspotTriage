// Heatmap screen functions

function heatmapBarBandClass(band) {
  const b = String(band || "").toLowerCase();
  if (b === "low") return "band-low";
  if (b === "medium") return "band-medium";
  if (b === "high") return "band-high";
  if (b === "critical") return "band-critical";
  return "";
}

function heatColor(pct) {
  const p = Math.max(0, Math.min(1, Number(pct) || 0));
  if (p <= 0.33) return `rgba(34,197,94,${0.16 + p * 0.30})`;
  if (p <= 0.66) return `rgba(234,179,8,${0.20 + (p - 0.33) * 0.36})`;
  if (p <= 0.85) return `rgba(249,115,22,${0.22 + (p - 0.66) * 0.58})`;
  return `rgba(239,68,68,${0.35 + (p - 0.85) * 2.0})`;
}

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

function applyHeatmapPresentationFilter(rows) {
  const el = $("heatmapViewFilterInput");
  const query = el ? el.value.trim().toLowerCase() : "";
  if (!query) return rows;
  return rows.filter((row) => {
    const pathValue = String(row.file || "").toLowerCase();
    const functionValue = String(row.method || "").toLowerCase();
    return pathValue.includes(query) || functionValue.includes(query);
  });
}

function renderHeatmapPanel() {
  const panel = $("heatmapPanel");
  const status = $("heatmapStatus");
  const rows = applyHeatmapPresentationFilter(state.heatmapRows);
  status.textContent = `${rows.length} row(s)`;
  if (!rows.length) {
    panel.className = "muted";
    panel.textContent = state.heatmapRows.length
      ? "No heatmap rows match the current filter."
      : "No heatmap rows yet.";
    return;
  }
  const cols = state.heatmapColumns;
  const maxima = state.heatmapColumnMaxima;
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
  <td class="heatmap-file-col" title="${escapeAttr(r.file || "")}"><span class="heatmap-file-label">${escapeHtml(truncateLeftLabelToWidth(r.file || ""))}</span></td>
  <td class="heatmap-method-col" title="${escapeAttr(r.method || "")}"><span class="heatmap-method">${escapeHtml(r.method || "")}</span></td>
  ${cells}
  <td>${escapeHtml(r.score_band || "")}</td>
</tr>`;
    })
    .join("");
  panel.className = "";
  panel.innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

async function refreshHeatmap() {
  const panel = $("heatmapPanel");
  const status = $("heatmapStatus");
  let lim = Number($("heatmapLimitInput").value);
  if (!Number.isFinite(lim) || lim < 1) lim = 500;
  if (lim > 500) lim = 500;
  $("heatmapLimitInput").value = String(lim);
  status.textContent = "Loading\u2026";
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
    state.heatmapRows = rows;
    state.heatmapColumns = cols;
    state.heatmapColumnMaxima = maxima;
    renderHeatmapPanel();
  } catch (e) {
    status.textContent = String(e);
  }
}

async function updateHeatmapData() {
  await generateCache();
  await refreshHeatmap();
}

document.addEventListener("DOMContentLoaded", async () => {
  const updateBtn = $("heatmapUpdateBtn");
  if (updateBtn) updateBtn.addEventListener("click", updateHeatmapData);
  const filterInput = $("heatmapViewFilterInput");
  if (filterInput) filterInput.addEventListener("input", renderHeatmapPanel);
  await syncHeatmapRepoDisplay();
  await refreshHeatmap();
});
