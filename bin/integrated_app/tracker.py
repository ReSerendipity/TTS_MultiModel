"""Generation queue tracking module.

Tracks generation queue depth and estimates wait times using
exponential moving average for stable estimates.
"""

import threading


class GenerationTracker:
    """Tracks generation queue depth and estimates wait times.

    Uses exponential moving average (alpha=0.2) to smooth generation
    time measurements for more stable wait time estimates.

    Attributes:
        queue_depth: Current number of queued generation requests.
        avg_gen_time: Exponential moving average of generation duration (seconds).
        _lock: Thread lock for state mutations.
        phase: Human-readable status phase description.
    """

    def __init__(self):
        self.queue_depth = 0
        self.avg_gen_time = 15.0
        self._lock = threading.RLock()
        self.phase = "空闲"

    def start_generation(self):
        """Increment queue depth at the start of a generation request.

        Returns:
            New queue depth after increment.
        """
        with self._lock:
            self.queue_depth += 1
            return self.queue_depth

    def end_generation(self, elapsed):
        """Update average generation time and decrement queue depth.

        Args:
            elapsed: Duration of the completed generation in seconds.
        """
        with self._lock:
            self.avg_gen_time = 0.8 * self.avg_gen_time + 0.2 * elapsed
            self.queue_depth = max(0, self.queue_depth - 1)

    def estimate_wait(self):
        """Estimate total wait time for queued requests.

        Returns:
            Estimated wait time in seconds.
        """
        with self._lock:
            return self.avg_gen_time * self.queue_depth

    def status_text(self):
        """Generate human-readable queue status string.

        Returns:
            Status text showing queue depth and estimated wait time,
            or "idle" if queue is empty.
        """
        with self._lock:
            if self.queue_depth == 0:
                return "空闲"
            wait = self.estimate_wait()
            return f"队列: {self.queue_depth} | 预计等待: {wait:.0f}秒"
