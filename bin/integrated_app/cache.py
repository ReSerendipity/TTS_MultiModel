"""LRU cache module with adaptive GPU-aware capacity management.

Provides LRUCache for fixed-capacity caching and AdaptiveLRUCache
that automatically adjusts capacity based on GPU memory utilization.
"""

import logging
import threading
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger("tts_multimodel")


class LRUCache:
    """Least Recently Used cache with fixed capacity.

    Uses OrderedDict to track access order. When capacity is exceeded,
    the least recently accessed item is evicted first.

    Attributes:
        _cache: OrderedDict storing cached items.
        _maxsize: Maximum number of items the cache can hold.
        _hits: Number of successful cache lookups.
        _misses: Number of failed cache lookups.
    """

    def __init__(self, maxsize: int = 50) -> None:
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Retrieve a cached item by key.

        Moves the accessed item to the end (most recently used position).

        Args:
            key: Cache key to look up.

        Returns:
            Cached value if found, None otherwise.
        """
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def put(self, key: str, value: Any) -> None:
        """Insert or update a cached item.

        Moves existing key to the end. If cache exceeds maxsize,
        evicts least recently used items until within capacity.

        Args:
            key: Cache key.
            value: Value to cache.
        """
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._cache

    def __delitem__(self, key: str) -> None:
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def get_stats(self) -> dict:
        """Return cache performance statistics.

        Returns:
            Dictionary with hits, misses, hit_rate (percentage),
            current size and maxsize.
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 1),
                "size": len(self._cache),
                "maxsize": self._maxsize,
            }

    def reset_stats(self) -> None:
        """Reset hit and miss counters to zero."""
        with self._lock:
            self._hits = 0
            self._misses = 0


class AdaptiveLRUCache(LRUCache):
    """LRU cache with adaptive capacity based on GPU memory usage.

    Automatically adjusts cache size inversely proportional to GPU
    memory utilization. High GPU usage triggers cache shrinkage
    to free system memory, low usage allows cache expansion.

    Capacity mapping:
        GPU > 90% -> 5 items
        GPU > 75% -> 10 items
        GPU > 50% -> 15 items
        Otherwise  -> 20 items

    Attributes:
        _CAPACITY_MAP: List of (gpu_threshold, cache_capacity) tuples.
        _adapt_lock: Thread lock for capacity adjustment.
    """

    _CAPACITY_MAP = [
        (90, 5),
        (75, 10),
        (50, 15),
        (0, 20),
    ]

    _MEMORY_LIMIT_MB = 512

    def __init__(self, default_maxsize: int = 15, adapt_interval: float = 30.0) -> None:
        super().__init__(maxsize=default_maxsize)
        self._adapt_lock = threading.Lock()
        self._adapt_interval = adapt_interval
        self._last_adapt_time = 0.0
        self._put_count = 0
        self._adapt_every_n = 10
        self._total_memory_estimate = 0
        self._eviction_count = 0

    @staticmethod
    def _estimate_item_size(value: Any) -> int:
        """Estimate the memory footprint of a cached value in bytes.

        Args:
            value: The cached value to estimate.

        Returns:
            Estimated size in bytes.
        """
        try:
            if isinstance(value, tuple) and len(value) > 0:
                first = value[0]
                if hasattr(first, "nbytes"):
                    total = first.nbytes
                    for item in value[1:]:
                        if hasattr(item, "nbytes"):
                            total += item.nbytes
                        else:
                            total += getattr(item, "__sizeof__", lambda: 1024)()
                    return total
            if hasattr(value, "__sizeof__"):
                return value.__sizeof__()
        except Exception:
            pass
        return 1024

    @staticmethod
    def _get_gpu_memory_percent() -> float:
        """Query current GPU memory allocation percentage via GPUBackendManager.

        Returns:
            Memory usage percentage (0.0 to 100.0), or 0.0 if GPU unavailable.
        """
        try:
            from .gpu_backend import GPUBackendManager

            if not GPUBackendManager.is_available():
                return 0.0

            mem_info = GPUBackendManager.get_memory_info()
            total = mem_info[0]
            allocated = mem_info[1]

            if total == 0:
                return 0.0
            return allocated / total * 100
        except Exception:
            return 0.0

    def _calculate_target_capacity(self) -> int:
        """Determine cache capacity based on current GPU memory usage.

        Returns:
            Target cache capacity (number of items).
        """
        gpu_pct = self._get_gpu_memory_percent()
        for threshold, capacity in self._CAPACITY_MAP:
            if gpu_pct > threshold:
                return capacity
        return 20

    def adapt_capacity(self) -> int:
        """Adjust cache capacity based on GPU memory and evict excess items.

        Returns:
            New cache capacity after adjustment.
        """
        target = self._calculate_target_capacity()
        with self._adapt_lock:
            old_max = self._maxsize
            self._maxsize = target
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)
            if old_max != target:
                logger.info(
                    f"[AdaptiveCache] 容量已调整: {old_max} -> {target} "
                    f"(GPU 使用率: {self._get_gpu_memory_percent():.1f}%)"
                )
        return target

    def put(self, key: str, value: Any) -> None:
        size = self._estimate_item_size(value)
        with self._adapt_lock:
            if key in self._cache:
                old_value = self._cache[key]
                self._total_memory_estimate -= self._estimate_item_size(old_value)
            self._total_memory_estimate += size
        super().put(key, value)
        with self._adapt_lock:
            memory_limit = self._MEMORY_LIMIT_MB * 1024 * 1024
            while self._total_memory_estimate > memory_limit and len(self._cache) > 0:
                evicted_key, evicted_value = self._cache.popitem(last=False)
                evicted_size = self._estimate_item_size(evicted_value)
                self._total_memory_estimate -= evicted_size
                self._eviction_count += 1
        self._put_count += 1
        now = time.monotonic()
        if (
            len(self._cache) >= self._maxsize
            or now - self._last_adapt_time >= self._adapt_interval
            or self._put_count >= self._adapt_every_n
        ):
            self.adapt_capacity()
            self._last_adapt_time = now
            self._put_count = 0

    def __delitem__(self, key: str) -> None:
        with self._adapt_lock:
            if key in self._cache:
                self._total_memory_estimate -= self._estimate_item_size(self._cache[key])
        super().__delitem__(key)

    def clear(self) -> None:
        """Clear all cached items and reset statistics."""
        with self._adapt_lock:
            self._cache.clear()
            self._total_memory_estimate = 0
            self._eviction_count = 0
        self.reset_stats()

    def get_stats(self) -> dict:
        """Return cache performance statistics including memory tracking.

        Returns:
            Dictionary with hits, misses, hit_rate, size, maxsize,
            memory_estimate_mb, eviction_count, and avg_item_size_kb.
        """
        with self._adapt_lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0
            memory_mb = self._total_memory_estimate / (1024 * 1024)
            cache_size = len(self._cache)
            avg_kb = (self._total_memory_estimate / cache_size / 1024) if cache_size > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 1),
                "size": cache_size,
                "maxsize": self._maxsize,
                "memory_estimate_mb": round(memory_mb, 2),
                "eviction_count": self._eviction_count,
                "avg_item_size_kb": round(avg_kb, 2),
            }
