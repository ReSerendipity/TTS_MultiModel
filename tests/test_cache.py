# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch, MagicMock


class TestLRUCache:
    def test_put_and_get(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        cache.put("b", 2)
        assert cache.get("a") == 1
        assert cache.get("b") == 2

    def test_get_miss(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=3)
        assert cache.get("nonexistent") is None

    def test_eviction(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_lru_order_update(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=2)
        cache.put("a", 1)
        cache.put("b", 2)
        _ = cache.get("a")
        cache.put("c", 3)
        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_eviction_order(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.put("d", 4)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_lru_access_updates_order(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.get("a")
        cache.put("d", 4)
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_cache_stats(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=5)
        cache.put("a", 1)
        cache.get("a")
        cache.get("b")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_clear(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=5)
        cache.put("a", 1)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get_stats()["size"] == 0

    def test_overwrite_existing(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        cache.put("a", 99)
        assert cache.get("a") == 99

    def test_contains(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        assert "a" in cache
        assert "b" not in cache

    def test_delete(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        del cache["a"]
        assert cache.get("a") is None

    def test_stats(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        _ = cache.get("a")
        _ = cache.get("b")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 50.0
        assert stats["size"] == 1
        assert stats["maxsize"] == 3

    def test_reset_stats(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        _ = cache.get("a")
        cache.reset_stats()
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0


class TestAdaptiveLRUCache:
    def test_default_capacity(self):
        from integrated_app.cache import AdaptiveLRUCache
        cache = AdaptiveLRUCache(default_maxsize=10)
        stats = cache.get_stats()
        assert stats["maxsize"] == 10

    @patch("integrated_app.cache.AdaptiveLRUCache._get_gpu_memory_percent", return_value=0.0)
    def test_low_gpu_expands_capacity(self, mock_gpu):
        from integrated_app.cache import AdaptiveLRUCache
        cache = AdaptiveLRUCache(default_maxsize=10)
        new_cap = cache.adapt_capacity()
        assert new_cap == 20

    @patch("integrated_app.cache.AdaptiveLRUCache._get_gpu_memory_percent", return_value=95.0)
    def test_high_gpu_shrinks_capacity(self, mock_gpu):
        from integrated_app.cache import AdaptiveLRUCache
        cache = AdaptiveLRUCache(default_maxsize=10)
        new_cap = cache.adapt_capacity()
        assert new_cap == 5

    @patch("integrated_app.cache.AdaptiveLRUCache._get_gpu_memory_percent", return_value=80.0)
    def test_medium_gpu_moderate_capacity(self, mock_gpu):
        from integrated_app.cache import AdaptiveLRUCache
        cache = AdaptiveLRUCache(default_maxsize=10)
        new_cap = cache.adapt_capacity()
        assert new_cap == 10

    def test_clear(self):
        from integrated_app.cache import AdaptiveLRUCache
        cache = AdaptiveLRUCache(default_maxsize=10)
        cache.put("a", 1)
        cache.clear()
        assert cache.get("a") is None
