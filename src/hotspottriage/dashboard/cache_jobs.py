"""Background cache generation jobs and port binding for the dashboard."""
from __future__ import annotations

import logging
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Protocol

from hotspottriage.dashboard.cache_http import CacheJob, slim_cache_job_result
from hotspottriage.discovery import is_git_url

logger = logging.getLogger(__name__)


class CacheGenerationHost(Protocol):
    """Narrow surface used by :func:`run_cache_generation_job` (avoids importing ``DashboardServer``)."""

    def _analysis_config_overrides(self, *, target: str | None) -> dict[str, Any]:
        """Implementations provide MCP/cache-layer config overrides for a target repo."""
        pass

    def publish_latest_block_metrics(
        self,
        rows: list[dict[str, Any]],
        *,
        analysis_repo: Path | None = None,
    ) -> None:
        """Implementations push scored block rows for heatmap and histograms."""
        pass


def find_free_port(host: str, base: int, *, span: int = 20) -> int:
    """Bind-probe successive TCP ports on *host* (must not be all-interfaces)."""
    normalized = str(host).strip()
    if not normalized or normalized in {"0.0.0.0", "::", "*"}:
        raise ValueError(
            "refusing to probe ports on all network interfaces; "
            "use a specific host such as 127.0.0.1"
        )
    for port in range(base, base + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((normalized, port))
            except OSError:
                continue
            return port
    raise OSError(f"No free port found in range {base}–{base + span - 1}")


def make_cache_job_progress_callback(
    job_id: str,
    jobs: dict[str, CacheJob],
    jobs_lock: threading.Lock,
) -> Callable[[str, int, int], None]:
    def _cache_progress(label: str, done: int, total: int) -> None:
        t = max(int(total), 1)
        d = min(max(int(done), 0), t)
        if label.startswith("Scanning "):
            msg = label
            pct = 26 + int(24 * d / t)
        elif label.startswith("Block churn"):
            msg = f"Block churn (git log -L) {d}/{t}"
            pct = 50 + int(18 * d / t)
        elif label.startswith("Building block rows"):
            msg = "Assembling block rows…" if d == 0 else label
            pct = 70 + int(12 * d / t)
        elif "::" in label:
            msg = label
            pct = 72 + int(14 * d / t)
        elif label.startswith("Indexing "):
            msg = label
            pct = 86 + int(9 * d / t)
        else:
            msg = label
            pct = 40
        with jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                return
            job.message = msg
            job.progress = min(96, max(job.progress, pct))

    return _cache_progress


def run_cache_generation_job(
    job_id: str,
    *,
    target: str,
    filt: str | None,
    score_metrics: str,
    cache_generator_mod: Any,
    jobs: dict[str, CacheJob],
    jobs_lock: threading.Lock,
    host: CacheGenerationHost,
) -> None:
    progress_cb = make_cache_job_progress_callback(job_id, jobs, jobs_lock)
    try:
        with jobs_lock:
            job = jobs.get(job_id)
            if job is not None:
                job.progress = 8
                job.message = "Starting…"
        result = cache_generator_mod.generate_full_cache(
            target=target,
            filter=filt,
            score_metrics=score_metrics,
            verbose=False,
            progress_callback=progress_cb,
            config_overrides=host._analysis_config_overrides(target=target),
        )
        with jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                return
            job.status = "done"
            job.progress = 100
            job.message = "Cache generation complete"
            job.result = slim_cache_job_result(result if isinstance(result, dict) else {})
        block_results = (
            result.get("blocks", {}).get("results", [])
            if isinstance(result, dict)
            else []
        )
        if isinstance(block_results, list) and block_results:
            _ar: Path | None = None
            if not is_git_url(target):
                _tp = Path(target).expanduser().resolve()
                if _tp.is_dir():
                    _ar = _tp
            host.publish_latest_block_metrics(
                [r for r in block_results if isinstance(r, dict)],
                analysis_repo=_ar,
            )
    except Exception as e:
        with jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                return
            job.status = "error"
            job.progress = 100
            job.message = "Cache generation failed"
            job.error = str(e)


def enqueue_cache_generation_job(
    host: CacheGenerationHost,
    *,
    target: str,
    filt: str | None,
    score_metrics: str,
    jobs: dict[str, CacheJob],
    jobs_lock: threading.Lock,
) -> str:
    # Local import avoids import-time cycle with cache_generator / mcp_server consumers.
    from hotspottriage import cache_generator as _cache_generator  # noqa: PLC0415

    job_id = str(uuid.uuid4())
    job = CacheJob(
        job_id=job_id,
        status="running",
        progress=5,
        message=f"Starting cache generation for {target}",
        started_at_monotonic=time.monotonic(),
    )
    with jobs_lock:
        jobs[job_id] = job

    def _thread_main() -> None:
        run_cache_generation_job(
            job_id,
            target=target,
            filt=filt,
            score_metrics=score_metrics,
            cache_generator_mod=_cache_generator,
            jobs=jobs,
            jobs_lock=jobs_lock,
            host=host,
        )

    threading.Thread(
        target=_thread_main,
        daemon=True,
        name=f"cache-job-{job_id[:8]}",
    ).start()
    return job_id
