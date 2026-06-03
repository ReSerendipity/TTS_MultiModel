import os
import time
import glob
import logging

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse

from ..config import SAVE_DIR, PERSONA_DIR, PROJECT_ROOT
from ..utils import get_history_table_data, get_history_table_data_paginated, get_total_history_count
from ..history_manager import get_history_manager

router = APIRouter(prefix="/api", tags=["audio"])

logger = logging.getLogger("tts_multimodel")

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".wma", ".aac"}


@router.get("/audio/{filename}", summary="获取音频", description="获取生成的音频文件")
async def serve_audio(filename: str):
    file_path = os.path.join(SAVE_DIR, filename)
    real_path = os.path.realpath(file_path)
    if not real_path.startswith(os.path.realpath(SAVE_DIR)):
        return JSONResponse({"status": "error", "message": "Invalid path"}, status_code=400)
    if os.path.isfile(real_path):
        # Audio files are user-generated, use moderate caching
        headers = {
            "Cache-Control": "public, max-age=3600",  # 1 hour
            "Accept-Ranges": "bytes",
        }
        return FileResponse(real_path, media_type="audio/wav", filename=filename, headers=headers)
    return JSONResponse({"status": "error", "message": f"File not found: {filename}"}, status_code=404)


@router.get("/persona/audio/{name}", summary="音色音频", description="获取指定音色的参考音频")
async def serve_persona_audio(name: str, request: Request):
    file_path = os.path.join(PERSONA_DIR, f"{name}.wav")
    real_path = os.path.realpath(file_path)
    if not real_path.startswith(os.path.realpath(PERSONA_DIR)):
        return JSONResponse({"status": "error", "message": "Invalid path"}, status_code=400)
    if os.path.isfile(real_path):
        headers = {
            "Cache-Control": "public, max-age=3600",
            "Accept-Ranges": "bytes",
        }
        return FileResponse(real_path, media_type="audio/wav", filename=f"{name}.wav", headers=headers)
    return JSONResponse({"status": "error", "message": f"Persona audio not found: {name}"}, status_code=404)


