"""Human-readable score narratives from block risk subscores.

Used by CLI, MCP ``analyze``, and the dashboard so wording stays consistent.
Template copy lives here only — surfaces call :func:`explain_score` /
:func:`build_score_explanation` instead of embedding duplicate prose in JS.
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


def score_driver_from_subscores(subscores: dict[str, float]) -> str:
    """Short driver label for the largest burden key (e.g. ``\"complexity\"``)."""
    if not subscores:
        return ""
    best_key = max(subscores.items(), key=lambda kv: kv[1])[0]
    return BURDEN_TO_DRIVER.get(str(best_key), str(best_key).removesuffix("_burden"))


def build_score_explanation(stat: Statistic) -> list[dict[str, Any]]:
    """Ranked burden breakdown with raw metrics for tooltips and JSON.

    Each item is ``{\"driver\", \"burden\", \"raw\"}`` where *driver* is a short
    stable key (``complexity``, ``churn``, …).
    """
    subs = stat.score_subscores
    if not subs:
        return []
    ordered = sorted(subs.items(), key=lambda kv: float(kv[1]), reverse=True)
    out: list[dict[str, Any]] = []
    for key, burden in ordered:
        bkey = str(key)
        driver = BURDEN_TO_DRIVER.get(bkey, bkey.removesuffix("_burden"))
        raw = _raw_snippet_for_burden(bkey, stat)
        out.append(
            {
                "driver": driver,
                "burden": round(float(burden), 4),
                "raw": raw,
            }
        )
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
) -> str:
    """Multi-line narrative for CLI, MCP rows, and dashboard detail API."""
    expl = build_score_explanation(stat)
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
        phrase = _format_raw_phrase(driver, item.get("raw") or {})
        if phrase:
            lines.append(f"{label:<18} {label_d} ({burden:.2f}) — {phrase}")
        else:
            lines.append(f"{label:<18} {label_d} ({burden:.2f})")
    rec: str | None = recommended_action
    if not rec and band_l in ("high", "critical"):
        rec = "Human review"
    if rec:
        lines.append(f"Recommended action: {rec}")
    return "\n".join(lines)
