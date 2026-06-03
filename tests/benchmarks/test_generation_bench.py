import pytest
import time
import numpy as np


class TestGenerationBenchmarks:
    def test_text_splitting_performance(self):
        from integrated_app.generation import split_text_for_tts
        long_text = "这是一段测试文本。" * 100
        start = time.monotonic()
        for _ in range(100):
            split_text_for_tts(long_text, max_chars=200)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"Text splitting too slow: {elapsed:.3f}s for 100 iterations"

    def test_audio_merge_performance(self):
        from integrated_app.generation import merge_audio_segments
        segments = [np.random.randn(24000).astype(np.float32) for _ in range(10)]
        start = time.monotonic()
        for _ in range(50):
            merge_audio_segments(segments, 24000, silence_duration=0.3)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"Audio merge too slow: {elapsed:.3f}s for 50 iterations"

    def test_cache_operations_performance(self):
        from integrated_app.cache import LRUCache
        cache = LRUCache(maxsize=100)
        start = time.monotonic()
        for i in range(1000):
            cache.put(f"key_{i}", f"value_{i}")
            cache.get(f"key_{i}")
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Cache operations too slow: {elapsed:.3f}s for 1000 iterations"
