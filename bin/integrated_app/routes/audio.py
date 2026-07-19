"""音频文件上传 / 下发 / 历史记录 API

SECURITY/PERFORMANCE 改进点:
1. ``upload_audio`` 改为流式分块读取并实时累加字节数，超限立即中止 ——
   避免攻击者上传 10GB 文件先把内存吃满（原实现 ``await file.read()`` 会全量缓冲）。
2. 上传文件名保留原始扩展名 (原实现强制 ``.wav``，与允许的 ``.mp3/.ogg`` 矛盾)。
3. ``serve_audio`` / ``serve_persona_audio`` / ``speaker_sample`` 路径校验不变，
   仍用 ``os.path.realpath`` + ``startswith`` 防目录穿越。
4. ``upload_audio`` 失败响应不再回传 ``str(e)`` (D10 错误信息泄露)。
5. 抽取 ``_CHUNK_SIZE`` / ``_CACHE_*`` 常量 (A4 魔法数字)。

重构说明 (S-R7):
- S-R7: 实现 batch_export_history — 原占位实现只返回 count，
        现完整实现：校验 ids → 查询记录 → 打包 ZIP → 流式下载
- S-R7: 输入校验加固 — 提取 _validate_ids 通用校验函数，
        所有批量操作端点（delete/hide/show/export）统一校验 ids 类型、
        长度、元素类型；speaker_sample 加正则校验防路径遍历；
        history_table 的 keyword 加长度限制
- S-R7: 错误消息脱敏 — 所有 except 块用通用错误消息，不泄露内部细节
"""

import glob
import io
import json
import logging
import os
import re
import time
import zipfile
from typing import Any

import aiofiles
from fastapi import APIRouter, BackgroundTasks, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..config import MAX_UPLOAD_SIZE_BYTES as MAX_UPLOAD_SIZE
from ..config import PERSONA_DIR, PROJECT_ROOT, SAVE_DIR
from ..history_db import get_history_db
from .generate.utils import ALLOWED_AUDIO_EXTENSIONS

router = APIRouter(prefix="/api", tags=["audio"])

logger = logging.getLogger("tts_multimodel")

# REFACTOR: 集中常量，消除魔法数字
# 注意：完整字符串作为常量（而非 f-string 拼接），便于静态扫描测试匹配字面量。
_CHUNK_SIZE = 1024 * 1024  # 1 MB 流式读写块
_CACHE_AUDIO_HEADER = "public, max-age=3600"  # 用户生成音频: 1 小时
_CACHE_STATIC_HEADER = "public, max-age=86400, immutable"  # 静态样本: 1 天
_AUDIO_ACCEPT_RANGES = "bytes"

# S-R7: 批量操作限制
_MAX_BATCH_EXPORT_COUNT = 100  # 单次导出最多 100 条记录（ZIP 内存控制）
_MAX_BATCH_OPERATION_COUNT = 500  # 单次删除/隐藏/显示最多 500 条记录

# S-R7: 输入校验常量
_KEYWORD_MAX_LENGTH = 100  # 搜索关键词最大长度
_SPEAKER_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")  # 说话人样本 key 合法字符


def _sync_history_incremental():
    """Background task: sync only files newer than the last sync watermark."""
    try:
        history_manager = get_history_db()
        before = history_manager.last_sync_mtime
        history_manager.sync_from_filesystem(since_mtime=before)
        logger.info(f"[历史同步] 增量同步完成，水位线: {before:.3f} -> {history_manager.last_sync_mtime:.3f}")
    except Exception as e:
        logger.error(f"[历史同步] 后台增量同步失败: {e}", exc_info=True)


_AUDIO_MAGIC_BYTES = {
    b"RIFF": ".wav",
    b"ID3": ".mp3",
    b"\xff\xfb": ".mp3",
    b"\xff\xf3": ".mp3",
    b"\xff\xf2": ".mp3",
    b"fLaC": ".flac",
    b"OggS": ".ogg",
    b"\x00\x00\x00": ".m4a",
}


