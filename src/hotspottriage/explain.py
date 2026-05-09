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

from typing import Any

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

    Each item includes ``driver``, ``burden``, ``raw`` (raw counters for
    debugging). When :attr:`Statistic.score_norm_inputs` is set, a
    ``normalized`` dict holds the ``[0, 1]`` inputs that feed the burden (same as
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
        raw = _raw_snippet_for_burden(bkey, stat)
        item: dict[str, Any] = {
            "driver": driver,
            "burden": round(burden_f, 4),
            "raw": raw,
        }
        if stat.score_norm_inputs and bkey in stat.score_norm_inputs:
            item["normalized"] = dict(stat.score_norm_inputs[bkey])
        if w is not None:
            item["final_weight"] = round(w, 4)
            item["score_contribution"] = round(contribution, 4)
        out.append(item)
    return out


def _raw_snippet_for_burden(burden_key: str, stat: Statistic) -> dict[str, Any]:
    if burden_key == "complexity_burden":
        return {
            "cyclomatic": stat.cyclomatic,
            "halstead": stat.halstead,
            "normalized_sloc": round(float(stat.normalized_sloc), 4),
        }
    if burden_key == "maintainability_burden":
        return {"maintainability": stat.maintainability}
    if burden_key == "churn_burden":
        return {
            "churn": stat.churn,
            "decayed_churn": round(float(stat.decayed_churn), 4),
            "churn_per_sloc": round(float(stat.churn_per_sloc), 4),
            "decayed_churn_per_sloc": round(float(stat.decayed_churn_per_sloc), 4),
        }
    if burden_key == "smell_burden":
        return {
            "smell_count": stat.smell_count,
            "smell_severity": round(float(stat.smell_severity), 4),
        }
    if burden_key == "similarity_burden":
        return {
            "similarity_score": round(float(stat.similarity_score), 4),
            "match_count": stat.match_count,
        }
    return {}


def _driver_label(driver: str) -> str:
    if driver == "smells":
        return "Smells"
    return driver.capitalize()


def _format_norm_phrase(norms: dict[str, float]) -> str:
    if not norms:
        return ""
    return ", ".join(f"n_{k}={float(v):.4f}" for k, v in sorted(norms.items()))


def _format_raw_phrase(driver: str, raw: dict[str, Any]) -> str:
    if not raw:
        return ""
    if driver == "complexity":
        parts = [
            f"cyclomatic={raw['cyclomatic']}",
            f"halstead={raw['halstead']}",
        ]
        if "normalized_sloc" in raw:
            parts.append(f"normalized_sloc={raw['normalized_sloc']}")
        return ", ".join(parts)
    if driver == "maintainability":
        return f"maintainability_index={raw['maintainability']}"
    if driver == "churn":
        return (
            f"churn={raw['churn']}, decayed_churn={raw['decayed_churn']}, "
            f"churn_per_sloc={raw['churn_per_sloc']}"
        )
    if driver == "smells":
        return (
            f"smell_count={raw['smell_count']}, "
            f"smell_severity={raw['smell_severity']}"
        )
    if driver == "similarity":
        return (
            f"similarity_score={raw['similarity_score']}, "
            f"match_count={raw['match_count']}"
        )
    return ", ".join(f"{k}={v}" for k, v in sorted(raw.items()))


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
) -> str:
    """Multi-line narrative for CLI, MCP rows, and dashboard detail API."""
    fw = _resolve_final_weights(stat, final_weights)
    expl = build_score_explanation(stat, final_weights=fw)
    if not expl:
        return ""
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
            phrase = _format_raw_phrase(driver, item.get("raw") or {})
        if "score_contribution" in item and "final_weight" in item:
            c = float(item["score_contribution"])
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
