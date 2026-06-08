"""Tests for prompt cache with safe serialization."""
import os
import sys
import pytest
import tempfile
import time

_BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

os.environ.setdefault("TTS_SKIP_MODEL_LOAD", "1")


class TestPromptCacheSerialization:
    """Test prompt cache uses safe JSON serialization."""

    def test_cache_file_extension(self):
        """Cache files use .json extension."""
        from integrated_app.prompt_cache import _get_cache_file_path
        path = _get_cache_file_path("test_key")
        assert str(path).endswith(".json")

    def test_metadata_extension(self):
        """Metadata file uses .json extension."""
        from integrated_app.prompt_cache import _get_metadata_path
        path = _get_metadata_path()
        assert str(path).endswith(".json")

    def test_no_pickle_in_module(self):
        """Module does not expose pickle as a public attribute."""
        import integrated_app.prompt_cache as pc
        # pickle should not be in the module's public namespace
        public_attrs = [a for a in dir(pc) if not a.startswith('_')]
        assert 'pickle' not in public_attrs

    def test_serialize_dict(self):
        """Can serialize a simple dict."""
        from integrated_app.prompt_cache import _serialize_prompt_cache, _deserialize_prompt_cache
        data = {"key": "value", "number": 42}
        serialized = _serialize_prompt_cache(data)
        deserialized = _deserialize_prompt_cache(serialized)
        assert deserialized["key"] == "value"
        assert deserialized["number"] == 42

    def test_serialize_nested_dict(self):
        """Can serialize nested dicts."""
        from integrated_app.prompt_cache import _serialize_prompt_cache, _deserialize_prompt_cache
        data = {"outer": {"inner": [1, 2, 3]}}
        serialized = _serialize_prompt_cache(data)
        deserialized = _deserialize_prompt_cache(serialized)
        assert deserialized["outer"]["inner"] == [1, 2, 3]

    def test_serialize_list(self):
        """Can serialize a list."""
        from integrated_app.prompt_cache import _serialize_prompt_cache, _deserialize_prompt_cache
        data = [1, "two", 3.0, None]
        serialized = _serialize_prompt_cache(data)
        deserialized = _deserialize_prompt_cache(serialized)
        assert deserialized == [1, "two", 3.0, None]


class TestPromptCacheOperations:
    """Test prompt cache CRUD operations."""

    @pytest.fixture
    def cache_dir(self, tmp_path):
        """Create a temporary cache directory."""
        return str(tmp_path / "prompt_cache")

    def test_cache_directory_creation(self, cache_dir):
        """Cache directory is created on first use."""
        from integrated_app.prompt_cache import PromptCacheManager
        manager = PromptCacheManager(cache_dir=cache_dir)
        assert os.path.isdir(cache_dir)

    def test_save_and_load(self, cache_dir):
        """Can save and load a cache entry."""
        from integrated_app.prompt_cache import PromptCacheManager
        manager = PromptCacheManager(cache_dir=cache_dir)
        # Save
        manager.save_prompt_cache("test_key", {"data": "test_value"})
        # Load
        result = manager.load_cached_prompt("test_key")
        assert result is not None

    def test_cache_stats(self, cache_dir):
        """Can get cache statistics."""
        from integrated_app.prompt_cache import PromptCacheManager
        manager = PromptCacheManager(cache_dir=cache_dir)
        stats = manager.get_cache_stats()
        assert isinstance(stats, dict)
        assert "total_entries" in stats

    def test_clear_cache(self, cache_dir):
        """Can clear the cache."""
        from integrated_app.prompt_cache import PromptCacheManager
        manager = PromptCacheManager(cache_dir=cache_dir)
        manager.save_prompt_cache("clear_key", {"data": "value"})
        manager.clear_prompt_cache()
        stats = manager.get_cache_stats()
        assert stats["total_entries"] == 0