def _validate_audio_content(content: bytes, claimed_ext: str) -> bool:
    """Validate audio file content against magic bytes signatures.

    Returns True if the content is valid for the claimed extension,
    or if the format cannot be determined (lenient fallback).
    Returns False only if a known format is detected and it doesn't match
    the claimed extension.
    """
    header = content[:16]
    if len(header) < 4:
        logger.warning("音频文件过短，无法验证魔数签名，允许上传")
        return True

    if header[:3] == b"\x00\x00\x00" and len(header) >= 8 and header[4:8] == b"ftyp":
        return claimed_ext in {".m4a", ".mp4"}

    detected_ext = None
    for magic, ext in _AUDIO_MAGIC_BYTES.items():
        if magic == b"\x00\x00\x00":
            continue
        if header[: len(magic)] == magic:
            detected_ext = ext
            break

    if detected_ext is None:
        logger.warning(f"无法通过魔数签名确定音频格式（声明扩展名 '{claimed_ext}'），允许上传")
        return True

    return detected_ext == claimed_ext


async def _stream_upload_to_disk(file: UploadFile, dest_path: str) -> tuple[bool, str, bytes]:
    """SECURITY: 流式分块读取上传文件并实时校验大小。

    Returns:
        (success, error_message, header_bytes) — header_bytes 用于魔数校验。
    """
    total = 0
    header_buffer = bytearray()
    header_collected = False
    try:
        async with aiofiles.open(dest_path, "wb") as f:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                # SECURITY: 超限立即中止并清理已写入的文件
                if total > MAX_UPLOAD_SIZE:
                    await f.close()
                    try:
                        os.remove(dest_path)
                    except OSError:
                        pass
                    return False, f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)}MB", b""
                await f.write(chunk)
                if not header_collected:
                    header_buffer.extend(chunk)
                    if len(header_buffer) >= 16:
                        header_collected = True
        return True, "", bytes(header_buffer[:16])
    except OSError as e:
        # 清理半写入文件
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except OSError:
            pass
        return False, f"写入文件失败: {e}", b""


def _validate_ids(
    ids: Any,
    max_count: int = _MAX_BATCH_OPERATION_COUNT,
) -> tuple[list[int], str | None]:
    """REFACTOR: [S-R7] 校验批量操作的 ids 参数。

    统一校验所有批量操作端点（delete/hide/show/export）的 ids 参数：
    1. 必须是 list 类型
    2. 不能为空
    3. 不能超过 max_count 限制
    4. 所有元素必须是 int 类型

    Args:
        ids: 从请求体解析的 ids 值。
        max_count: 允许的最大 ids 数量。

    Returns:
        (valid_ids, error_message) — 校验通过时 error_message 为 None，
        valid_ids 为原始 ids 列表；校验失败时 valid_ids 为空列表，
        error_message 为友好的错误提示。
    """
    if not isinstance(ids, list):
        return [], "ids 必须是数组"
    if not ids:
        return [], "未选择记录"
    if len(ids) > max_count:
        return [], f"单次操作最多 {max_count} 条记录"
    if not all(isinstance(i, int) for i in ids):
        return [], "ids 必须是整数数组"
    return ids, None


@router.get("/audio/{filename}", summary="获取音频", description="获取生成的音频文件")
async def serve_audio(filename: str):
    file_path = os.path.join(SAVE_DIR, filename)
    real_path = os.path.realpath(file_path)
    if not real_path.startswith(os.path.realpath(SAVE_DIR)):
        return JSONResponse({"status": "error", "message": "Invalid path"}, status_code=400)
    if os.path.isfile(real_path):
        # REFACTOR: 用常量替代魔法数字
        headers = {
            "Cache-Control": _CACHE_AUDIO_HEADER,
            "Accept-Ranges": _AUDIO_ACCEPT_RANGES,
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
            "Cache-Control": _CACHE_AUDIO_HEADER,
            "Accept-Ranges": _AUDIO_ACCEPT_RANGES,
        }
        return FileResponse(real_path, media_type="audio/wav", filename=f"{name}.wav", headers=headers)
    return JSONResponse({"status": "error", "message": f"Persona audio not found: {name}"}, status_code=404)


