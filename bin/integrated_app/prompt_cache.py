"""Prompt Cache 持久化模块

缓存参考音频的 prompt_cache 对象，避免重复编码。
使用文件内容哈希作为缓存键，支持 LRU 淘汰和 TTL 过期。
使用 JSON+binary 格式替代 pickle，提升安全性。
"""

import base64
import contextlib
import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

np: Any = None
try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

torch: Any = None
try:
    import torch

    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

logger = logging.getLogger("tts_multimodel")

_PROMPT_CACHE_DIR = Path("./prompt_cache")
_MAX_CACHE_ENTRIES = 50
_CACHE_TTL_SECONDS = 86400 * 7
_METADATA_VERSION = 2

_lock = threading.RLock()


def _serialize_value(obj):
    """将单个值转换为 JSON 可序列化的结构。"""
    if _HAS_TORCH and isinstance(obj, torch.Tensor):
        arr = obj.detach().cpu().numpy()
        return {
            "__type__": "tensor",
            "data": base64.b64encode(arr.tobytes()).decode("ascii"),
            "dtype": str(arr.dtype),
            "shape": list(arr.shape),
        }
    if _HAS_NUMPY and isinstance(obj, np.ndarray):
        return {
            "__type__": "ndarray",
            "data": base64.b64encode(obj.tobytes()).decode("ascii"),
            "dtype": str(obj.dtype),
            "shape": list(obj.shape),
        }
    if isinstance(obj, dict):
        return {k: _serialize_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_value(item) for item in obj]
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return {"__type__": "str", "data": str(obj)}


