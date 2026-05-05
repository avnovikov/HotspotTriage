"""Code-smell detection using a thin Pylint JSON wrapper.

The public API is `compute_smells(path)`, which runs Pylint with a small,
explicit set of smell-oriented rules and returns normalized smell records.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

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


def compute_smells(path: Path) -> list[dict[str, Any]]:
    """Return normalized smell findings for one Python file.

    Output shape:
    - file: file path as reported by Pylint
    - line: 1-indexed line number
    - smell: normalized smell family
    - message: human-readable finding message
    """
    thresholds = _default_thresholds()
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