@router.post("/upload/audio", summary="上传音频", description="上传音频文件到服务器")
async def upload_audio(file: UploadFile = File(...)):
    try:
        # Validate file extension
        _, ext = os.path.splitext(file.filename or "")
        if ext.lower() not in ALLOWED_AUDIO_EXTENSIONS:
            return JSONResponse(
                {"status": "error", "message": f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}"},
                status_code=400,
            )
        timestamp = int(time.time() * 1000)
        filename = f"temp_upload_{timestamp}.wav"
        file_path = os.path.join(SAVE_DIR, filename)
        content = await file.read()
        # Validate file size
        if len(content) > MAX_UPLOAD_SIZE:
            return JSONResponse(
                {"status": "error", "message": f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)}MB"},
                status_code=413,
            )
        with open(file_path, "wb") as f:
            f.write(content)
        return JSONResponse({"status": "ok", "path": file_path, "filename": filename})
    except Exception as e:
        logger.error(f"Audio upload failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@router.get("/speaker/sample/{key}", summary="说话人样本", description="获取预置说话人的样本音频")
async def speaker_sample(key: str):
    samples_dir = os.path.join(PROJECT_ROOT, "samples", "parity")
    if not os.path.isdir(samples_dir):
        return JSONResponse({"status": "error", "message": "Samples directory not found"}, status_code=404)
    pattern = os.path.join(samples_dir, f"*{key.lower()}*.wav")
    matches = glob.glob(pattern)
    if matches:
        headers = {
            "Cache-Control": "public, max-age=86400, immutable",  # 1 day, static samples
            "Accept-Ranges": "bytes",
        }
        return FileResponse(matches[0], media_type="audio/wav", filename=os.path.basename(matches[0]), headers=headers)
    return JSONResponse({"status": "error", "message": f"No sample found for speaker: {key}"}, status_code=404)


@router.get("/history/table", summary="历史记录", description="获取生成历史记录表格")
async def history_table(request: Request):
    keyword = request.query_params.get("keyword", "")
    time_filter = request.query_params.get("time_filter", "all")
    include_hidden = request.query_params.get("include_hidden", "false").lower() == "true"
    try:
        limit = int(request.query_params.get("limit", 20))
    except (ValueError, TypeError):
        limit = 20
    try:
        offset = int(request.query_params.get("offset", 0))
    except (ValueError, TypeError):
        offset = 0
    
    # 使用新的历史记录管理器
    history_manager = get_history_manager()
    
    # 首先尝试从文件系统同步
    try:
        history_manager.sync_from_filesystem()
    except Exception as e:
        logger.error(f"Failed to sync history from filesystem: {e}")
    
    # 限制每页最大数量
    if limit > 100:
        limit = 100
    elif limit <= 0:
        limit = 20
    
    result = history_manager.get_paginated_records(
        limit=limit,
        offset=offset,
        search_keyword=keyword,
        time_filter=time_filter,
        include_hidden=include_hidden
    )
    
    # 转换为与之前兼容的格式
    records = []
    for rec in result["items"]:
        size_mb = rec.file_size / (1024 * 1024) if rec.file_size > 0 else 0
        size_str = f"{size_mb:.1f} MB"
        duration_str = f"{rec.duration_seconds:.1f}s" if rec.duration_seconds > 0 else "<1s"
        records.append([
            rec.filename,
            rec.created_at,
            duration_str,
            size_str
        ])
    
    return JSONResponse({
        "status": "ok",
        "records": records,
        "total": result["total"],
        "hasMore": result["hasMore"],
        "loaded": result["loaded"],
    })


@router.post("/batch_export_history", summary="批量导出", description="批量导出历史记录中的音频文件")
async def batch_export_history(request: Request):
    payload = await request.json()
    ids = payload.get("ids", [])
    if not ids:
        return JSONResponse({"status": "error", "error": "No records selected"}, status_code=400)
    return JSONResponse({"status": "ok", "count": len(ids)})


@router.post("/batch_delete_history", summary="批量删除", description="批量删除历史记录")
async def batch_delete_history(request: Request):
    """批量隐藏历史记录（不删除实际文件）"""
    payload = await request.json()
    ids = payload.get("ids", [])
    delete_files = payload.get("delete_files", False)
    
    if not ids:
        return JSONResponse({"status": "error", "error": "No records selected"}, status_code=400)
    
    history_manager = get_history_manager()
    
    if delete_files:
        # 彻底删除文件和记录
        count = history_manager.delete_multiple_records(ids, delete_files=True)
        action = "deleted"
    else:
        # 只隐藏记录
        count = history_manager.hide_multiple_records(ids)
        action = "hidden"
    
    return JSONResponse({"status": "ok", "count": count, "action": action})


@router.post("/history/hide", summary="隐藏记录", description="隐藏指定的历史记录")
async def hide_history_records(request: Request):
    """隐藏历史记录"""
    payload = await request.json()
    ids = payload.get("ids", [])
    if not ids:
        return JSONResponse({"status": "error", "error": "No records selected"}, status_code=400)
    
    history_manager = get_history_manager()
    count = history_manager.hide_multiple_records(ids)
    return JSONResponse({"status": "ok", "count": count})


@router.post("/history/clear_all", summary="清空记录", description="清空所有历史记录")
async def clear_all_history(request: Request):
    """清除所有历史记录（默认只隐藏）"""
    payload = await request.json()
    hide_only = payload.get("hide_only", True)
    
    history_manager = get_history_manager()
    count = history_manager.clear_all_records(hide_only=hide_only)
    
    action = "hidden" if hide_only else "cleared"
    return JSONResponse({"status": "ok", "count": count, "action": action})


@router.post("/history/show", summary="显示记录", description="显示指定的隐藏记录")
async def show_history_records(request: Request):
    """恢复显示被隐藏的历史记录"""
    payload = await request.json()
    ids = payload.get("ids", [])
    if not ids:
        return JSONResponse({"status": "error", "error": "未选择记录"}, status_code=400)
    
    history_manager = get_history_manager()
    count = history_manager.show_multiple_records(ids)
    return JSONResponse({"status": "ok", "count": count})


@router.post("/history/show_all", summary="显示全部", description="显示所有隐藏的记录")
async def show_all_history(request: Request):
    """恢复显示所有被隐藏的历史记录"""
    history_manager = get_history_manager()
    count = history_manager.show_all_records()
    return JSONResponse({"status": "ok", "count": count})


@router.post("/history/sync", summary="同步记录", description="同步文件系统与数据库的历史记录")
async def sync_history():
    """从文件系统同步历史记录"""
    history_manager = get_history_manager()
    count = history_manager.sync_from_filesystem()
    return JSONResponse({"status": "ok", "added_count": count})
