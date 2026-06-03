# -*- coding: utf-8 -*-
import os
import sys
import time
import pytest

_BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MODELSCOPE_OFFLINE", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")


class TestProgressManager:
    def test_start_and_complete(self):
        from integrated_app.progress import ProgressManager
        pm = ProgressManager()
        pm.start(total_segments=3, phase="测试中")
        assert pm._phase == "测试中"
        assert pm._total_segments == 3
        assert pm._is_complete is False
        pm.complete()
        assert pm._is_complete is True
        assert pm._current_segment == 3

    def test_advance_segment(self):
        from integrated_app.progress import ProgressManager
        pm = ProgressManager()
        pm.start(total_segments=3, phase="开始")
        pm.advance_segment(phase="第1段")
        assert pm._current_segment == 1
        pm.advance_segment(phase="第2段")
        assert pm._current_segment == 2
        pm.advance_segment(phase="第3段")
        assert pm._current_segment == 3

    def test_cancel(self):
        from integrated_app.progress import ProgressManager
        pm = ProgressManager()
        pm.start(total_segments=1, phase="开始")
        assert pm.is_cancelled() is False
        pm.cancel()
        assert pm.is_cancelled() is True

    def test_reset(self):
        from integrated_app.progress import ProgressManager
        pm = ProgressManager()
        pm.start(total_segments=3, phase="测试中")
        pm.advance_segment(phase="第1段")
        pm.complete()
        pm.reset()
        assert pm._phase == ""
        assert pm._current_segment == 0
        assert pm._is_complete is False
        assert pm._is_cancelled is False

    def test_update_phase(self):
        from integrated_app.progress import ProgressManager
        pm = ProgressManager()
        pm.start(total_segments=1, phase="初始")
        pm.update_phase("更新后")
        assert pm._phase == "更新后"

    def test_add_chars_processed(self):
        from integrated_app.progress import ProgressManager
        pm = ProgressManager()
        pm.start(total_segments=1, phase="开始")
        pm.add_chars_processed(100)
        pm.add_chars_processed(50)
        assert pm._total_chars_processed == 150

    def test_get_speed_stats(self):
        from integrated_app.progress import ProgressManager
        pm = ProgressManager()
        pm.start(total_segments=1, phase="开始")
        pm.add_chars_processed(100)
        stats = pm.get_speed_stats()
        assert stats["total_chars"] == 100
        assert stats["chars_per_sec"] >= 0

    def test_progress_html_complete(self):
        from integrated_app.progress import ProgressManager
        pm = ProgressManager()
        pm.start(total_segments=1, phase="完成")
        pm.complete()
        html = pm.get_progress_html()
        assert "100%" in html
        assert "生成完成" in html

    def test_progress_html_too_early(self):
        from integrated_app.progress import ProgressManager
        pm = ProgressManager()
        pm.start(total_segments=1, phase="刚开始")
        html = pm.get_progress_html()
        assert html == ""

    def test_format_duration(self):
        from integrated_app.progress import ProgressManager
        pm = ProgressManager()
        assert pm._format_duration(0) == "0秒"
        assert pm._format_duration(30) == "30秒"
        assert pm._format_duration(90) == "1分30秒"

    def test_schedule_reset(self):
        from integrated_app.progress import ProgressManager
        pm = ProgressManager()
        pm.start(total_segments=1, phase="测试")
        pm.complete()
        pm.schedule_reset(delay_seconds=0.1)
        time.sleep(0.3)
        assert pm._phase == ""
        assert pm._is_complete is False
