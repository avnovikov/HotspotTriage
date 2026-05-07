"""Code-smell detection using a thin Pylint JSON wrapper.

The public API is `compute_smells(path)`, which runs Pylint with a small,
explicit set of smell-oriented rules and returns normalized smell records.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import token
import tokenize
from copy import deepcopy
from io import StringIO
from pathlib import Path
from typing import Any, Iterable

from radon.raw import analyze as raw_analyze

from hotspottriage import blocks as _blocks
from hotspottriage import complexity as _complexity
from hotspottriage import config as _config

logger = logging.getLogger(__name__)

# Log once per process when Pylint cannot be run (missing binary / PATH).
_PYLINT_SKIP_WARNED = False

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

# Pylint codes whose primary location is the class line; map to blocks via `scope`.
_CLASS_SCOPED_PYLINT_CODES: frozenset[str] = frozenset({"R0902", "R0903", "R0904"})

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


def _pylint_executable() -> str | None:
    """Resolve ``pylint``: ``PATH``, then same directory as ``sys.executable`` (venv layout).

    Do not ``resolve()`` the interpreter path: venv shims often symlink to a base
    ``python3.x``; resolving would point at the framework ``bin`` where ``pylint``
    is not installed even when ``.venv/bin/pylint`` exists.
    """
    which = shutil.which("pylint")
    if which:
        return which
    candidate = Path(sys.executable).expanduser().parent / "pylint"
    return str(candidate) if candidate.is_file() else None


def _log_pylint_skip_once() -> None:
    global _PYLINT_SKIP_WARNED
    if _PYLINT_SKIP_WARNED:
        return
    _PYLINT_SKIP_WARNED = True
    logger.warning(
        "pylint executable not found; Pylint-backed smells are skipped (radon/comment "
        "heuristics still run). Install pylint or run from the project venv so "
        "`pylint` is on PATH or next to Python."
    )


def _build_pylint_command(
    path: Path, thresholds: dict[str, int | float], pylint_exe: str
) -> list[str]:
    return [
        pylint_exe,
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
        rec: dict[str, Any] = {
            "file": str(item.get("path", path)),
            "line": int(item.get("line") or 0),
            "smell": smell,
            "message": str(item.get("message", "")),
            "pylint_code": code,
        }
        if code in _CLASS_SCOPED_PYLINT_CODES:
            sym = str(item.get("obj", "")).strip()
            if sym:
                rec["scope"] = {"kind": "class", "symbol": sym}
        out.append(rec)
    return out


def _run_pylint_raw(path: Path, thresholds: dict[str, int | float]) -> list[dict[str, Any]]:
    """Return raw pylint json objects filtered to dict entries only."""
    exe = _pylint_executable()
    if exe is None:
        _log_pylint_skip_once()
        return []
    cmd = _build_pylint_command(path, thresholds, exe)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        _log_pylint_skip_once()
        return []
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
                    "scope": {"kind": "class", "symbol": class_name},
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
                    "scope": {"kind": "class", "symbol": class_name},
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


def finding_applies_to_block(finding: dict[str, Any], block: _blocks.Block) -> bool:
    """True if a raw finding should count toward ``block`` in block-level stats.

    Most findings use Pylint's 1-based ``line`` within ``[block.start, block.end]``.
    Class-scoped rows (``scope.kind == "class"``) use Pylint's class line, which is
    often *outside* method bodies, so we match every method block under that class
    name (``Foo.bar``, ``Foo.Inner.baz``, …).
    """
    scope = finding.get("scope")
    if isinstance(scope, dict) and scope.get("kind") == "class":
        sym = str(scope.get("symbol") or "").strip()
        if sym:
            return block.name == sym or block.name.startswith(f"{sym}.")
    line = int(finding.get("line") or 0)
    return block.start <= line <= block.end


def smell_resolution_cfg(merged_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Slice of merged config used by :func:`compute_smells` for severity weights."""
    src = merged_config if merged_config is not None else _config.DEFAULTS
    base_rw = _config.DEFAULTS["smell_rule_weights"]
    base_cw = _config.DEFAULTS["smell_category_weights"]
    rw = src.get("smell_rule_weights")
    cw = src.get("smell_category_weights")
    return {
        "smell_rule_weights": deepcopy(rw) if isinstance(rw, dict) else deepcopy(base_rw),
        "smell_category_weights": deepcopy(cw) if isinstance(cw, dict) else deepcopy(base_cw),
        "smell_default_weight": float(
            src.get("smell_default_weight", _config.DEFAULTS["smell_default_weight"])
        ),
    }


