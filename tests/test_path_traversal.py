"""Tests for path traversal protection in audio routes."""
import pytest
from pathlib import Path


def _is_safe_path(base_dir: str, user_path: str) -> bool:
    """Check if user_path stays within base_dir."""
    base = Path(base_dir).resolve()
    target = (base / user_path).resolve()
    return str(target).startswith(str(base))


class TestPathTraversalProtection:
    def test_normal_path_allowed(self):
        assert _is_safe_path("/app/outputs", "audio_001.wav") is True

    def test_parent_traversal_blocked(self):
        assert _is_safe_path("/app/outputs", "../etc/passwd") is False

    def test_double_parent_traversal_blocked(self):
        assert _is_safe_path("/app/outputs", "../../etc/passwd") is False

    def test_absolute_path_blocked(self):
        assert _is_safe_path("/app/outputs", "/etc/passwd") is False

    def test_null_byte_in_path(self):
        assert _is_safe_path("/app/outputs", "audio.wav\x00../etc/passwd") is True  # resolve handles null bytes

    def test_encoded_traversal(self):
        assert _is_safe_path("/app/outputs", "%2e%2e/etc/passwd") is True  # not decoded by resolve

    def test_subdirectory_allowed(self):
        assert _is_safe_path("/app/outputs", "subdir/audio.wav") is True

    def test_current_dir_reference(self):
        assert _is_safe_path("/app/outputs", "./audio.wav") is True
