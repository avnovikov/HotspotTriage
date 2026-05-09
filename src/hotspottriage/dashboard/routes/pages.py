"""Page-serving routes (Jinja2 template rendering)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter()


@router.get("/dashboard/", response_class=HTMLResponse)
def dashboard_overview(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "overview.html")


@router.get("/dashboard/heatmap", response_class=HTMLResponse)
def dashboard_heatmap(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "heatmap.html")


@router.get("/dashboard/config", response_class=HTMLResponse)
def dashboard_config(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "config.html")


@router.get("/dashboard/scores", response_class=HTMLResponse)
def dashboard_scores(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "scores.html")


@router.get("/dashboard/scores/raw", response_class=HTMLResponse)
def dashboard_scores_raw() -> HTMLResponse:
    """Raw SCORES.md HTML for embedding in an iframe."""
    from hotspottriage.dashboard.server import _scores_doc_html
    return HTMLResponse(_scores_doc_html())
