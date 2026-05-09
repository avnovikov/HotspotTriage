"""Public :class:`Statistic` row type (output + stats pipeline).

Defined in a tiny module so :mod:`hotspottriage.output` does not import
:mod:`hotspottriage.stats`, which breaks cyclic imports through
``config → output → stats → …`` (CodeQL ``py/cyclic-import``).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Statistic:
    path: str
    sloc: int
    normalized_sloc: float
    cyclomatic: int
    halstead: int
    maintainability: int
    churn: int
    churn_per_sloc: float
    decayed_churn: float
    decayed_churn_per_sloc: float
    smell_count: int
    smell_severity: float
    smell_burden: float
    smells: dict[str, int]
    similarity_score: float
    similarity_band: str
    match_count: int
    score: float
    score_band: str = "n/a"
    score_subscores: dict[str, float] = field(default_factory=dict)
    score_driver: str = ""
    score_explanation: list[dict[str, Any]] = field(default_factory=list)
    # Normalized ``final_weights`` map used with ``score_subscores`` (block runs).
    score_final_weights: dict[str, float] | None = None

    def as_dict(self) -> dict:
        return asdict(self)
