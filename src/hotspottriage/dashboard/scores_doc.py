"""Standalone HTML for ``SCORES.md`` (iframe / raw endpoint; no import of ``server``)."""
from __future__ import annotations

import html
from pathlib import Path


def scores_doc_html() -> str:
    """Return a lightweight HTML page for ``SCORES.md``."""
    repo_root = Path(__file__).resolve().parents[3]
    scores_path = repo_root / "SCORES.md"
    try:
        body = scores_path.read_text(encoding="utf-8")
    except OSError:
        body = "# SCORES.md not found\n\nUnable to locate the `SCORES.md` file."
    escaped = html.escape(body)
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<title>HotspotTriage Scores</title>"
        "<style>"
        "body{margin:0;padding:1rem;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "background:#fcfcfa;color:#1f2937;}"
        "main{max-width:980px;margin:0 auto;}"
        "pre{white-space:pre-wrap;word-break:break-word;background:#fff;border:1px solid #d1d5db;"
        "border-radius:10px;padding:1rem;line-height:1.45;box-shadow:0 2px 10px rgba(15,23,42,.08);}"
        "</style></head><body><main><pre>"
        f"{escaped}"
        "</pre></main></body></html>"
    )
