"""Code-smell detection using a thin Pylint JSON wrapper.

The public API is `compute_smells(path)`, which runs Pylint with a small,
explicit set of smell-oriented rules and returns normalized smell records.
"""
from __future__ import annotations

import json
import re
import subprocess
import token
import tokenize
from io import StringIO
from pathlib import Path
from typing import Any

from radon.raw import analyze as raw_analyze

from hotspottriage import blocks as _blocks
from hotspottriage import complexity as _complexity
from hotspottriage import config as _config

PYLINT_CODES: tuple[str, ...] = (
    "R0915",  # too-many-statements
    "R0902",  # too-many-instance-attributes
    "R0904",  # too-many-public-methods
    "R0913",  # too-many-arguments
    "R0912",  # too-many-branches
    "R0903",  # too-few-public-methods
    "W0613",  # unused-argument
    "W0611",  # unused-import
    "W0612",  # unused-variable
)

SMELL_BY_CODE: dict[str, str] = {
    "R0915": "long_method",
    "R0902": "large_class",
    "R0904": "large_class",
    "R0913": "long_parameter_list",
    "R0912": "switch_statements",
    "R0903": "lazy_class",
    "W0613": "unused_parameters",
    "W0611": "dead_code",
    "W0612": "dead_code",
}


def _default_thresholds() -> dict[str, int]:
    return {
        "max_statements": int(_config.DEFAULTS["smell_max_statements"]),
        "max_attributes": int(_config.DEFAULTS["smell_max_attributes"]),
        "max_public_methods": int(_config.DEFAULTS["smell_max_public_methods"]),
        "max_args": int(_config.DEFAULTS["smell_max_args"]),
        "max_branches": int(_config.DEFAULTS["smell_max_branches"]),
        "min_public_methods": int(_config.DEFAULTS["smell_min_public_methods"]),
        "max_comment_ratio": float(_config.DEFAULTS["smell_max_comment_ratio"]),
        "max_comment_block_lines": int(_config.DEFAULTS["smell_max_comment_block_lines"]),
        "data_class_min_attributes": int(_config.DEFAULTS["smell_data_class_min_attributes"]),
        "middle_man_max_avg_method_sloc": float(
            _config.DEFAULTS["smell_middle_man_max_avg_method_sloc"]
        ),
        "speculative_generality_min_hits": int(
            _config.DEFAULTS["smell_speculative_generality_min_hits"]
        ),
    }


def _build_pylint_command(path: Path, thresholds: dict[str, int]) -> list[str]:
    return [
        "pylint",
        str(path),
        "--output-format=json",
        "--disable=all",
        f"--enable={','.join(PYLINT_CODES)}",
        f"--max-statements={thresholds['max_statements']}",
        f"--max-attributes={thresholds['max_attributes']}",
        f"--max-public-methods={thresholds['max_public_methods']}",
        f"--max-args={thresholds['max_args']}",
        f"--max-branches={thresholds['max_branches']}",
        f"--min-public-methods={thresholds['min_public_methods']}",
    ]


