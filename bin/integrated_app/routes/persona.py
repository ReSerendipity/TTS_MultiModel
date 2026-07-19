# -*- coding: utf-8 -*-
"""音色库 API 路由。

提供音色表格数据查询、搜索过滤以及单条删除能力。
音色参考音频下发由 routes/audio.py 的 /api/persona/audio/{name} 处理。
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..persona_manager import (
    delete_persona,
    get_persona_detail_table,
    get_total_persona_count,
)

router = APIRouter(prefix="/api/persona", tags=["persona"])
logger = logging.getLogger("tts_multimodel")

_KEYWORD_MAX_LENGTH = 100


@router.get("/table", summary="音色表格", description="获取音色库表格数据，支持 JSON 格式")
async def persona_table(request: Request):
    keyword = request.query_params.get("keyword", "")
    if len(keyword) > _KEYWORD_MAX_LENGTH:
        keyword = keyword[:_KEYWORD_MAX_LENGTH]

    records = get_persona_detail_table(search_keyword=keyword)

    return JSONResponse({
        "status": "ok",
        "records": records,
        "total": get_total_persona_count(),
    })


@router.delete("/{name}", summary="删除音色", description="删除指定音色及其关联文件")
async def persona_delete(name: str):
    success, message = delete_persona(name)
    if success:
        return JSONResponse({"status": "ok", "message": message})
    return JSONResponse({"status": "error", "message": message}, status_code=400)
