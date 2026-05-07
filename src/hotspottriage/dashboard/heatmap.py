"""Heatmap HTML fragment builder for dashboard block results."""
from __future__ import annotations

from html import escape
import json
from typing import Any

_MODULE_LABEL = "<module>"
_SCORE_NORM_METRICS = (
    "norm_cyclomatic",
    "norm_halstead",
    "norm_normalized_sloc",
    "norm_maintainability",
    "norm_churn",
    "norm_churn_per_sloc",
    "norm_decayed_churn",
    "norm_decayed_churn_per_sloc",
    "norm_smell_count",
    "norm_similarity_score",
    "norm_match_count",
)

_SCORE_COLORS = (
    (0.29, "#4ade80"),
    (0.59, "#facc15"),
    (0.79, "#fb923c"),
    (1.0, "#f87171"),
)


def _to_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _format_number(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _score_color(score: float) -> str:
    for threshold, color in _SCORE_COLORS:
        if score <= threshold:
            return color
    return _SCORE_COLORS[-1][1]


def _split_path_symbol(path_value: str) -> tuple[str, str]:
    if "::" not in path_value:
        return path_value, ""
    file_path, symbol = path_value.split("::", 1)
    return file_path, symbol


def _split_class_method(symbol: str) -> tuple[str, str]:
    if not symbol:
        return _MODULE_LABEL, ""
    if "." not in symbol:
        return _MODULE_LABEL, symbol
    class_name, method_name = symbol.rsplit(".", 1)
    return class_name or _MODULE_LABEL, method_name


def _row_metrics(row: dict[str, Any], norm_keys: list[str]) -> dict[str, float]:
    metrics: dict[str, float] = {"score": _to_float(row.get("score", 0.0))}
    for key in norm_keys:
        metrics[key] = _to_float(row.get(key, 0.0))
    return metrics


def _metric_cell(metric_key: str, row: dict[str, Any], value: float) -> str:
    color = _score_color(value)
    raw_key = metric_key.removeprefix("norm_")
    raw_value = row.get(raw_key)
    if raw_value is None:
        title = f"{metric_key}: norm={value:.3f}"
    else:
        title = f"{raw_key}: {_format_number(raw_value)} -> norm={value:.3f}"
    return (
        '<td class="heatmap-cell" '
        f'style="background:{color}" title="{escape(title)}">'
        f"{value:.3f}</td>"
    )


def _score_cell(score: float, band: str) -> str:
    color = _score_color(score)
    percent = round(score * 100)
    return (
        '<td class="heatmap-score" '
        f'title="score={score:.3f} ({escape(band or "n/a")})">'
        '<div class="heatmap-score-bar">'
        f'<span class="heatmap-score-fill" style="width:{percent}%;background:{color}"></span>'
        f"<span>{score:.3f}</span>"
        "</div></td>"
    )


def _detail_attr(row: dict[str, Any], file_path: str, class_name: str, symbol: str) -> str:
    detail = {
        "path": file_path,
        "symbol": symbol,
        "class": class_name,
        "score": row.get("score"),
        "score_band": row.get("score_band"),
        "smells": row.get("smells"),
        "score_subscores": row.get("score_subscores"),
    }
    return escape(json.dumps(detail, separators=(",", ":")))


def _placeholder_fragment() -> str:
    return (
        '<div class="heatmap">'
        '<div class="heatmap-empty">No results yet</div>'
        "</div>"
    )


def build_heatmap_fragment(results: list[dict[str, Any]]) -> str:
    """Build a pre-rendered heatmap fragment for dashboard injection."""
    if not isinstance(results, list):
        raise ValueError("results must be a list of dict rows")
    if not results:
        return _placeholder_fragment()

    method_rows = [row for row in results if isinstance(row, dict) and "::" in str(row.get("path", ""))]
    if not method_rows:
        return _placeholder_fragment()

    present_norm_keys = {
        key
        for row in method_rows
        for key in row.keys()
        if key.startswith("norm_")
    }
    norm_keys = [k for k in _SCORE_NORM_METRICS if k in present_norm_keys]

    grouped: dict[str, dict[str, Any]] = {}
    for row in method_rows:
        file_path, symbol = _split_path_symbol(str(row.get("path", "")))
        class_name, method_name = _split_class_method(symbol)
        if not file_path or not method_name:
            continue
        file_entry = grouped.setdefault(
            file_path,
            {"max_score": 0.0, "classes": {}, "rows": []},
        )
        class_entry = file_entry["classes"].setdefault(
            class_name,
            {"max_score": 0.0, "rows": []},
        )
        score = _to_float(row.get("score", 0.0))
        file_entry["max_score"] = max(file_entry["max_score"], score)
        class_entry["max_score"] = max(class_entry["max_score"], score)
        class_entry["rows"].append(row)

    files_sorted = sorted(
        grouped.items(),
        key=lambda item: item[1]["max_score"],
        reverse=True,
    )

    columns_html = "".join(
        f'<th data-sort-key="{escape(key)}">{escape(key)}</th>'
        for key in norm_keys
    )

    tbody_rows: list[str] = []
    visible_files = 10
    row_idx = 0

    for file_index, (file_path, file_entry) in enumerate(files_sorted):
        file_id = f"f-{file_index}"
        file_expanded = file_index < visible_files
        file_score = _to_float(file_entry["max_score"])
        file_band = "critical" if file_score >= 0.8 else "high" if file_score >= 0.6 else "normal"
        file_metrics = {"score": file_score}
        file_metrics.update({key: 0.0 for key in norm_keys})

        class_entries = sorted(
            file_entry["classes"].items(),
            key=lambda item: item[1]["max_score"],
            reverse=True,
        )

        for key in norm_keys:
            best_value = 0.0
            for _, class_entry in class_entries:
                class_best = max((_to_float(r.get(key, 0.0)) for r in class_entry["rows"]), default=0.0)
                best_value = max(best_value, class_best)
            file_metrics[key] = best_value

        file_cells = "".join(_metric_cell(key, {}, file_metrics[key]) for key in norm_keys)
        file_score_cell = _score_cell(file_score, file_band)
        file_toggle = "v" if file_expanded else ">"
        file_row = (
            f'<tr class="heatmap-row file-row" data-row-id="{file_id}" data-kind="file" '
            f'data-parent="" data-expanded="{str(file_expanded).lower()}" '
            f'data-score="{file_score:.6f}" data-score-band="{file_band}">'
            '<td class="heatmap-name">'
            f'<button class="heatmap-toggle" type="button">{file_toggle}</button>'
            f'<span class="heatmap-label">{escape(file_path)}</span>'
            "</td>"
            f"{file_cells}{file_score_cell}</tr>"
        )
        tbody_rows.append(file_row)
        row_idx += 1

        for class_idx, (class_name, class_entry) in enumerate(class_entries):
            class_id = f"{file_id}-c-{class_idx}"
            class_expanded = file_expanded and class_idx < 4
            class_score = _to_float(class_entry["max_score"])
            class_band = "critical" if class_score >= 0.8 else "high" if class_score >= 0.6 else "normal"
            class_hidden = "" if file_expanded else "heatmap-hidden"
            class_metrics = {"score": class_score}
            class_metrics.update(
                {key: max((_to_float(r.get(key, 0.0)) for r in class_entry["rows"]), default=0.0) for key in norm_keys}
            )
            class_cells = "".join(_metric_cell(key, {}, class_metrics[key]) for key in norm_keys)
            class_score_cell = _score_cell(class_score, class_band)
            class_toggle = "v" if class_expanded else ">"
            class_row = (
                f'<tr class="heatmap-row class-row {class_hidden}" data-row-id="{class_id}" data-kind="class" '
                f'data-parent="{file_id}" data-expanded="{str(class_expanded).lower()}" '
                f'data-score="{class_score:.6f}" data-score-band="{class_band}">'
                '<td class="heatmap-name heatmap-indent-1">'
                f'<button class="heatmap-toggle" type="button">{class_toggle}</button>'
                f'<span class="heatmap-label">{escape(class_name)}</span>'
                "</td>"
                f"{class_cells}{class_score_cell}</tr>"
            )
            tbody_rows.append(class_row)
            row_idx += 1

            method_rows_sorted = sorted(
                class_entry["rows"],
                key=lambda row: _to_float(row.get("score", 0.0)),
                reverse=True,
            )
            for method_row in method_rows_sorted:
                _, symbol = _split_path_symbol(str(method_row.get("path", "")))
                _, method_name = _split_class_method(symbol)
                method_score = _to_float(method_row.get("score", 0.0))
                method_band = str(method_row.get("score_band", ""))
                method_metrics = _row_metrics(method_row, norm_keys)
                hidden = "" if class_expanded else "heatmap-hidden"
                metric_cells = "".join(
                    _metric_cell(key, method_row, method_metrics[key]) for key in norm_keys
                )
                score_cell = _score_cell(method_score, method_band)
                detail = _detail_attr(method_row, file_path, class_name, symbol)
                method_id = f"m-{row_idx}"
                method_row_html = (
                    f'<tr class="heatmap-row method-row {hidden}" data-row-id="{method_id}" data-kind="method" '
                    f'data-parent="{class_id}" data-expanded="false" data-score="{method_score:.6f}" '
                    f'data-score-band="{escape(method_band)}" data-detail="{detail}" '
                    + " ".join(f'data-{k.replace("_", "-")}="{method_metrics[k]:.6f}"' for k in method_metrics)
                    + ">"
                    '<td class="heatmap-name heatmap-indent-2">'
                    '<span class="heatmap-toggle-placeholder"></span>'
                    f'<span class="heatmap-label">{escape(method_name)}</span>'
                    "</td>"
                    f"{metric_cells}{score_cell}</tr>"
                )
                tbody_rows.append(method_row_html)
                row_idx += 1

    table_html = (
        '<div class="heatmap" data-default-sort="score">'
        '<div class="heatmap-toolbar">'
        '<button class="heatmap-filter is-active" type="button" data-filter="all">All</button>'
        '<button class="heatmap-filter" type="button" data-filter="high">High</button>'
        '<button class="heatmap-filter" type="button" data-filter="critical">Critical</button>'
        "</div>"
        '<table class="heatmap-table"><thead><tr><th data-sort-key="name">Path</th>'
        f"{columns_html}"
        '<th data-sort-key="score">SCORE</th></tr></thead>'
        f'<tbody>{"".join(tbody_rows)}</tbody></table>'
        '<aside class="heatmap-drawer" hidden>'
        '<h3>Detail</h3><pre class="heatmap-drawer-body">Click a row for details.</pre>'
        "</aside>"
        "</div>"
    )
    return table_html