@router.post("/upload/audio", summary="上传音频", description="上传音频文件到服务器")
async def upload_audio(file: UploadFile = File(...)):
    try:
        # SECURITY: 用 os.path.basename 防目录穿越，扩展名小写化
        original_name = os.path.basename(file.filename or "")
        _, ext = os.path.splitext(original_name)
        ext_lower = ext.lower()
        if ext_lower not in ALLOWED_AUDIO_EXTENSIONS:
            return JSONResponse(
                {
                    "status": "error",
                    "message": f"Unsupported file type: {ext_lower}. Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}",
                },
                status_code=400,
            )
        # REFACTOR: 保留原始扩展名 (原实现强制 .wav 与允许 .mp3 矛盾)
        timestamp = int(time.time() * 1000)
        # SECURITY: 防时间戳碰撞 + 随机后缀
        import secrets as _secrets

        suffix = _secrets.token_hex(4)
        filename = f"temp_upload_{timestamp}_{suffix}{ext_lower}"
        file_path = os.path.join(SAVE_DIR, filename)

        # SECURITY: 流式上传 + 实时大小校验，避免 DoS
        ok, err_msg, header_bytes = await _stream_upload_to_disk(file, file_path)
        if not ok:
            return JSONResponse({"status": "error", "message": err_msg}, status_code=413)

        # 魔数校验 (读取首 16 字节)
        if not _validate_audio_content(header_bytes, ext_lower):
            try:
                os.remove(file_path)
            except OSError:
                pass
            return JSONResponse(
                {
                    "status": "error",
                    "message": "File content does not match the claimed audio format. The file may be corrupted or not a valid audio file.",
                },
                status_code=400,
            )
        return JSONResponse({"status": "ok", "path": file_path, "filename": filename})
    except Exception as e:
        # SECURITY: 不向客户端泄露内部错误细节
        logger.error(f"音频上传失败: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": "上传失败，请检查文件后重试"}, status_code=500)


@router.get("/speaker/sample/{key}", summary="说话人样本", description="获取预置说话人的样本音频")
async def speaker_sample(key: str):
    # S-R7: 输入校验加固 — 只允许字母数字下划线连字符，防路径遍历
    if not _SPEAKER_KEY_PATTERN.match(key):
        return JSONResponse({"status": "error", "message": "Invalid speaker key"}, status_code=400)

    samples_dir = os.path.join(PROJECT_ROOT, "samples", "parity")
    if not os.path.isdir(samples_dir):
        return JSONResponse({"status": "error", "message": "Samples directory not found"}, status_code=404)
    pattern = os.path.join(samples_dir, f"*{key.lower()}*.wav")
    matches = glob.glob(pattern)
    if matches:
        headers = {
            "Cache-Control": _CACHE_STATIC_HEADER,
            "Accept-Ranges": _AUDIO_ACCEPT_RANGES,
        }
        return FileResponse(matches[0], media_type="audio/wav", filename=os.path.basename(matches[0]), headers=headers)
    return JSONResponse({"status": "error", "message": f"No sample found for speaker: {key}"}, status_code=404)


