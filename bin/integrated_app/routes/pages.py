from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
import os

from ..i18n import t, get_lang, register_i18n_filters, get_i18n_json

router = APIRouter()


@router.get("/")
async def index(request: Request):
    templates = request.app.state.templates
    lang = get_lang(request)
    return templates.TemplateResponse(
        request=request,
        name="base.html",
        context={
            "version": getattr(request.app.state, "version", "0.0.0"),
            "lang": lang,
            "i18n_json": get_i18n_json(lang),
        },
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/favicon.ico", summary="网站图标")
async def favicon():
    svg_content = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="20" fill="%236B5CE7"/><text x="50" y="68" font-size="50" font-weight="bold" fill="white" text-anchor="middle" font-family="Arial">TTS</text></svg>'
    return HTMLResponse(content=svg_content, media_type="image/svg+xml")
