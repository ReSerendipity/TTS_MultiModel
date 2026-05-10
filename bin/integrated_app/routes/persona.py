import os
import re
import html
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi import Form

from ..persona_manager import (
    fn_save_persona, get_persona_list, get_persona_desc,
    get_persona_detail_table, get_total_persona_count,
)
from ..config import PERSONA_DIR
from ..model_manager import _persona_embedding_cache

router = APIRouter(prefix="/api/persona", tags=["persona"])

logger = logging.getLogger("tts_multimodel")


@router.get("/list")
async def persona_list(request: Request):
    include_official = request.query_params.get("include_official", "false").lower() == "true"
    personas = get_persona_list(include_official=include_official)
    return JSONResponse({"status": "ok", "personas": personas, "total": get_total_persona_count()})


@router.get("/options")
async def persona_options(request: Request):
    include_official = request.query_params.get("include_official", "true").lower() == "true"
    personas = get_persona_list(include_official=include_official)
    options_html = ""
    for name in personas:
        options_html += f'<option value="{html.escape(name)}">{html.escape(name)}</option>'
    return HTMLResponse(options_html)


@router.get("/detail")
async def persona_detail(request: Request):
    name = request.query_params.get("name", "")
    if not name:
        return JSONResponse({"status": "error", "message": "Name parameter required"}, status_code=400)
    desc = get_persona_desc(name)
    return JSONResponse({"status": "ok", "name": name, "description": desc})


@router.post("/save")
async def save_persona(
    request: Request,
    name: str = Form(""),
    audio: str = Form(""),
    ref_text: str = Form(""),
):
    if not name:
        return JSONResponse({"status": "error", "message": "音色名称不能为空"}, status_code=400)
    try:
        msg, needs_confirm = fn_save_persona(name, audio, ref_text)
        return JSONResponse({
            "status": "ok" if not needs_confirm else "confirm",
            "message": msg,
            "needs_confirm": needs_confirm,
        })
    except Exception as e:
        logger.error(f"Persona save failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@router.delete("/{name}")
async def delete_persona(name: str):
    if not re.match(r'^[a-zA-Z0-9_\-\u4e00-\u9fff]+$', name):
        return JSONResponse({"status": "error", "message": "Invalid persona name"}, status_code=400)
    try:
        for ext in [".wav", ".txt"]:
            p = os.path.join(PERSONA_DIR, f"{name}{ext}")
            real_path = os.path.realpath(p)
            if not real_path.startswith(os.path.realpath(PERSONA_DIR)):
                return JSONResponse({"status": "error", "message": "Path traversal detected"}, status_code=400)
            if os.path.exists(p):
                os.remove(p)
        meta_path = os.path.join(PERSONA_DIR, f"{name}.meta.json")
        if os.path.exists(meta_path):
            os.remove(meta_path)
        if name in _persona_embedding_cache:
            del _persona_embedding_cache[name]
        return JSONResponse({"status": "ok", "message": f"音色 [{name}] 已删除"})
    except Exception as e:
        logger.error(f"Persona delete failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@router.get("/table")
async def persona_table(request: Request):
    search_keyword = request.query_params.get("keyword", "") or request.query_params.get("search_keyword", "")
    accept = request.headers.get("accept", "")
    table_data = get_persona_detail_table(search_keyword=search_keyword)
    if "application/json" in accept or request.query_params.get("format") == "json":
        return JSONResponse({"status": "ok", "records": table_data, "total": len(table_data)})
    rows_html = ""
    for row in table_data:
        name = row[0]
        status = row[1]
        size = row[2]
        time_str = row[3]
        ref_text = row[4]
        rows_html += (
            f'<tr>'
            f'<td>{html.escape(name)}</td>'
            f'<td>{html.escape(status)}</td>'
            f'<td>{html.escape(size)}</td>'
            f'<td>{html.escape(time_str)}</td>'
            f'<td>{html.escape(ref_text)}</td>'
            f'<td>'
            f'<button class="btn-sm" onclick="playPersonaAudio(\'{html.escape(name, quote=True)}\')">▶ 试听</button> '
            f'<button class="btn-sm btn-danger" onclick="deletePersona(\'{html.escape(name, quote=True)}\')">🗑 删除</button>'
            f'</td>'
            f'</tr>'
        )
    return HTMLResponse(rows_html)
