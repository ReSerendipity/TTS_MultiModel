"""Tests for audio processing utilities."""
import os
import sys
import pytest
import numpy as np

_BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

os.environ.setdefault("TTS_SKIP_MODEL_LOAD", "1")


class TestAudioProcessing:
    """Test audio processing functions."""

    def test_module_import(self):
        """Audio processing module can be imported."""
        from integrated_app.audio_processing import normalize_loudness
        assert normalize_loudness is not None

    def test_normalize_loudness_silence(self):
        """Normalizing silence doesn't crash."""
        from integrated_app.audio_processing import normalize_loudness
        silence = np.zeros(24000, dtype=np.float32)
        result = normalize_loudness(silence, target_lufs=-16.0)
        assert result is not None
        assert len(result) == len(silence)

    def test_normalize_loudness_sine(self):
        """Normalizing a sine wave produces non-zero output."""
        from integrated_app.audio_processing import normalize_loudness
        t = np.linspace(0, 1, 24000, dtype=np.float32)
        sine = np.sin(2 * np.pi * 440 * t) * 0.5
        result = normalize_loudness(sine, target_lufs=-16.0)
        assert result is not None
        assert np.max(np.abs(result)) > 0

    def test_normalize_loudness_preserves_shape(self):
        """Normalization preserves the general shape of the waveform."""
        from integrated_app.audio_processing import normalize_loudness
        t = np.linspace(0, 1, 24000, dtype=np.float32)
        sine = np.sin(2 * np.pi * 440 * t) * 0.5
        result = normalize_loudness(sine, target_lufs=-16.0)
        # Cross-correlation should be high (same shape)
        correlation = np.corrcoef(sine, result)[0, 1]
        assert correlation > 0.9


class TestAudioFormatDetection:
    """Test audio format detection via magic bytes."""

    def test_wav_magic_bytes(self):
        """WAV files are detected by RIFF header."""
        from integrated_app.routes.audio import _validate_audio_content
        assert _validate_audio_content(b"RIFF\x00\x00\x00\x00WAVEfmt ", ".wav") is True

    def test_mp3_id3_magic_bytes(self):
        """MP3 files with ID3 tag are detected."""
        from integrated_app.routes.audio import _validate_audio_content
        assert _validate_audio_content(b"ID3\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00", ".mp3") is True

    def test_flac_magic_bytes(self):
        """FLAC files are detected by fLaC header."""
        from integrated_app.routes.audio import _validate_audio_content
        assert _validate_audio_content(b"fLaC\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00", ".flac") is True

    def test_ogg_magic_bytes(self):
        """OGG files are detected by OggS header."""
        from integrated_app.routes.audio import _validate_audio_content
        assert _validate_audio_content(b"OggS\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00", ".ogg") is True

    def test_mismatch_rejected(self):
        """File with wrong magic bytes for claimed format is rejected."""
        from integrated_app.routes.audio import _validate_audio_content
        assert _validate_audio_content(b"RIFF\x00\x00\x00\x00WAVEfmt ", ".mp3") is False

    def test_unknown_format_allowed(self):
        """Unknown format is allowed (lenient validation)."""
        from integrated_app.routes.audio import _validate_audio_content
        assert _validate_audio_content(b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10", ".wav") is True