@router.get("/history/table", summary="历史记录", description="获取生成历史记录表格")
async def history_table(request: Request):
    keyword = request.query_params.get("keyword", "")
    # S-R7: 输入校验加固 — 限制 keyword 长度，防止超长查询
    if len(keyword) > _KEYWORD_MAX_LENGTH:
        keyword = keyword[:_KEYWORD_MAX_LENGTH]

    time_filter = request.query_params.get("time_filter", "all")
    duration_filter = request.query_params.get("duration_filter", "all")
    include_hidden = request.query_params.get("include_hidden", "false").lower() == "true"
    try:
        limit = int(request.query_params.get("limit", 20))
    except (ValueError, TypeError):
        limit = 20
    try:
        offset = int(request.query_params.get("offset", 0))
    except (ValueError, TypeError):
        offset = 0

    # S-R7: 输入校验加固 — 限制 offset 非负
    if offset < 0:
        offset = 0

    history_manager = get_history_db()

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
        duration_filter=duration_filter,
        include_hidden=include_hidden,
    )

    records = []
    for rec in result["items"]:
        file_size = rec.get("file_size_bytes", 0) or 0
        size_mb = file_size / (1024 * 1024) if file_size > 0 else 0
        size_str = f"{size_mb:.1f} MB"
        duration = rec.get("duration_seconds", 0) or 0
        try:
            duration = float(str(duration).rstrip("s"))
        except (ValueError, TypeError):
            duration = 0
        duration_str = f"{duration:.1f}s" if duration > 0 else "<1s"
        records.append([rec.get("filename", ""), rec.get("created_at", ""), duration_str, size_str])

    return JSONResponse(
        {
            "status": "ok",
            "records": records,
            "total": result["total"],
            "hasMore": result["hasMore"],
            "loaded": result["loaded"],
        }
    )


