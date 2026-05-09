// Overview screen: cache actions, logs, stats, health

function updateCacheContext(statusText) {
  const target = $("cacheTargetInput").value.trim() || "n/a";
  const incRaw = $("cacheIncludeInput").value.trim();
  const excRaw = $("cacheExcludeInput").value.trim();
  const incDisp = incRaw ? incRaw : "<default **/*.py>";
  const excDisp = excRaw ? excRaw : "<none>";
  $("cacheContextPanel").textContent =
`Path: ${target}
Cache Status: ${statusText}
Build Parameters: include=${incDisp}, exclude=${excDisp}`;
}

function mirrorCacheInputs() {
  void syncHeatmapRepoDisplay();
}

async function saveCacheContext({ overwrite = true, statusText = null } = {}) {
  const payload = {
    target: repoTargetCanonicalForApi(),
    include: $("cacheIncludeInput").value.trim(),
    exclude: $("cacheExcludeInput").value.trim(),
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

async function normalizeTargetForAction() {
  const normalizePromise = saveCacheContext({
    overwrite: true,
    statusText: "normalizing target",
  });
  const timeoutPromise = new Promise((resolve) => setTimeout(() => resolve(null), 700));
  await Promise.race([normalizePromise, timeoutPromise]);
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
  const targetIds = ["cacheTargetInput"];
  const includeIds = ["cacheIncludeInput"];
  const excludeIds = ["cacheExcludeInput"];
  targetIds.forEach((id) => {
    const el = $(id);
    if (!el) return;
    if ((overwrite || !el.value.trim()) && ctx.last_target) {
      setRepoTargetInputFromServer(
        el,
        String(ctx.last_target),
        String(ctx.last_target_display || ctx.last_target || ""),
      );
    }
  });
  const inc =
    ctx.last_include !== undefined && ctx.last_include !== null
      ? String(ctx.last_include)
      : "";
  const exc =
    ctx.last_exclude !== undefined && ctx.last_exclude !== null
      ? String(ctx.last_exclude)
      : "";
  includeIds.forEach((id) => {
    const el = $(id);
    if (!el) return;
    if (overwrite || !el.value.trim()) {
      el.value = inc;
    }
  });
  excludeIds.forEach((id) => {
    const el = $(id);
    if (!el) return;
    if (overwrite || !el.value.trim()) {
      el.value = exc;
    }
  });
  void syncHeatmapRepoDisplay();
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

async function clearStats() {
  await fetch("/api/stats/clear", { method: "POST" });
  await refreshStats();
}

async function generateCache() {
  const box = $("cacheStatus");
  const bar = $("cacheProgress");
  box.textContent = "Starting cache generation\u2026";
  bar.classList.remove("done", "err");
  bar.style.width = "8%";
  await normalizeTargetForAction();
  const target = repoTargetCanonicalForApi();
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
        include: $("cacheIncludeInput").value.trim(),
        exclude: $("cacheExcludeInput").value.trim(),
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

async function checkCacheStatus() {
  const box = $("cacheStatus");
  const bar = $("cacheProgress");
  box.textContent = "Checking cache\u2026";
  bar.classList.remove("done", "err");
  bar.style.width = "25%";
  await normalizeTargetForAction();
  const target = repoTargetCanonicalForApi();
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
        include: $("cacheIncludeInput").value.trim(),
        exclude: $("cacheExcludeInput").value.trim(),
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
      setRepoTargetInputFromServer(
        $("cacheTargetInput"),
        String(data.target),
        String(data.target_display || data.target || ""),
      );
      mirrorCacheInputs();
    }
    if (data.stale || data.usable === false) {
      const msg = data.message || "Cache is stale or incompatible; regenerate cache.";
      const dirDisp = data.cache_dir_display || data.cache_dir;
      box.textContent = `${msg} size=${data.size_bytes ?? 0} bytes, dir=${dirDisp}`;
      updateCacheContext(`stale (${dirDisp})`);
      bar.classList.remove("done");
      bar.classList.add("err");
      bar.style.width = "100%";
      return;
    }
    if (!data.exists) {
      const dirDisp = data.cache_dir_display || data.cache_dir;
      box.textContent = `No cache yet at ${dirDisp}`;
      updateCacheContext(`missing (${dirDisp})`);
      bar.classList.remove("done");
      bar.classList.add("err");
      bar.style.width = "100%";
      return;
    }
    const dirDisp = data.cache_dir_display || data.cache_dir;
    box.textContent = `Cache exists: entries=${data.entries}, size=${data.size_bytes} bytes, dir=${dirDisp}`;
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

document.addEventListener("DOMContentLoaded", async () => {
  // Cache action buttons
  const checkBtn = $("checkCacheBtn");
  const genBtn = $("generateCacheBtn");
  const saveCtxBtn = $("cacheSaveCtxBtn");
  if (checkBtn) checkBtn.addEventListener("click", () => checkCacheStatus());
  if (genBtn) genBtn.addEventListener("click", () => generateCache());
  if (saveCtxBtn) {
    saveCtxBtn.addEventListener("click", async () => {
      const st = $("cacheSaveCtxStatus");
      st.textContent = "";
      const ctx = await saveCacheContext({ overwrite: true, statusText: "saved" });
      if (ctx) {
        st.textContent = "Saved.";
        setTimeout(() => { st.textContent = ""; }, 2600);
      } else {
        st.textContent = "Save failed.";
      }
    });
  }
  ["cacheIncludeInput", "cacheExcludeInput", "cacheTargetInput"].forEach((id) => {
    const el = $(id);
    if (el) {
      el.addEventListener("input", () => {
        if (id === "cacheTargetInput") {
          el.dataset.htCanonicalTarget = el.value.trim();
        }
        mirrorCacheInputs();
        updateCacheContext("pending");
      });
    }
  });

  // Logs
  const clearLogsBtn = $("clearLogsBtn");
  if (clearLogsBtn) clearLogsBtn.addEventListener("click", clearLogs);
  const pauseBtn = $("pauseLogsBtn");
  if (pauseBtn) {
    pauseBtn.addEventListener("click", () => {
      state.pauseScroll = !state.pauseScroll;
      pauseBtn.textContent = `Pause Scroll: ${state.pauseScroll ? "On" : "Off"}`;
    });
  }

  // Stats
  const clearStatsBtn = $("clearStatsBtn");
  if (clearStatsBtn) clearStatsBtn.addEventListener("click", clearStats);

  // Boot
  await loadConfig();
  await loadCacheContext();
  if ($("cacheTargetInput") && $("cacheTargetInput").value.trim()) {
    void checkCacheStatus();
  }
  await refreshStats();
  connectLogStream();
  setInterval(refreshStats, 5000);
});