def resolve_smell_severity(finding: dict[str, Any], res_cfg: dict[str, Any]) -> float:
    """Return severity in ``[0.0, 1.0]`` using rule → category → default order."""
    rules: dict[str, Any] = res_cfg.get("smell_rule_weights") or {}
    cats: dict[str, Any] = res_cfg.get("smell_category_weights") or {}
    default = float(res_cfg.get("smell_default_weight", 0.4))

    smell_id = str(finding.get("smell") or "").strip()
    if smell_id and smell_id in rules:
        return max(0.0, min(1.0, float(rules[smell_id])))

    code = finding.get("pylint_code")
    if isinstance(code, str) and code:
        ch = code[0].upper()
        if ch in cats:
            return max(0.0, min(1.0, float(cats[ch])))

    return max(0.0, min(1.0, default))


def _attach_severities(findings: list[dict[str, Any]], res_cfg: dict[str, Any]) -> None:
    for item in findings:
        item["severity"] = resolve_smell_severity(item, res_cfg)


def summarize_smells(findings: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Roll up raw findings by normalized smell id (e.g. ``long_method``, ``dead_code``).

    Returns ``{ smell_type: occurrence_count }`` for the file or block scope.
    """
    out: dict[str, int] = {}
    for item in findings:
        smell_type = str(item.get("smell") or "unknown")
        out[smell_type] = out.get(smell_type, 0) + 1
    return out


def compute_smells(
    path: Path, merged_config: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Return normalized smell findings for one Python file.

    Output shape (one dict per occurrence; ``summarize_smells`` counts by ``smell`` id):
    - file: file path as reported by Pylint
    - line: 1-indexed line number
    - smell: normalized smell family
    - message: human-readable finding message
    - severity: float in ``[0.0, 1.0]`` from rule / Pylint category / default weights
    - pylint_code: optional Pylint ``message-id`` (e.g. ``R0913``) for category fallback
    - scope: optional ``{"kind": "class", "symbol": qualname}`` for class-attributed
      findings (used by ``finding_applies_to_block`` so block rows stay aligned)
    """
    thresholds = _default_thresholds()
    src = path.read_text(encoding="utf-8", errors="replace")
    raw_pylint = _run_pylint_raw(path, thresholds)
    out = _compute_pylint_smells(path, raw_pylint)
    out.extend(_compute_approximate_smells(path, src, raw_pylint, thresholds))
    out.extend(_compute_comment_smells(path, thresholds))
    res_cfg = smell_resolution_cfg(merged_config)
    _attach_severities(out, res_cfg)
    return out


def collect_repo_smell_findings(
    target: str,
    filter: str | None = None,
    *,
    respect_gitignore: bool = True,
    ignore_dir: str | None = None,
    merged_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Flat smell findings for tracked files under the same filters as the CLI/MCP used.

    Not an MCP tool — for internal use and tests. Uses :func:`compute_smells` per file.
    """
    from hotspottriage import discovery, filtering

    cfg = dict(_config.DEFAULTS)
    if filter:
        cfg["filter"] = [f.strip() for f in filter.split(",")]
    cfg["respect_gitignore"] = respect_gitignore
    if ignore_dir:
        cfg["ignore_directories"] = [d.strip() for d in ignore_dir.split(",")]

    findings: list[dict[str, Any]] = []
    with discovery.resolve_target(target) as repo:
        patterns = list(cfg["filter"])
        if not cfg["no_default_filter"]:
            patterns.append(cfg["default_filter"])
        glob_keep = filtering.make_filter(patterns)
        keep = filtering.make_tracked_path_predicate(
            repo,
            glob_keep=glob_keep,
            ignore_directories=cfg["ignore_directories"],
            respect_gitignore=cfg["respect_gitignore"],
        )
        files = [f for f in discovery.list_tracked_files(repo) if keep(f)]
        for rel in files:
            findings.extend(compute_smells(repo / rel, merged_config))
    return findings
