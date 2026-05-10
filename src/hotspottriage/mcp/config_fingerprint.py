"""Stable digest of merged MCP analyze config."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def config_fingerprint(cfg: dict[str, Any]) -> str:
    """Stable digest of the merged analyze config (for comparing runs)."""
    payload = json.dumps(cfg, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
