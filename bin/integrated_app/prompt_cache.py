"""Prompt Cache 持久化模块

缓存参考音频的 prompt_cache 对象，避免重复编码。
使用文件内容哈希作为缓存键，支持 LRU 淘汰和 TTL 过期。
"""

import hashlib
import logging
import pickle
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("tts_multimodel")

_PROMPT_CACHE_DIR = Path("./prompt_cache")
_MAX_CACHE_ENTRIES = 50
_CACHE_TTL_SECONDS = 86400 * 7

_lock = threading.RLock()

def _ensure_cache_dir():
    _PROMPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _get_prompt_cache_key(audio_path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(audio_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
    except OSError:
        h.update(audio_path.encode('utf-8'))
    return h.hexdigest()[:16]

def _get_cache_file_path(cache_key: str) -> Path:
    return _PROMPT_CACHE_DIR / f"{cache_key}.pkl"

def _get_metadata_path() -> Path:
    return _PROMPT_CACHE_DIR / "metadata.pkl"

def _load_metadata() -> dict:
    meta_path = _get_metadata_path()
    if meta_path.exists():
        try:
            with open(meta_path, 'rb') as f:
                return pickle.load(f)
        except (pickle.PickleError, OSError):
            return {}
    return {}

def _save_metadata(metadata: dict):
    meta_path = _get_metadata_path()
    try:
        with open(meta_path, 'wb') as f:
            pickle.dump(metadata, f)
    except (pickle.PickleError, OSError) as e:
        logger.warning(f"保存缓存元数据失败: {e}")

def _cleanup_expired(metadata: dict):
    now = time.time()
    expired_keys = [
        k for k, v in metadata.items()
        if now - v.get("created_at", 0) > _CACHE_TTL_SECONDS
    ]
    for key in expired_keys:
        cache_file = _get_cache_file_path(key)
        if cache_file.exists():
            try:
                cache_file.unlink()
            except OSError:
                pass
        del metadata[key]
    if expired_keys:
        logger.info(f"清理了 {len(expired_keys)} 个过期缓存条目")
        _save_metadata(metadata)
    return metadata

def _evict_lru(metadata: dict) -> dict:
    while len(metadata) >= _MAX_CACHE_ENTRIES:
        oldest_key = min(metadata, key=lambda k: metadata[k].get("last_accessed", 0))
        cache_file = _get_cache_file_path(oldest_key)
        if cache_file.exists():
            try:
                cache_file.unlink()
            except OSError:
                pass
        del metadata[oldest_key]
        logger.info(f"LRU 淘汰缓存条目: {oldest_key}")
    _save_metadata(metadata)
    return metadata

def load_cached_prompt(audio_path: str) -> Any | None:
    with _lock:
        _ensure_cache_dir()
        cache_key = _get_prompt_cache_key(audio_path)
        cache_file = _get_cache_file_path(cache_key)

        if not cache_file.exists():
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
            with open(cache_file, 'rb') as f:
                prompt_cache = pickle.load(f)
            logger.info(f"Prompt Cache 命中: {audio_path} (访问 {metadata[cache_key]['access_count']} 次)")
            return prompt_cache
        except (pickle.PickleError, OSError) as e:
            logger.warning(f"读取缓存失败: {e}")
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except OSError:
                    pass
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
            with open(cache_file, 'wb') as f:
                pickle.dump(prompt_cache, f)
            metadata[cache_key]["file_size"] = cache_file.stat().st_size
            _save_metadata(metadata)
            logger.info(f"Prompt Cache 已保存: {audio_path}")
        except (pickle.PickleError, OSError) as e:
            logger.warning(f"保存缓存失败: {e}")

def clear_prompt_cache():
    with _lock:
        _ensure_cache_dir()
        metadata = _load_metadata()
        cleared = 0
        for key in list(metadata.keys()):
            cache_file = _get_cache_file_path(key)
            if cache_file.exists():
                try:
                    cache_file.unlink()
                    cleared += 1
                except OSError:
                    pass
        meta_path = _get_metadata_path()
        if meta_path.exists():
            try:
                meta_path.unlink()
            except OSError:
                pass
        logger.info(f"Prompt Cache 已清空，共清理 {cleared} 个条目")

def get_cache_stats() -> dict:
    with _lock:
        _ensure_cache_dir()
        metadata = _load_metadata()
        total_size = 0
        for key in metadata:
            cache_file = _get_cache_file_path(key)
            if cache_file.exists():
                total_size += cache_file.stat().st_size
        return {
            "entries": len(metadata),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "max_entries": _MAX_CACHE_ENTRIES,
            "ttl_seconds": _CACHE_TTL_SECONDS,
            "cache_dir": str(_PROMPT_CACHE_DIR),
        }
