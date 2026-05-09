"""Pydantic models for dashboard HTTP bodies (size limits, coercion)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hotspottriage.path_utils import MAX_TARGET_PATH_STR_LEN

MAX_CACHE_FILTER_FIELD_LEN = 8192


class DashboardCacheRequestBody(BaseModel):
    """JSON body for cache-related dashboard POST endpoints."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=False)

    target: str = Field(default="", max_length=MAX_TARGET_PATH_STR_LEN)
    include: str = Field(default="", max_length=MAX_CACHE_FILTER_FIELD_LEN)
    exclude: str = Field(default="", max_length=MAX_CACHE_FILTER_FIELD_LEN)
    filter: str = Field(default="", max_length=MAX_CACHE_FILTER_FIELD_LEN)

    @field_validator("target", "include", "exclude", "filter", mode="before")
    @classmethod
    def _coerce_optional_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


class DashboardConfigPatchBody(BaseModel):
    """JSON body for ``/api/config/patch`` (only documented keys)."""

    model_config = ConfigDict(extra="forbid")

    metric_normalization: dict[str, Any] | None = None
    score_aggregation: dict[str, Any] | None = None
    proposed_models: dict[str, Any] | None = None
