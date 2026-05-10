"""File-level statistics: complexity, churn, smells, product score."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Iterable

from hotspottriage import complexity as _complexity
from hotspottriage.config import DEFAULTS as _DEFAULTS
from hotspottriage.statistic_row import Statistic

from hotspottriage.stats.metrics import decayed_value, ratio
from hotspottriage.stats.scoring import product_score
from hotspottriage.stats.smell_burden import finalize_smell_burden


def _file_metric_dict(
    repo: Path,
    rel: str,
    churn_count: int,
    min_sloc: int,
    age_seconds: int,
    decay_half_life: int | None,
    merged_config: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Compute all raw metrics for one file and return ``(metrics, smell_summary)``."""
    from hotspottriage import smell as _smell

    raw_smells = _smell.compute_smells(repo / rel, merged_config)
    smell_summary = _smell.summarize_smells(raw_smells)

    m: dict[str, Any] = dict(_complexity.compute_all(repo / rel))
    m["churn"] = churn_count
    m["churn_per_sloc"] = ratio(int(m["churn"]), int(m["sloc"]), min_sloc_for_ratio=min_sloc)

    n_smells = len(raw_smells)
    m["smell_count"] = float(n_smells)
    m["smell_severity"] = (
        sum(float(x.get("severity", 0.0)) for x in raw_smells) / max(1, n_smells)
        if raw_smells
        else 0.0
    )

    m["decayed_churn"] = (
        decayed_value(m["churn"], age_seconds, decay_half_life)
        if decay_half_life
        else m["churn"]
    )
    m["decayed_churn_per_sloc"] = ratio(
        m["decayed_churn"], int(m["sloc"]), min_sloc_for_ratio=min_sloc
    )
    m["similarity_score"] = 0.0

    return m, smell_summary


def _statistic_from_file_metrics(
    rel: str,
    m: dict[str, Any],
    smell_summary: dict[str, int],
    score_metrics: list[str],
    smell_weight: float,
) -> Statistic:
    return Statistic(
        path=rel,
        sloc=int(m["sloc"]),
        normalized_sloc=0.0,
        cyclomatic=int(m["cyclomatic"]),
        halstead=int(m["halstead"]),
        maintainability=int(m["maintainability"]),
        churn=int(m["churn"]),
        churn_per_sloc=float(m["churn_per_sloc"]),
        decayed_churn=float(m["decayed_churn"]),
        decayed_churn_per_sloc=float(m["decayed_churn_per_sloc"]),
        smell_count=int(m["smell_count"]),
        smell_severity=float(m["smell_severity"]),
        smell_burden=float(m["smell_burden"]),
        smells=smell_summary,
        similarity_score=0.0,
        similarity_band="n/a",
        match_count=0,
        score=product_score(m, score_metrics, smell_weight=smell_weight),
    )


def build_stats(
    repo: Path,
    files: Iterable[str],
    churn: dict[str, int],
    score_metrics: Iterable[str],
    decay_half_life: int | None = None,
    smell_weight: float = 0.0,
    progress_callback: Callable[[str, int, int], None] | None = None,
    merged_config: dict[str, Any] | None = None,
) -> list[Statistic]:
    from hotspottriage import churn as _churn
    from datetime import datetime

    sm = list(score_metrics)
    files_list = list(files)
    total_files = len(files_list)
    if progress_callback:
        progress_callback("Analyzing files", 0, total_files)

    current_time = int(datetime.now().timestamp())
    timestamps = _churn.get_file_timestamps(repo, files_list)
    cfg = merged_config if merged_config is not None else _DEFAULTS
    min_sloc = int(cfg.get("min_sloc_for_ratio", _DEFAULTS["min_sloc_for_ratio"]))

    pending: list[tuple[str, dict[str, Any], dict[str, int]]] = []
    for idx, rel in enumerate(files_list, start=1):
        age_seconds = current_time - timestamps.get(rel, current_time)
        m, smell_summary = _file_metric_dict(
            repo, rel, churn.get(rel, 0), min_sloc, age_seconds, decay_half_life, merged_config,
        )
        pending.append((rel, m, smell_summary))
        if progress_callback:
            progress_callback(rel, idx, total_files)

    finalize_smell_burden([m for _, m, _ in pending])

    return [
        _statistic_from_file_metrics(rel, m, summary, sm, smell_weight)
        for rel, m, summary in pending
    ]
