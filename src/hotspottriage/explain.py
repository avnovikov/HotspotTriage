"""Human-readable score narratives from block risk subscores.

Used by CLI, MCP ``analyze``, and the dashboard so wording stays consistent.
Template copy lives here only — surfaces call :func:`explain_score` /
:func:`build_score_explanation` instead of embedding duplicate prose in JS.

When ``final_weights`` (or :attr:`Statistic.score_final_weights`) is present,
ordering and ``score_driver`` follow **score contributions**
(``final_weight × burden``), matching :func:`hotspottriage.score.compute_score`.

When :attr:`Statistic.score_norm_inputs` is present, narrative suffix lines use
**only** those normalized ``[0, 1]`` metrics (the same values folded into each
burden before ``final_weights``), not raw counters.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from hotspottriage.statistic_row import Statistic

BURDEN_TO_DRIVER: dict[str, str] = {
    "complexity_burden": "complexity",
    "maintainability_burden": "maintainability",
    "churn_burden": "churn",
    "smell_burden": "smells",
    "similarity_burden": "similarity",
}

# Tie-break when contributions or burdens are equal (aligns with score.py keys).
_BURDEN_TIE_ORDER = (
    "complexity_burden",
    "churn_burden",
    "maintainability_burden",
    "smell_burden",
    "similarity_burden",
)
_BURDEN_TIE_INDEX = {k: i for i, k in enumerate(_BURDEN_TIE_ORDER)}

# ``explain_score(..., contribution_detail="score_only")`` (heatmap): skip lines
# whose contribution (or unweighted burden) is below this threshold.
_HEATMAP_SCORE_DISPLAY_FLOOR = 0.05


def _heatmap_line_metric(item: dict[str, Any]) -> float:
    """Per-line sort/filter value: weighted contribution, else raw burden."""
    if "score_contribution" in item and "final_weight" in item:
        return float(item["score_contribution"])
    return float(item["burden"])


def _resolve_final_weights(
    stat: Statistic,
    final_weights: dict[str, float] | None,
) -> dict[str, float] | None:
    if final_weights is not None:
        return final_weights
    return stat.score_final_weights


def score_driver_from_subscores(
    subscores: dict[str, float],
    *,
    final_weights: dict[str, float] | None = None,
) -> str:
    """Short driver label: largest burden, or largest score contribution when weighted."""
    if not subscores:
        return ""
    if final_weights:
        def contribution(k: str) -> float:
            return float(subscores[k]) * float(final_weights.get(str(k), 0.0))

        best_key = max(
            subscores.keys(),
            key=lambda k: (contribution(str(k)), -_BURDEN_TIE_INDEX.get(str(k), 99)),
        )
    else:
        best_key = max(
            subscores.items(),
            key=lambda kv: (float(kv[1]), -_BURDEN_TIE_INDEX.get(str(kv[0]), 99)),
        )[0]
    return BURDEN_TO_DRIVER.get(str(best_key), str(best_key).removesuffix("_burden"))


def build_score_explanation(
    stat: Statistic,
    *,
    final_weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Ranked burden breakdown for tooltips and JSON.

    Each item includes ``driver``, ``burden``, and when
    :attr:`Statistic.score_norm_inputs` is set, a ``normalized`` dict with the
    ``[0, 1]`` inputs that feed the burden (same as
    :func:`hotspottriage.score.compute_score`). When ``final_weights`` is set
    (or ``stat.score_final_weights``), items are sorted by descending
    ``score_contribution`` (= ``final_weight × burden``) and include
    ``final_weight`` and ``score_contribution`` fields.
    """
    subs = stat.score_subscores
    if not subs:
        return []
    fw = _resolve_final_weights(stat, final_weights)
    rows: list[tuple[str, float, float | None, float]] = []
    for key, burden in subs.items():
        bkey = str(key)
        burden_f = float(burden)
        if fw and bkey in fw:
            w = float(fw[bkey])
            rows.append((bkey, burden_f, w, w * burden_f))
        else:
            rows.append((bkey, burden_f, None, burden_f))
    rows.sort(
        key=lambda t: (-t[3], _BURDEN_TIE_INDEX.get(t[0], 99)),
    )
    out: list[dict[str, Any]] = []
    for bkey, burden_f, w, contribution in rows:
        driver = BURDEN_TO_DRIVER.get(bkey, bkey.removesuffix("_burden"))
        item: dict[str, Any] = {
            "driver": driver,
            "burden": round(burden_f, 4),
        }
        if stat.score_norm_inputs and bkey in stat.score_norm_inputs:
            item["normalized"] = dict(stat.score_norm_inputs[bkey])
        if w is not None:
            item["final_weight"] = round(w, 4)
            item["score_contribution"] = round(contribution, 4)
        out.append(item)
    return out


def sanitize_score_explanation_entries(
    items: Iterable[Any],
) -> list[dict[str, Any]]:
    """Copy explanation dicts and drop legacy ``raw`` keys from persisted rows."""
    out: list[dict[str, Any]] = []
    for x in items:
        if not isinstance(x, dict):
            continue
        d = dict(x)
        d.pop("raw", None)
        out.append(d)
    return out


def _driver_label(driver: str) -> str:
    if driver == "smells":
        return "Smells"
    return driver.capitalize()


def _format_norm_phrase(norms: dict[str, float]) -> str:
    if not norms:
        return ""
    return ", ".join(f"n_{k}={float(v):.4f}" for k, v in sorted(norms.items()))


