"""Shared context for multi-pass block-level analysis."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class BlockAnalysisContext:
    """Intermediate state for block-level analysis pipeline."""

    repo: Path
    files: list[str]
    blob_shas: dict[str, str]
    previous_rows: dict[str, dict[str, Any]]
    prev_rows_list: list[dict[str, Any]]
    timestamps: dict[str, int]
    current_time: int
    merged_config: dict[str, Any]
    decay_half_life: int | None = None