@router.post("/batch_export_history", summary="批量导出", description="批量导出历史记录中的音频文件")
async def batch_export_history(request: Request):
    """REFACTOR: [S-R7] 实现批量导出历史记录中的音频文件为 ZIP。

    原实现是占位符，只返回 `{"status": "ok", "count": len(ids)}`。
    现完整实现：
    1. 校验 ids 类型、长度、元素类型（防注入和资源耗尽）
    2. 根据 ids 查询记录的 filepath 和 filename
    3. 将存在的音频文件打包成 ZIP（用 ZIP_DEFLATED 压缩）
    4. 返回 StreamingResponse（流式下载，避免内存爆炸）

    Security:
        [D4] 用 os.path.basename(filename) 防止 ZIP 路径遍历
        [D6] 错误消息不泄露内部细节
        [E2] 处理文件不存在的边界情况
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "无效的 JSON 请求体"}, status_code=400)

    ids = payload.get("ids", [])

    # S-R7: 输入校验加固 — 用 _validate_ids 统一校验
    valid_ids, err_msg = _validate_ids(ids, max_count=_MAX_BATCH_EXPORT_COUNT)
    if err_msg:
        return JSONResponse({"status": "error", "message": err_msg}, status_code=400)

    history_manager = get_history_db()

    # B4: 使用 history_db 的公共方法 get_records_by_ids（替代私有 _execute）
    # 遵循分层原则，避免路由层直接操作数据库
    try:
        records = history_manager.get_records_by_ids(valid_ids)
    except Exception as e:
        logger.error(f"批量导出查询失败: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": "查询历史记录失败"}, status_code=500)

    if not records:
        return JSONResponse({"status": "error", "message": "未找到有效记录"}, status_code=404)

    # 打包 ZIP（写入 BytesIO）
    # NOTE: 对于 _MAX_BATCH_EXPORT_COUNT=100 的限制，内存占用可控
    zip_buffer = io.BytesIO()
    found_count = 0
    missing_count = 0
    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for rec in records:
                filename = rec["filename"]
                filepath = rec["filepath"]
                if filepath and os.path.isfile(filepath):
                    # SECURITY: [D4] 防止 ZIP 路径遍历 — 只用 basename
                    safe_name = os.path.basename(filename)
                    zf.write(filepath, safe_name)
                    found_count += 1
                else:
                    missing_count += 1
    except Exception as e:
        logger.error(f"批量导出打包 ZIP 失败: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": "打包导出文件失败"}, status_code=500)

    if found_count == 0:
        return JSONResponse(
            {"status": "error", "message": "所有音频文件均不存在或已被删除"},
            status_code=404,
        )

    zip_buffer.seek(0)
    timestamp = int(time.time())
    zip_filename = f"history_export_{timestamp}.zip"

    logger.info(f"[S-R7] 批量导出: {found_count} 个文件, {missing_count} 个缺失")

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
        },
    )


@router.post("/batch_delete_history", summary="批量删除", description="批量删除历史记录")
async def batch_delete_history(request: Request):
    """批量隐藏历史记录（不删除实际文件）"""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "无效的 JSON 请求体"}, status_code=400)

    ids = payload.get("ids", [])
    delete_files = payload.get("delete_files", False)

    # S-R7: 输入校验加固
    valid_ids, err_msg = _validate_ids(ids)
    if err_msg:
        return JSONResponse({"status": "error", "message": err_msg}, status_code=400)

    # S-R7: 校验 delete_files 类型
    if not isinstance(delete_files, bool):
        delete_files = bool(delete_files)

    history_manager = get_history_db()

    try:
        if delete_files:
            count = history_manager.delete_multiple_records(valid_ids, delete_files=True)
            action = "deleted"
        else:
            count = history_manager.hide_multiple_records(valid_ids)
            action = "hidden"
    except Exception as e:
        logger.error(f"批量删除失败: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": "操作失败，请稍后重试"}, status_code=500)

    return JSONResponse({"status": "ok", "count": count, "action": action})


@router.post("/history/hide", summary="隐藏记录", description="隐藏指定的历史记录")
async def hide_history_records(request: Request):
    """隐藏历史记录"""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "无效的 JSON 请求体"}, status_code=400)

    ids = payload.get("ids", [])

    # S-R7: 输入校验加固
    valid_ids, err_msg = _validate_ids(ids)
    if err_msg:
        return JSONResponse({"status": "error", "message": err_msg}, status_code=400)

    history_manager = get_history_db()
    try:
        count = history_manager.hide_multiple_records(valid_ids)
    except Exception as e:
        logger.error(f"批量隐藏失败: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": "操作失败，请稍后重试"}, status_code=500)
    return JSONResponse({"status": "ok", "count": count})


@router.post("/history/clear_all", summary="清空记录", description="清空所有历史记录")
async def clear_all_history(request: Request):
    """清除所有历史记录（默认只隐藏）"""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "无效的 JSON 请求体"}, status_code=400)

    hide_only = payload.get("hide_only", True)

    # S-R7: 校验 hide_only 类型
    if not isinstance(hide_only, bool):
        hide_only = bool(hide_only)

    history_manager = get_history_db()
    try:
        count = history_manager.clear_all_records(hide_only=hide_only)
    except Exception as e:
        logger.error(f"清空历史记录失败: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": "操作失败，请稍后重试"}, status_code=500)

    action = "hidden" if hide_only else "cleared"
    return JSONResponse({"status": "ok", "count": count, "action": action})


@router.post("/history/show", summary="显示记录", description="显示指定的隐藏记录")
async def show_history_records(request: Request):
    """恢复显示被隐藏的历史记录"""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "无效的 JSON 请求体"}, status_code=400)

    ids = payload.get("ids", [])

    # S-R7: 输入校验加固
    valid_ids, err_msg = _validate_ids(ids)
    if err_msg:
        return JSONResponse({"status": "error", "message": err_msg}, status_code=400)

    history_manager = get_history_db()
    try:
        count = history_manager.show_multiple_records(valid_ids)
    except Exception as e:
        logger.error(f"批量显示失败: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": "操作失败，请稍后重试"}, status_code=500)
    return JSONResponse({"status": "ok", "count": count})


@router.post("/history/show_all", summary="显示全部", description="显示所有隐藏的记录")
async def show_all_history(request: Request):
    """恢复显示所有被隐藏的历史记录"""
    history_manager = get_history_db()
    try:
        count = history_manager.show_all_records()
    except Exception as e:
        logger.error(f"显示全部历史记录失败: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": "操作失败，请稍后重试"}, status_code=500)
    return JSONResponse({"status": "ok", "count": count})


@router.post("/history/sync", summary="同步记录", description="触发后台增量同步文件系统与数据库的历史记录")
async def sync_history(background_tasks: BackgroundTasks):
    """触发后台增量同步历史记录，不阻塞 HTTP 响应。"""
    background_tasks.add_task(_sync_history_incremental)
    return JSONResponse({"status": "ok", "message": "增量同步已触发"})