def _rank_label(index: int, n: int) -> str:
    if n <= 1:
        return "Primary driver:"
    if index == n - 1:
        return "Low risk:"
    if index == 0:
        return "Primary driver:"
    if index == 1:
        return "Secondary driver:"
    return "Contributing:"


def explain_score(
    stat: Statistic,
    *,
    recommended_action: str | None = None,
    final_weights: dict[str, float] | None = None,
    contribution_detail: Literal["full", "score_only"] = "full",
) -> str:
    """Multi-line narrative for CLI, MCP rows, and dashboard detail API.

    ``contribution_detail``:
    - ``full`` (default): per-driver line shows
      ``score contribution = final_weight × burden`` when weights apply.
    - ``score_only``: same ordering, but each weighted line shows only the
      numeric contribution as ``(score …)`` (heatmap tooltips). Drivers whose
      contribution (or unweighted burden) is strictly below ``0.05`` are
      omitted; rank labels apply only to the remaining lines.
    """
    fw = _resolve_final_weights(stat, final_weights)
    expl_all = build_score_explanation(stat, final_weights=fw)
    if not expl_all:
        return ""
    expl = expl_all
    if contribution_detail == "score_only":
        expl = [
            it
            for it in expl_all
            if _heatmap_line_metric(it) >= _HEATMAP_SCORE_DISPLAY_FLOOR
        ]
    band_raw = str(stat.score_band).strip()
    band_l = band_raw.lower()
    if band_l in ("", "n/a"):
        lines = [f"BLOCK — {stat.path}"]
    else:
        icon = "⚠️" if band_l in ("high", "critical") else "ℹ️"
        lines = [f"{icon} {band_raw.upper()} RISK — {stat.path}"]
    n = len(expl)
    for i, item in enumerate(expl):
        label = _rank_label(i, n)
        driver = item["driver"]
        label_d = _driver_label(driver)
        burden = float(item["burden"])
        norms = item.get("normalized")
        if isinstance(norms, dict) and norms:
            phrase = _format_norm_phrase({str(k): float(v) for k, v in norms.items()})
        else:
            phrase = ""
        if "score_contribution" in item and "final_weight" in item:
            c = float(item["score_contribution"])
            if contribution_detail == "score_only":
                core = f"{label:<18} {label_d} (score {c:.2f})"
            else:
                w = float(item["final_weight"])
                core = (
                    f"{label:<18} {label_d} (score contribution {c:.2f} = "
                    f"final_weight {w:.2f} × burden {burden:.2f})"
                )
        else:
            core = f"{label:<18} {label_d} ({burden:.2f})"
        if phrase:
            lines.append(f"{core} — {phrase}")
        else:
            lines.append(core)
    rec: str | None = recommended_action
    if not rec and band_l in ("high", "critical"):
        rec = "Human review"
    if rec:
        lines.append(f"Recommended action: {rec}")
    return "\n".join(lines)


_METRIC_PLAIN: dict[str, str] = {
    "cyclomatic": "cyclomatic complexity",
    "halstead": "Halstead volume",
    "normalized_sloc": "normalized SLOC",
    "maintainability": "maintainability index",
    "churn": "churn",
    "churn_per_sloc": "churn per line",
    "decayed_churn": "decayed churn",
    "decayed_churn_per_sloc": "decayed churn per line",
    "smell_count": "smell count",
    "smell_severity": "smell severity",
    "similarity_score": "similarity score",
    "match_count": "similarity matches",
}


def _compact_cause_phrase(norms: dict[str, float] | None) -> str:
    """Short clause naming the strongest normalized inputs for the primary driver."""
    if not norms:
        return ""
    ranked = sorted(norms.items(), key=lambda kv: -float(kv[1]))
    parts: list[str] = []
    for k, v in ranked:
        vf = float(v)
        if vf < 0.12 and parts:
            continue
        label = _METRIC_PLAIN.get(str(k), str(k).replace("_", " "))
        if vf >= 0.62:
            parts.append(f"high {label}")
        elif vf >= 0.35:
            parts.append(f"elevated {label}")
        elif not parts:
            parts.append(f"{label} ({vf:.2f})")
        if len(parts) >= 2:
            break
    if not parts and ranked:
        k, v = ranked[0]
        parts.append(f"{_METRIC_PLAIN.get(str(k), str(k))} ({float(v):.2f})")
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} and {parts[1]}"


def compact_agent_rationale(
    stat: Statistic,
    *,
    final_weights: dict[str, float] | None = None,
) -> str:
    """One-line (optionally two) natural-language summary for MCP compact rows.

    Names the primary (and optional secondary) risk driver in plain language,
    with a short cause phrase from the same normalized inputs as
    :func:`build_score_explanation` (aligned with heatmap ``score_only`` tone).
    """
    if not stat.score_subscores:
        return ""
    fw = _resolve_final_weights(stat, final_weights)
    expl = build_score_explanation(stat, final_weights=fw)
    if not expl:
        return ""
    primary = expl[0]
    driver = str(primary["driver"]).lower()
    norms_raw = primary.get("normalized")
    norms: dict[str, float] | None = None
    if isinstance(norms_raw, dict):
        norms = {str(k): float(v) for k, v in norms_raw.items()}
    cause = _compact_cause_phrase(norms)
    head = f"Main driver: {driver}"
    if cause:
        head += f" — {cause}"
    head += "."
    parts = [head]
    if len(expl) > 1:
        sec = expl[1]
        if _heatmap_line_metric(sec) >= _HEATMAP_SCORE_DISPLAY_FLOOR:
            parts.append(f"Second: {str(sec['driver']).lower()}.")
    return " ".join(parts)
