"""Progress tracking module.

Manages generation progress tracking and renders HTML progress bars
for frontend rendering via HTMX partial updates.
"""

import threading
import time


class ProgressManager:
    """Manages generation progress tracking and renders HTML progress bars.

    Tracks segment-by-segment progress with phase labels, timing,
    byte throughput, and character throughput. Generates HTML for
    frontend rendering via HTMX partial updates.

    Supports single-segment mode (animated progress 5%->95%) and
    multi-segment mode (explicit segment counting).

    Attributes:
        _phase: Current progress phase label (e.g., "推理中", "完成").
        _current_segment: Number of completed segments.
        _total_segments: Total number of segments to process.
        _start_time: Timestamp when progress tracking started.
        _segment_times: Rolling history of per-segment durations.
        _max_history: Maximum number of segment times to retain for averaging.
        _total_bytes_processed: Cumulative bytes processed across all segments.
        _last_segment_bytes: Bytes in the most recently processed segment.
        _is_complete: Whether all segments have been processed.
        _is_cancelled: Whether the operation has been cancelled.
        _total_chars_processed: Cumulative characters processed.
    """

    def __init__(self, max_history=5):
        self._phase = ""
        self._current_segment = 0
        self._total_segments = 1
        self._start_time = 0
        self._segment_times = []
        self._max_history = max_history
        self._lock = threading.RLock()
        self._total_bytes_processed = 0
        self._last_segment_bytes = 0
        self._is_complete = False
        self._is_cancelled = False
        self._total_chars_processed = 0

    def _notify_sse(self):
        """通知 SSE 事件总线状态已变化。"""
        try:
            from .routes.sse import event_bus

            event_bus.notify()
        except Exception:
            pass

    def start(self, total_segments=1, phase="准备中"):
        """Initialize progress tracking for a new generation task.

        Args:
            total_segments: Expected number of segments to process.
            phase: Initial phase label.
        """
        with self._lock:
            self._phase = phase
            self._current_segment = 0
            self._total_segments = total_segments
            self._start_time = time.time()
            self._segment_times = []
            self._total_bytes_processed = 0
            self._last_segment_bytes = 0
            self._is_complete = False
            self._is_cancelled = False
            self._total_chars_processed = 0
        self._notify_sse()

    def update_phase(self, phase):
        """Update the current phase label.

        Args:
            phase: New phase label string.
        """
        with self._lock:
            self._phase = phase
        self._notify_sse()

    def advance_segment(self, phase="推理中", segment_bytes=0):
        """Mark a segment as completed and record timing data.

        Args:
            phase: Phase label for the next segment.
            segment_bytes: Byte size of the completed segment.
        """
        with self._lock:
            self._is_complete = False
            if self._current_segment > 0:
                elapsed = time.time() - self._start_time
                self._segment_times.append(elapsed / self._current_segment)
                if len(self._segment_times) > self._max_history:
                    self._segment_times.pop(0)
            if segment_bytes > 0:
                self._total_bytes_processed += segment_bytes
                self._last_segment_bytes = segment_bytes
            self._current_segment += 1
            self._phase = phase
        self._notify_sse()

    def set_total_bytes(self, total_bytes):
        """Override the total bytes processed counter.

        Args:
            total_bytes: New total bytes value.
        """
        with self._lock:
            self._total_bytes_processed = total_bytes

    def get_progress_html(self):
        """Render HTML progress bar with phase, percentage, and timing info.

        Returns:
            HTML string for the progress bar, or empty string if
            progress is too early to display (<0.5s elapsed).
        """
        with self._lock:
            if self._is_complete:
                return (
                    '<div class="tts-progress-bar">'
                    '<div class="tts-progress-fill tts-progress-complete" style="width:100%"></div>'
                    "</div>"
                    '<div class="tts-progress-info tts-progress-complete-info">'
                    '<span class="tts-progress-phase">生成完成</span>'
                    '<span class="tts-progress-percentage">100%</span>'
                    "</div>"
                )
            if self._total_segments <= 0:
                return ""
            if self._total_segments == 1:
                elapsed = time.time() - self._start_time if self._start_time > 0 else 0
                estimated_total = 20.0
                raw_progress = elapsed / estimated_total
                pct = max(5, min(95, int(5 + raw_progress * 90)))
                remaining = max(0, estimated_total - elapsed)
                speed_items = self._get_speed_info(elapsed)
                phase_display = self._phase
                return (
                    f'<div class="tts-progress-bar">'
                    f'<div class="tts-progress-fill" style="width:{pct}%"></div>'
                    f"</div>"
                    f'<div class="tts-progress-info">'
                    f'<span class="tts-progress-phase">{phase_display}</span>'
                    f'<span class="tts-progress-percentage">{pct}%</span>'
                    f'<span class="tts-progress-speed">{speed_items}</span>'
                    f"</div>"
                )
            progress = self._current_segment / self._total_segments
            pct = int(progress * 100)
            elapsed = time.time() - self._start_time if self._start_time > 0 else 0
            remaining = self._estimate_remaining()
            speed_items = self._get_speed_info(elapsed)
            phase_display = self._phase
            segment_info = f"第 {self._current_segment}/{self._total_segments} 段"
            remaining_text = f"预计剩余 {self._format_duration(remaining)}" if remaining > 0 else ""
            return (
                f'<div class="tts-progress-bar">'
                f'<div class="tts-progress-fill" style="width:{pct}%"></div>'
                f"</div>"
                f'<div class="tts-progress-info">'
                f'<span class="tts-progress-phase">{phase_display}</span>'
                f'<span class="tts-progress-segment">{segment_info}</span>'
                f'<span class="tts-progress-percentage">{pct}%</span>'
                f'<span class="tts-progress-speed">{speed_items}</span>'
                f'<span class="tts-progress-remaining">{remaining_text}</span>'
                f"</div>"
            )

    def _get_speed_info(self, elapsed):
        """Calculate throughput metrics for display.

        Args:
            elapsed: Total elapsed time in seconds.

        Returns:
            Formatted speed string (e.g., "2.3秒/段 | ~1.5MB 待处理")
            or empty string if insufficient data.
        """
        if elapsed <= 0 or self._current_segment <= 0:
            return ""
        avg_per_segment = elapsed / self._current_segment
        remaining_segments = self._total_segments - self._current_segment
        if remaining_segments <= 0:
            return ""
        speed_text = f"{avg_per_segment:.1f}秒/段"
        if self._total_bytes_processed > 0 and self._current_segment > 0:
            avg_bytes = self._total_bytes_processed / self._current_segment
            remaining_bytes = avg_bytes * remaining_segments
            if remaining_bytes > 1024 * 1024:
                speed_text += f" | ~{remaining_bytes / (1024 * 1024):.1f}MB 待处理"
        return speed_text

    def _format_duration(self, seconds):
        """Format seconds into human-readable duration string.

        Args:
            seconds: Duration in seconds.

        Returns:
            Formatted string (e.g., "35秒", "2分10秒", "0秒").
        """
        if seconds <= 0:
            return "0秒"
        if seconds < 60:
            return f"{int(seconds)}秒"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}分{secs}秒"

    def _estimate_remaining(self):
        """Estimate remaining time based on historical segment timings.

        Uses rolling average of recent segment times if available,
        otherwise falls back to overall average.

        Returns:
            Estimated remaining time in seconds.
        """
        if not self._segment_times:
            if self._current_segment > 0 and self._start_time > 0:
                avg = (time.time() - self._start_time) / self._current_segment
            else:
                return 0
        else:
            avg = sum(self._segment_times) / len(self._segment_times)
        remaining_segments = self._total_segments - self._current_segment
        return avg * remaining_segments

    def reset(self):
        """Reset all progress state to initial values."""
        with self._lock:
            self._phase = ""
            self._current_segment = 0
            self._total_segments = 1
            self._start_time = 0
            self._segment_times = []
            self._total_bytes_processed = 0
            self._last_segment_bytes = 0
            self._is_complete = False
            self._is_cancelled = False
            self._total_chars_processed = 0
        self._notify_sse()

    def cancel(self):
        """Mark the current operation as cancelled."""
        with self._lock:
            self._is_cancelled = True
        self._notify_sse()

    def is_cancelled(self):
        """Check if the current operation has been cancelled.

        Returns:
            True if cancelled, False otherwise.
        """
        with self._lock:
            return self._is_cancelled

    def should_stop(self):
        """Check if the operation should stop (cancelled or complete).

        Returns:
            True if the operation should stop, False otherwise.
        """
        with self._lock:
            return self._is_cancelled or self._is_complete

    def add_chars_processed(self, char_count):
        """Accumulate the count of processed characters.

        Args:
            char_count: Number of characters in the processed segment.
        """
        with self._lock:
            self._total_chars_processed += char_count

    def get_speed_stats(self):
        """Calculate character throughput statistics.

        Returns:
            Dictionary with total_chars, elapsed time, and chars_per_sec.
        """
        with self._lock:
            elapsed = time.time() - self._start_time if self._start_time > 0 else 0
            chars_per_sec = (self._total_chars_processed / elapsed) if elapsed > 0 else 0
            return {
                "total_chars": self._total_chars_processed,
                "elapsed": elapsed,
                "chars_per_sec": round(chars_per_sec, 1),
            }

    def complete(self):
        """Mark all segments as completed and set progress to 100%."""
        with self._lock:
            self._current_segment = self._total_segments
            self._phase = "完成"
            self._is_complete = True
        self._notify_sse()

    def schedule_reset(self, delay_seconds=3):
        """Schedule a delayed reset of progress state on a background thread.

        Args:
            delay_seconds: Seconds to wait before resetting (default: 3).
        """

        def _delayed_reset():
            time.sleep(delay_seconds)
            self.reset()

        t = threading.Thread(target=_delayed_reset, daemon=True)
        t.start()

    def get_status(self) -> dict:
        """Get current progress status as a dictionary.

        Provides a public interface for SSE and other consumers
        to read progress state without accessing private attributes.

        Returns:
            Dictionary with keys: phase, current_segment, total_segments,
            is_complete, is_cancelled, is_active.
        """
        with self._lock:
            return {
                "phase": self._phase,
                "current_segment": self._current_segment,
                "total_segments": self._total_segments,
                "is_complete": self._is_complete,
                "is_cancelled": self._is_cancelled,
                "is_active": self._phase != "",
            }