def _deserialize_value(data):
    """从 JSON 反序列化结构中还原 Python 对象。"""
    if isinstance(data, dict):
        type_tag = data.get("__type__")
        if type_tag == "tensor" and _HAS_NUMPY and _HAS_TORCH:
            raw = base64.b64decode(data["data"])
            arr = np.frombuffer(raw, dtype=np.dtype(data["dtype"])).reshape(data["shape"]).copy()
            return torch.from_numpy(arr)
        if type_tag == "ndarray" and _HAS_NUMPY:
            raw = base64.b64decode(data["data"])
            return np.frombuffer(raw, dtype=np.dtype(data["dtype"])).reshape(data["shape"]).copy()
        if type_tag == "str":
            return data["data"]
        return {k: _deserialize_value(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_deserialize_value(item) for item in data]
    return data


def _serialize_prompt_cache(obj):
    """将 prompt_cache 对象序列化为 JSON 可保存的字典。"""
    return _serialize_value(obj)


def _deserialize_prompt_cache(data):
    """从 JSON 字典反序列化还原 prompt_cache 对象。"""
    return _deserialize_value(data)


def _ensure_cache_dir():
    _PROMPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_prompt_cache_key(audio_path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(audio_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        h.update(audio_path.encode("utf-8"))
    return h.hexdigest()[:16]


def _get_cache_file_path(cache_key: str) -> Path:
    return _PROMPT_CACHE_DIR / f"{cache_key}.json"


def _get_old_cache_file_path(cache_key: str) -> Path:
    return _PROMPT_CACHE_DIR / f"{cache_key}.pkl"


def _get_metadata_path() -> Path:
    return _PROMPT_CACHE_DIR / "metadata.json"


def _get_old_metadata_path() -> Path:
    return _PROMPT_CACHE_DIR / "metadata.pkl"


def _migrate_legacy_metadata() -> dict:
    """尝试从旧版 metadata.pkl 迁移元数据到新格式。"""
    old_path = _get_old_metadata_path()
    if not old_path.exists():
        return {}
    try:
        import pickle as _pickle

        with open(old_path, "rb") as f:
            metadata = _pickle.load(f)
        if isinstance(metadata, dict):
            metadata["version"] = _METADATA_VERSION
            _save_metadata(metadata)
            with contextlib.suppress(OSError):
                old_path.unlink()
            logger.info("已将元数据从 metadata.pkl 迁移为 metadata.json")
            return metadata
    except Exception as e:
        logger.warning(f"迁移旧版元数据失败: {e}")
    return {}


def _load_metadata() -> dict:
    meta_path = _get_metadata_path()
    if meta_path.exists():
        try:
            with open(meta_path, encoding="utf-8") as f:
                metadata = json.load(f)
            if not isinstance(metadata, dict):
                return {}
            return metadata
        except (json.JSONDecodeError, OSError):
            return {}
    # 尝试从旧格式迁移
    return _migrate_legacy_metadata()


def _save_metadata(metadata: dict):
    meta_path = _get_metadata_path()
    try:
        metadata["version"] = _METADATA_VERSION
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, OSError, TypeError) as e:
        logger.warning(f"保存缓存元数据失败: {e}")


def _cleanup_expired(metadata: dict):
    now = time.time()
    expired_keys = [
        k for k, v in metadata.items() if k != "version" and now - v.get("created_at", 0) > _CACHE_TTL_SECONDS
    ]
    for key in expired_keys:
        cache_file = _get_cache_file_path(key)
        if cache_file.exists():
            with contextlib.suppress(OSError):
                cache_file.unlink()
        del metadata[key]
    if expired_keys:
        logger.info(f"清理了 {len(expired_keys)} 个过期缓存条目")
        _save_metadata(metadata)
    return metadata


def _evict_lru(metadata: dict) -> dict:
    entries = {k: v for k, v in metadata.items() if k != "version"}
    while len(entries) >= _MAX_CACHE_ENTRIES:
        oldest_key = min(entries, key=lambda k: entries[k].get("last_accessed", 0))
        cache_file = _get_cache_file_path(oldest_key)
        if cache_file.exists():
            with contextlib.suppress(OSError):
                cache_file.unlink()
        del metadata[oldest_key]
        del entries[oldest_key]
        logger.info(f"LRU 淘汰缓存条目: {oldest_key}")
    _save_metadata(metadata)
    return metadata


def _migrate_legacy_cache(cache_key: str) -> Any | None:
    """尝试从旧版 .pkl 缓存文件迁移到新 JSON 格式。"""
    old_path = _get_old_cache_file_path(cache_key)
    if not old_path.exists():
        return None
    try:
        import pickle as _pickle

        with open(old_path, "rb") as f:
            prompt_cache = _pickle.load(f)
        # 保存为新格式
        new_path = _get_cache_file_path(cache_key)
        serialized = _serialize_prompt_cache(prompt_cache)
        with open(new_path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, ensure_ascii=False)
        # 删除旧文件
        with contextlib.suppress(OSError):
            old_path.unlink()
        logger.info(f"已将缓存 {cache_key} 从 .pkl 迁移为 .json")
        return prompt_cache
    except Exception as e:
        logger.warning(f"迁移旧版缓存失败 ({cache_key}): {e}")
        return None


def load_cached_prompt(audio_path: str) -> Any | None:
    with _lock:
        _ensure_cache_dir()
        cache_key = _get_prompt_cache_key(audio_path)
        cache_file = _get_cache_file_path(cache_key)

        # 如果新格式文件不存在，尝试从旧格式迁移
        if not cache_file.exists():
            migrated = _migrate_legacy_cache(cache_key)
            if migrated is not None:
                # 迁移成功后更新元数据
                metadata = _load_metadata()
                metadata = _cleanup_expired(metadata)
                if cache_key in metadata:
                    now = time.time()
                    metadata[cache_key]["last_accessed"] = now
                    metadata[cache_key]["access_count"] = metadata[cache_key].get("access_count", 0) + 1
                    _save_metadata(metadata)
                    logger.info(
                        f"Prompt Cache 命中(迁移): {audio_path} (访问 {metadata[cache_key]['access_count']} 次)"
                    )
                return migrated
            return None

        metadata = _load_metadata()
        metadata = _cleanup_expired(metadata)

        if cache_key not in metadata:
            return None

        now = time.time()
        metadata[cache_key]["last_accessed"] = now
        metadata[cache_key]["access_count"] = metadata[cache_key].get("access_count", 0) + 1
        _save_metadata(metadata)

        try:
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
            prompt_cache = _deserialize_prompt_cache(data)
            logger.info(f"Prompt Cache 命中: {audio_path} (访问 {metadata[cache_key]['access_count']} 次)")
            return prompt_cache
        except (json.JSONDecodeError, OSError, Exception) as e:
            logger.warning(f"读取缓存失败: {e}")
            if cache_file.exists():
                with contextlib.suppress(OSError):
                    cache_file.unlink()
            if cache_key in metadata:
                del metadata[cache_key]
                _save_metadata(metadata)
            return None


def save_prompt_cache(audio_path: str, prompt_cache: Any):
    with _lock:
        _ensure_cache_dir()
        cache_key = _get_prompt_cache_key(audio_path)
        cache_file = _get_cache_file_path(cache_key)

        metadata = _load_metadata()
        metadata = _cleanup_expired(metadata)
        metadata = _evict_lru(metadata)

        now = time.time()
        metadata[cache_key] = {
            "audio_path": audio_path,
            "created_at": now,
            "last_accessed": now,
            "access_count": 1,
            "file_size": cache_file.stat().st_size if cache_file.exists() else 0,
        }

        try:
            serialized = _serialize_prompt_cache(prompt_cache)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(serialized, f, ensure_ascii=False)
            metadata[cache_key]["file_size"] = cache_file.stat().st_size
            _save_metadata(metadata)
            logger.info(f"Prompt Cache 已保存: {audio_path}")
        except (json.JSONDecodeError, OSError, TypeError, Exception) as e:
            logger.warning(f"保存缓存失败: {e}")


def clear_prompt_cache():
    with _lock:
        _ensure_cache_dir()
        metadata = _load_metadata()
        cleared = 0
        for key in list(metadata.keys()):
            if key == "version":
                continue
            cache_file = _get_cache_file_path(key)
            old_cache_file = _get_old_cache_file_path(key)
            for f in (cache_file, old_cache_file):
                if f.exists():
                    with contextlib.suppress(OSError):
                        f.unlink()
                        cleared += 1
        meta_path = _get_metadata_path()
        old_meta_path = _get_old_metadata_path()
        for f in (meta_path, old_meta_path):
            if f.exists():
                with contextlib.suppress(OSError):
                    f.unlink()
        logger.info(f"Prompt Cache 已清空，共清理 {cleared} 个条目")


def get_cache_stats() -> dict:
    with _lock:
        _ensure_cache_dir()
        metadata = _load_metadata()
        total_size = 0
        for key in metadata:
            if key == "version":
                continue
            cache_file = _get_cache_file_path(key)
            if cache_file.exists():
                total_size += cache_file.stat().st_size
        return {
            "entries": len({k for k in metadata if k != "version"}),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "max_entries": _MAX_CACHE_ENTRIES,
            "ttl_seconds": _CACHE_TTL_SECONDS,
            "cache_dir": str(_PROMPT_CACHE_DIR),
        }
