from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os

from ..persona_manager import get_persona_list, get_total_persona_count, get_persona_detail_table
from ..utils import generate_speaker_card_grid, get_generation_history_enhanced, get_total_history_count, get_history_table_data_paginated
from ..config import OFFICIAL_SPEAKER_INFO, _OFFICIAL_SPEAKERS_ORDERED, _LANGS, _DIALECTS
from ..model_manager import current_engine
from ..i18n import t, get_lang, register_i18n_filters

router = APIRouter()

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))
register_i18n_filters(templates.env)

_TAB_TEMPLATES = {
    "voice_design": "tabs/voice_design.html",
    "voice_clone": "tabs/voice_clone.html",
    "ultimate_clone": "tabs/ultimate_clone.html",
    "script": "tabs/script.html",
    "voxcpm2": "tabs/voxcpm2.html",
    "lora": "tabs/lora_manager.html",
    "lora_training": "tabs/lora_training.html",
    "history": "tabs/history.html",
    "persona": "tabs/persona.html",
}


def _common_context(request: Request):
    lang = get_lang(request)
    return {
        "request": request,
        "current_engine": current_engine,
        "langs": _LANGS,
        "dialects": _DIALECTS,
        "lang": lang,
    }


@router.get("/tab/{tab_name}")
async def get_tab(request: Request, tab_name: str):
    template_name = _TAB_TEMPLATES.get(tab_name)
    if not template_name:
        return HTMLResponse(
            f'<div class="card" style="padding:40px;text-align:center;color:var(--text-muted);">'
            f'<p>Tab "{tab_name}" is under construction</p></div>'
        )

    template_path = os.path.join(_BASE_DIR, "templates", template_name)
    if not os.path.exists(template_path):
        return HTMLResponse(
            f'<div class="card" style="padding:40px;text-align:center;color:var(--text-muted);">'
            f'<p>Tab "{tab_name}" template not found</p></div>'
        )

    ctx = _common_context(request)

    if tab_name == "voice_design":
        ctx["persona_list"] = get_persona_list(include_official=False)
    elif tab_name == "voice_clone":
        ctx["persona_list"] = get_persona_list(include_official=True)
    elif tab_name == "ultimate_clone":
        ctx["persona_list"] = get_persona_list(include_official=True)
    elif tab_name == "voxcpm2":
        ctx["persona_list"] = get_persona_list(include_official=True)
    elif tab_name == "history":
        search = request.query_params.get("search_keyword", "")
        time_filter = request.query_params.get("time_filter", "all")
        paginated = get_history_table_data_paginated(
            search_keyword=search,
            time_filter=time_filter,
            limit=20,
            offset=0,
        )
        ctx["history_records"] = paginated["items"] if paginated["items"] else [["暂无记录", "-", "-", "-"]]
        ctx["history_count"] = paginated["total"]
        ctx["history_loaded"] = paginated["loaded"]
        ctx["history_has_more"] = paginated["hasMore"]
        ctx["search_keyword"] = search
        ctx["time_filter"] = time_filter
    elif tab_name == "persona":
        ctx["persona_count"] = get_total_persona_count()
        ctx["total_persona_count"] = ctx["persona_count"]
        ctx["persona_table_data"] = get_persona_detail_table()

    return templates.TemplateResponse(template_name, ctx, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
