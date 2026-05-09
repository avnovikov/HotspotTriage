"""Split / compose dashboard cache glob filters for include vs exclude fields.

CLI and ``generate_full_cache`` use a single comma-separated filter string with
gitignore-style AND semantics; ``!`` prefixes negated patterns. The dashboard
shows separate include and exclude inputs; this module converts between the two
representations. Pattern tokens are normalised (e.g. leading ``./`` stripped)
via :func:`hotspottriage.filtering.normalize_filter_pattern`.
"""

from __future__ import annotations

from hotspottriage.filtering import normalize_filter_pattern


def _comma_tokens(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def split_filter_for_fields(combined: str) -> tuple[str, str]:
    """Split a combined filter string into display include / exclude CSV strings."""
    includes: list[str] = []
    excludes: list[str] = []
    for token in _comma_tokens(combined):
        if token.startswith("!"):
            body = token[1:].strip()
            norm_exc = normalize_filter_pattern(body)
            if norm_exc.startswith("!"):
                norm_exc = norm_exc[1:].lstrip()
            if norm_exc:
                excludes.append(norm_exc)
        else:
            norm_inc = normalize_filter_pattern(token)
            if norm_inc:
                includes.append(norm_inc)
    return ",".join(includes), ",".join(excludes)


def compose_filter_from_fields(include_csv: str, exclude_csv: str) -> str | None:
    """Build the combined filter string for the analysis pipeline.

    Returns ``None`` when there are no explicit patterns (pipeline applies the
    default ``**/*.py`` rule via config).
    """
    parts: list[str] = []
    for token in _comma_tokens(include_csv):
        norm = normalize_filter_pattern(token)
        if norm:
            parts.append(norm)
    for token in _comma_tokens(exclude_csv):
        norm = normalize_filter_pattern(token)
        if not norm:
            continue
        if norm.startswith("!"):
            parts.append(norm)
        else:
            parts.append(f"!{norm}")
    if not parts:
        return None
    return ",".join(parts)
