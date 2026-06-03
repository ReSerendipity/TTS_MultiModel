# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import numpy as np
import pytest

_BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MODELSCOPE_OFFLINE", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")


class TestSplitTextForTTS:
    def test_short_text_no_split(self):
        from integrated_app.generation import split_text_for_tts
        text = "你好世界"
        result = split_text_for_tts(text, max_chars=200)
        assert result == ["你好世界"]

    def test_empty_text(self):
        from integrated_app.generation import split_text_for_tts
        result = split_text_for_tts("", max_chars=200)
        assert result == [""]

    def test_split_on_chinese_period(self):
        from integrated_app.generation import split_text_for_tts
        text = "这是第一句话。这是第二句话。这是第三句话。"
        result = split_text_for_tts(text, max_chars=15)
        assert len(result) >= 2
        for seg in result:
            assert len(seg) <= 20

    def test_split_on_comma(self):
        from integrated_app.generation import split_text_for_tts
        text = "第一部分，第二部分，第三部分，第四部分"
        result = split_text_for_tts(text, max_chars=10)
        assert len(result) >= 2

    def test_split_on_english_period(self):
        from integrated_app.generation import split_text_for_tts
        text = "Hello world. This is a test. Another sentence here."
        result = split_text_for_tts(text, max_chars=20)
        assert len(result) >= 2

    def test_no_natural_break_forces_split(self):
        from integrated_app.generation import split_text_for_tts
        text = "abcdefghij"
        result = split_text_for_tts(text, max_chars=5)
        assert len(result) >= 2

    def test_exact_max_chars(self):
        from integrated_app.generation import split_text_for_tts
        text = "12345"
        result = split_text_for_tts(text, max_chars=5)
        assert result == ["12345"]

    def test_single_char_over(self):
        from integrated_app.generation import split_text_for_tts
        text = "123456"
        result = split_text_for_tts(text, max_chars=5)
        assert len(result) >= 2

    def test_chinese_exclamation(self):
        from integrated_app.generation import split_text_for_tts
        text = "太好了！真的吗？当然！"
        result = split_text_for_tts(text, max_chars=8)
        assert len(result) >= 2

    def test_mixed_punctuation_priority(self):
        from integrated_app.generation import split_text_for_tts
        text = "第一句。第二句，第三句"
        result = split_text_for_tts(text, max_chars=6)
        assert len(result) >= 2


class TestMergeAudioSegments:
    def test_empty_list(self):
        from integrated_app.generation import merge_audio_segments
        result, sr = merge_audio_segments([], 48000)
        assert result is None
        assert sr == 48000

    def test_single_segment(self):
        from integrated_app.generation import merge_audio_segments
        seg = np.random.randn(48000).astype(np.float32) * 0.5
        result, sr = merge_audio_segments([seg], 48000)
        assert result is not None
        assert len(result) == 48000
        assert sr == 48000

    def test_two_segments_with_silence(self):
        from integrated_app.generation import merge_audio_segments
        seg1 = np.random.randn(48000).astype(np.float32) * 0.5
        seg2 = np.random.randn(48000).astype(np.float32) * 0.5
        result, sr = merge_audio_segments([seg1, seg2], 48000, silence_duration=0.3)
        silence_samples = int(48000 * 0.3)
        expected_len = 48000 + silence_samples + 48000
        assert len(result) == expected_len

    def test_int16_input_normalized(self):
        from integrated_app.generation import merge_audio_segments
        seg = (np.random.randn(48000) * 16000).astype(np.int16)
        result, sr = merge_audio_segments([seg], 48000)
        assert result is not None
        assert np.max(np.abs(result)) <= 1.0

    def test_stereo_input_converted(self):
        from integrated_app.generation import merge_audio_segments
        seg = np.random.randn(48000, 2).astype(np.float32) * 0.5
        result, sr = merge_audio_segments([seg], 48000)
        assert result is not None
        assert result.ndim == 1

    def test_custom_silence_duration(self):
        from integrated_app.generation import merge_audio_segments
        seg1 = np.zeros(1000, dtype=np.float32)
        seg2 = np.zeros(1000, dtype=np.float32)
        result, sr = merge_audio_segments([seg1, seg2], 48000, silence_duration=0.5)
        silence_samples = int(48000 * 0.5)
        expected_len = 1000 + silence_samples + 1000
        assert len(result) == expected_len


class TestSaveAudio:
    def test_save_wav(self):
        from integrated_app.generation import save_audio
        with tempfile.TemporaryDirectory() as tmpdir:
            import integrated_app.config as cfg
            original = cfg.SAVE_DIR
            cfg.SAVE_DIR = tmpdir
            try:
                wav = np.random.randn(48000).astype(np.float32) * 0.5
                path, name = save_audio(wav, 48000, prefix="test")
                assert os.path.exists(path)
                assert name.startswith("test_")
                assert name.endswith(".wav")
            finally:
                cfg.SAVE_DIR = original


class TestFindBestSplitPoint:
    def test_chinese_period(self):
        from integrated_app.generation import _find_best_split_point
        text = "你好世界。再见"
        idx = _find_best_split_point(text)
        assert idx == text.index("。")

    def test_no_punctuation(self):
        from integrated_app.generation import _find_best_split_point
        text = "没有标点的文本"
        idx = _find_best_split_point(text)
        assert idx == 0

    def test_english_period(self):
        from integrated_app.generation import _find_best_split_point
        text = "Hello world. Goodbye"
        idx = _find_best_split_point(text)
        assert idx == text.index(".")
