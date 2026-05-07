import os
import time
import glob
import logging

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse

from ..config import SAVE_DIR, PERSONA_DIR, PROJECT_ROOT
from ..utils import get_history_table_data, get_history_table_data_paginated, get_total_history_count

router = APIRouter(prefix="/api", tags=["audio"])

logger = logging.getLogger("tts_multimodel")

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".wma", ".aac"}


@router.get("/audio/{filename}")
async def serve_audio(filename: str):
    file_path = os.path.join(SAVE_DIR, filename)
    real_path = os.path.realpath(file_path)
    if not real_path.startswith(os.path.realpath(SAVE_DIR)):
        return JSONResponse({"status": "error", "message": "Invalid path"}, status_code=400)
    if os.path.isfile(real_path):
        return FileResponse(real_path, media_type="audio/wav", filename=filename)
    return JSONResponse({"status": "error", "message": f"File not found: {filename}"}, status_code=404)


@router.get("/persona/audio/{name}")
async def serve_persona_audio(name: str):
    file_path = os.path.join(PERSONA_DIR, f"{name}.wav")
    real_path = os.path.realpath(file_path)
    if not real_path.startswith(os.path.realpath(PERSONA_DIR)):
        return JSONResponse({"status": "error", "message": "Invalid path"}, status_code=400)
    if os.path.isfile(real_path):
        return FileResponse(real_path, media_type="audio/wav", filename=f"{name}.wav")
    return JSONResponse({"status": "error", "message": f"Persona audio not found: {name}"}, status_code=404)


@router.post("/upload/audio")
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


@router.get("/speaker/sample/{key}")
async def speaker_sample(key: str):
    samples_dir = os.path.join(PROJECT_ROOT, "samples", "parity")
    if not os.path.isdir(samples_dir):
        return JSONResponse({"status": "error", "message": "Samples directory not found"}, status_code=404)
    pattern = os.path.join(samples_dir, f"*{key.lower()}*.wav")
    matches = glob.glob(pattern)
    if matches:
        return FileResponse(matches[0], media_type="audio/wav", filename=os.path.basename(matches[0]))
    return JSONResponse({"status": "error", "message": f"No sample found for speaker: {key}"}, status_code=404)


@router.get("/history/table")
async def history_table(request: Request):
    keyword = request.query_params.get("keyword", "")
    time_filter = request.query_params.get("time_filter", "all")
    # Pagination parameters
    try:
        limit = int(request.query_params.get("limit", 0))
    except (ValueError, TypeError):
        limit = 0
    try:
        offset = int(request.query_params.get("offset", 0))
    except (ValueError, TypeError):
        offset = 0

    # If limit/offset are provided, use paginated response
    if limit > 0:
        # Clamp limit to max 50
        if limit > 50:
            limit = 50
        result = get_history_table_data_paginated(
            search_keyword=keyword,
            time_filter=time_filter,
            limit=limit,
            offset=offset,
        )
        return JSONResponse({
            "status": "ok",
            "records": result["items"],
            "total": result["total"],
            "hasMore": result["hasMore"],
            "loaded": result["loaded"],
        })

    # Legacy non-paginated response (for backward compatibility)
    table_data = get_history_table_data(search_keyword=keyword, time_filter=time_filter)
    return JSONResponse({"status": "ok", "records": table_data, "total": get_total_history_count()})


@router.post("/batch_export_history")
async def batch_export_history(request: Request):
    payload = await request.json()
    ids = payload.get("ids", [])
    if not ids:
        return JSONResponse({"status": "error", "error": "No records selected"}, status_code=400)
    return JSONResponse({"status": "ok", "count": len(ids)})


@router.post("/batch_delete_history")
async def batch_delete_history(request: Request):
    from ..utils import invalidate_history_cache
    payload = await request.json()
    ids = payload.get("ids", [])
    if not ids:
        return JSONResponse({"status": "error", "error": "No records selected"}, status_code=400)
    deleted = 0
    for filename in ids:
        filepath = os.path.join(SAVE_DIR, filename)
        real_path = os.path.realpath(filepath)
        if real_path.startswith(os.path.realpath(SAVE_DIR)) and os.path.isfile(real_path):
            os.remove(real_path)
            deleted += 1
    invalidate_history_cache()
    return JSONResponse({"status": "ok", "deleted": deleted})