def _compute_pylint_smells(path: Path, raw_pylint: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return smell findings emitted by Pylint for one file."""
    out: list[dict[str, Any]] = []
    for item in raw_pylint:
        code = str(item.get("message-id", ""))
        smell = SMELL_BY_CODE.get(code)
        if smell is None:
            continue
        out.append(
            {
                "file": str(item.get("path", path)),
                "line": int(item.get("line") or 0),
                "smell": smell,
                "message": str(item.get("message", "")),
            }
        )
    return out


def _run_pylint_raw(path: Path, thresholds: dict[str, int | float]) -> list[dict[str, Any]]:
    """Return raw pylint json objects filtered to dict entries only."""
    cmd = _build_pylint_command(path, thresholds)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise RuntimeError(
            "pylint executable not found; install pylint to enable smell detection"
        ) from e
    raw = proc.stdout.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid pylint JSON output for {path}: {e}") from e
    if not isinstance(data, list):
        raise ValueError(f"unexpected pylint output type for {path}: {type(data).__name__}")
    return [item for item in data if isinstance(item, dict)]


def _parse_attribute_count(message: str) -> int:
    match = re.search(r"\((\d+)/\d+\)", message)
    return int(match.group(1)) if match else 0


def _mean_method_sloc_for_class(src: str, class_name: str) -> float:
    method_slocs: list[int] = []
    for block in _blocks.extract_blocks(src):
        if not block.name.startswith(f"{class_name}."):
            continue
        snippet = _complexity.slice_block(src, block.start, block.end)
        method_slocs.append(int(_complexity.compute_for_source(snippet)["sloc"]))
    if not method_slocs:
        return 0.0
    return sum(method_slocs) / len(method_slocs)


def _compute_approximate_smells(
    path: Path, src: str, raw_pylint: list[dict[str, Any]], thresholds: dict[str, int | float]
) -> list[dict[str, Any]]:
    """Approximate smells from pylint heuristics.

    These signals are heuristic and intentionally include `confidence=approximate`.
    """
    out: list[dict[str, Any]] = []
    by_code: dict[str, list[dict[str, Any]]] = {}
    for item in raw_pylint:
        code = str(item.get("message-id", ""))
        by_code.setdefault(code, []).append(item)

    few_methods_objs = {str(i.get("obj", "")): i for i in by_code.get("R0903", [])}
    min_attrs = int(thresholds["data_class_min_attributes"])
    for item in by_code.get("R0902", []):
        class_name = str(item.get("obj", ""))
        attrs = _parse_attribute_count(str(item.get("message", "")))
        if class_name in few_methods_objs and attrs >= min_attrs:
            out.append(
                {
                    "file": str(item.get("path", path)),
                    "line": int(item.get("line") or 0),
                    "smell": "data_class",
                    "message": (
                        f"Class '{class_name}' has few public methods and {attrs} instance "
                        f"attributes (threshold: {min_attrs})"
                    ),
                    "confidence": "approximate",
                }
            )

    max_avg_sloc = float(thresholds["middle_man_max_avg_method_sloc"])
    for class_name, item in few_methods_objs.items():
        if not class_name:
            continue
        avg_sloc = _mean_method_sloc_for_class(src, class_name)
        if 0 < avg_sloc <= max_avg_sloc:
            out.append(
                {
                    "file": str(item.get("path", path)),
                    "line": int(item.get("line") or 0),
                    "smell": "middle_man",
                    "message": (
                        f"Class '{class_name}' has few public methods and average method "
                        f"SLOC {avg_sloc:.2f} (threshold: {max_avg_sloc:.2f})"
                    ),
                    "confidence": "approximate",
                }
            )

    unused_imports = by_code.get("W0611", [])
    unused_vars = by_code.get("W0612", [])
    min_hits = int(thresholds["speculative_generality_min_hits"])
    if len(unused_imports) >= min_hits and len(unused_vars) >= min_hits:
        for item in [*unused_imports, *unused_vars]:
            out.append(
                {
                    "file": str(item.get("path", path)),
                    "line": int(item.get("line") or 0),
                    "smell": "speculative_generality",
                    "message": (
                        "Unused imports and variables suggest over-generalized, unused "
                        "abstractions"
                    ),
                    "confidence": "approximate",
                }
            )
    return out


def _max_consecutive_comment_block_start(src: str) -> tuple[int, int]:
    """Return (max_run_length, start_line) for consecutive COMMENT token lines."""
    line_numbers: list[int] = []
    for tok in tokenize.generate_tokens(StringIO(src).readline):
        if tok.type == token.COMMENT:
            line_numbers.append(tok.start[0])
    if not line_numbers:
        return (0, 0)

    max_len = 1
    max_start = line_numbers[0]
    cur_len = 1
    cur_start = line_numbers[0]

    for prev, nxt in zip(line_numbers, line_numbers[1:]):
        if nxt == prev + 1:
            cur_len += 1
            continue
        if cur_len > max_len:
            max_len = cur_len
            max_start = cur_start
        cur_len = 1
        cur_start = nxt

    if cur_len > max_len:
        max_len = cur_len
        max_start = cur_start
    return (max_len, max_start)


def _compute_comment_smells(path: Path, thresholds: dict[str, int | float]) -> list[dict[str, Any]]:
    """Return comment-related smell findings computed from source/radon/tokenize."""
    src = path.read_text(encoding="utf-8", errors="replace")
    raw = raw_analyze(src)
    out: list[dict[str, Any]] = []

    sloc = int(raw.sloc)
    comments = int(raw.comments)
    comment_ratio = (comments / sloc) if sloc > 0 else 0.0
    max_ratio = float(thresholds["max_comment_ratio"])
    if comment_ratio > max_ratio:
        out.append(
            {
                "file": str(path),
                "line": 1,
                "smell": "excessive_comments",
                "message": (
                    f"Comment ratio {comment_ratio:.3f} exceeds threshold {max_ratio:.3f} "
                    f"({comments} comments / {sloc} sloc)"
                ),
            }
        )

    max_block, start_line = _max_consecutive_comment_block_start(src)
    max_block_lines = int(thresholds["max_comment_block_lines"])
    if max_block > max_block_lines:
        out.append(
            {
                "file": str(path),
                "line": start_line,
                "smell": "large_comment_block",
                "message": (
                    f"Comment block length {max_block} exceeds threshold {max_block_lines}"
                ),
            }
        )
    return out


def compute_smells(path: Path) -> list[dict[str, Any]]:
    """Return normalized smell findings for one Python file.

    Output shape:
    - file: file path as reported by Pylint
    - line: 1-indexed line number
    - smell: normalized smell family
    - message: human-readable finding message
    """
    thresholds = _default_thresholds()
    src = path.read_text(encoding="utf-8", errors="replace")
    raw_pylint = _run_pylint_raw(path, thresholds)
    out = _compute_pylint_smells(path, raw_pylint)
    out.extend(_compute_approximate_smells(path, src, raw_pylint, thresholds))
    out.extend(_compute_comment_smells(path, thresholds))
    return out
