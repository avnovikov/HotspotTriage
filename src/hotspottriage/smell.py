"""Code-smell detection using a thin Pylint JSON wrapper.

The public API is `compute_smells(path)`, which runs Pylint with a small,
explicit set of smell-oriented rules and returns normalized smell records.
"""
from __future__ import annotations

import json
import subprocess
import token
import tokenize
from io import StringIO
from pathlib import Path
from typing import Any

from radon.raw import analyze as raw_analyze

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


def _compute_pylint_smells(path: Path, thresholds: dict[str, int]) -> list[dict[str, Any]]:
    """Return smell findings emitted by Pylint for one file."""
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

    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
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
    out = _compute_pylint_smells(path, thresholds)
    out.extend(_compute_comment_smells(path, thresholds))
    return out
