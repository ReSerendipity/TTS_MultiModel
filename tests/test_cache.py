# -*- coding: utf-8 -*-
"""Tests for cache.py LRU logic."""
import pytest
from integrated_app.cache import LRUCache


class TestLRUCache:
    def test_put_and_get(self):
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        assert cache.get("a") == 1

    def test_eviction(self):
        cache = LRUCache(maxsize=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)  # "a" should be evicted
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_lru_order_update(self):
        cache = LRUCache(maxsize=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")  # access "a" to make it most recently used
        cache.put("c", 3)  # "b" should be evicted (least recently used)
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_overwrite(self):
        cache = LRUCache(maxsize=2)
        cache.put("a", 1)
        cache.put("a", 99)
        assert cache.get("a") == 99

    def test_stats(self):
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        cache.get("a")  # hit
        cache.get("b")  # miss
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_contains(self):
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        assert "a" in cache
        assert "b" not in cache

    def test_delete(self):
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        del cache["a"]
        assert cache.get("a") is None
