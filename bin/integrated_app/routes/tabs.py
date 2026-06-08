from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os
import html

from ..persona_manager import get_persona_list, get_total_persona_count, get_persona_detail_table
from ..history_db import get_history_db
from ..config import _LANGS, _DIALECTS, GEN_SPLIT_MAX_CHARS
from ..model_registry import registry
from ..i18n import t, get_lang, register_i18n_filters

router = APIRouter()

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))
register_i18n_filters(templates.env)

_TAB_TEMPLATES = {
    "voice_design": "tabs/voice_design.html",
    "voice_clone": "tabs/voice_clone.html",
    "ultimate_clone": "tabs/ultimate_clone.html",
    "prompt_continue": "tabs/prompt_continue.html",
    "script": "tabs/script.html",
    "voxcpm2": "tabs/settings.html",
    "settings": "tabs/settings.html",
    "indextts2": "tabs/indextts2.html",
    "indextts2_clone": "tabs/indextts2_clone.html",
    "indextts2_emotion": "tabs/indextts2_emotion.html",
    "indextts2_duration": "tabs/indextts2_duration.html",
    "lora": "tabs/lora_manager.html",
    "lora_training": "tabs/lora_training.html",
    "history": "tabs/history.html",
    "persona": "tabs/persona.html",
    "help": "tabs/help.html",
}


# VoxCPM2相关的标签页（这些页面使用VoxCPM2模型，字符上限8192）
_VOXCPM2_TABS = {"voice_design", "voice_clone", "ultimate_clone", "prompt_continue", "voxcpm2"}

# IndexTTS2相关的标签页（这些页面使用IndexTTS2模型，字符上限3072）
_INDEXTTS2_TABS = {"indextts2", "indextts2_clone", "indextts2_emotion", "indextts2_duration"}


def _common_context(request: Request, tab_name: str = ""):
    lang = get_lang(request)
    # Use configurable split_max_chars from AdvancedParamsConfig
    try:
        from ..config_models import AdvancedParamsConfig
        split_chars = AdvancedParamsConfig().split_max_chars
    except Exception:
        split_chars = GEN_SPLIT_MAX_CHARS
    
    # Model-specific total character limits: 根据标签页决定，而非registry.current_engine
    if tab_name in _VOXCPM2_TABS:
        engine_max_chars = 8192  # VoxCPM2字符上限
    elif tab_name in _INDEXTTS2_TABS:
        engine_max_chars = 3072  # IndexTTS2字符上限
    else:
        # 其他标签页（script、settings、history等）使用当前引擎或默认值
        engine_max_chars = 8192 if registry.current_engine == "voxcpm2" else 3072
    
    return {
        "request": request,
        "current_engine": registry.current_engine,
        "langs": _LANGS,
        "dialects": _DIALECTS,
        "lang": lang,
        "gen_split_max_chars": split_chars,
        "engine_max_total_chars": engine_max_chars,
    }


@router.get("/tab/{tab_name}", summary="标签页")
async def get_tab(request: Request, tab_name: str):
    template_name = _TAB_TEMPLATES.get(tab_name)
    if not template_name:
        safe_name = html.escape(tab_name)
        return HTMLResponse(
            f'<div class="card" style="padding:40px;text-align:center;color:var(--text-muted);">'
            f'<p>Tab "{safe_name}" is under construction</p></div>'
        )

    template_path = os.path.join(_BASE_DIR, "templates", template_name)
    if not os.path.exists(template_path):
        safe_name = html.escape(tab_name)
        return HTMLResponse(
            f'<div class="card" style="padding:40px;text-align:center;color:var(--text-muted);">'
            f'<p>Tab "{safe_name}" template not found</p></div>'
        )

    ctx = _common_context(request, tab_name=tab_name)

    if tab_name == "voice_design":
        ctx["persona_list"] = get_persona_list()
    elif tab_name == "voice_clone":
        ctx["persona_list"] = get_persona_list()
    elif tab_name == "ultimate_clone":
        ctx["persona_list"] = get_persona_list()
    elif tab_name == "voxcpm2":
        ctx["persona_list"] = get_persona_list()
    elif tab_name == "history":
        search = request.query_params.get("search_keyword", "")
        time_filter = request.query_params.get("time_filter", "all")
        db = get_history_db()
        paginated = db.get_paginated_records(
            search_keyword=search,
            time_filter=time_filter,
            limit=20,
            offset=0,
        )
        # Convert dict items to table rows [basename, time, duration, size]
        items = []
        for rec in paginated["items"]:
            file_size = rec.get("file_size_bytes", 0) or 0
            size_mb = file_size / (1024 * 1024) if file_size > 0 else 0
            size_str = f"{size_mb:.1f} MB"
            duration = rec.get("duration_seconds", 0) or 0
            duration_str = f"{duration:.1f}s" if duration > 0 else "<1s"
            items.append([
                rec.get("filename", ""),
                rec.get("created_at", ""),
                duration_str,
                size_str,
            ])
        no_records_text = t("history_no_records", lang)
        ctx["history_records"] = items if items else [[no_records_text, "-", "-", "-"]]
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
