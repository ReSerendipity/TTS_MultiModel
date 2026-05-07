# -*- coding: utf-8 -*-
"""Generation time estimator: uses linear regression on historical data to predict generation duration."""

import math
import os
import json
import logging
from typing import Optional, List, Dict

logger = logging.getLogger("tts_multimodel")


class GenerationTimeEstimator:
    """Tracks generation times and uses simple linear regression to predict future durations.
    
    Model: duration = a * char_count + b
    Updated incrementally using Welford's online algorithm.
    """

    def __init__(self, data_file: str = "generation_times.json", max_entries: int = 200):
        self._data_file = data_file
        self._max_entries = max_entries
        self._samples: List[Dict] = []
        # Linear regression coefficients: duration = slope * chars + intercept
        self._slope: float = 0.1  # default: ~100ms per char
        self._intercept: float = 2.0  # default: 2s base overhead
        self._count: int = 0
        self._load()

    def _load(self):
        if os.path.exists(self._data_file):
            try:
                with open(self._data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._samples = data.get("samples", [])
                    self._count = data.get("count", 0)
                    # Precompute coefficients from loaded samples
                    if len(self._samples) >= 2:
                        self._recompute_coefficients()
                    elif len(self._samples) == 1:
                        s = self._samples[0]
                        chars = s["char_count"]
                        dur = s["duration"]
                        if chars > 0:
                            self._slope = dur / chars
                        self._intercept = max(0, dur - self._slope * chars)
            except Exception:
                pass

    def _save(self):
        try:
            with open(self._data_file, "w", encoding="utf-8") as f:
                json.dump({"samples": self._samples, "count": self._count}, f, ensure_ascii=False)
        except Exception:
            pass

    def record(self, char_count: int, duration: float, engine: str = "unknown", segment_count: int = 1):
        """Record a completed generation."""
        self._samples.append({
            "char_count": char_count,
            "duration": round(duration, 3),
            "engine": engine,
            "segments": segment_count,
        })
        self._count += 1

        # Trim oldest entries if exceeding max
        if len(self._samples) > self._max_entries:
            self._samples = self._samples[-self._max_entries:]

        self._recompute_coefficients()
        self._save()

    def _recompute_coefficients(self):
        """Compute linear regression coefficients from samples using least squares."""
        if len(self._samples) < 2:
            return

        n = len(self._samples)
        sum_x = sum(s["char_count"] for s in self._samples)
        sum_y = sum(s["duration"] for s in self._samples)
        sum_xy = sum(s["char_count"] * s["duration"] for s in self._samples)
        sum_xx = sum(s["char_count"] ** 2 for s in self._samples)

        denominator = n * sum_xx - sum_x * sum_x
        if abs(denominator) < 1e-10:
            # All char_counts are the same, use average
            self._slope = 0
            self._intercept = sum_y / n if n > 0 else 2.0
            return

        self._slope = (n * sum_xy - sum_x * sum_y) / denominator
        self._intercept = (sum_y - self._slope * sum_x) / n

        # Sanity checks
        if self._slope < 0.001:
            self._slope = 0.05  # minimum 50ms per char
        if self._intercept < 0.5:
            self._intercept = 1.0  # minimum 1s overhead
        if self._slope > 1.0:
            self._slope = 0.5  # cap at 500ms per char

    def estimate(self, char_count: int, segment_count: int = 1) -> float:
        """Estimate generation duration for the given character count.
        
        Returns estimated duration in seconds.
        """
        if char_count <= 0:
            return self._intercept

        estimate = self._slope * char_count + self._intercept

        # Adjust for segment count (overhead per segment)
        if segment_count > 1:
            per_segment_overhead = 0.3 * (segment_count - 1)  # 0.3s merge overhead
            estimate += per_segment_overhead

        return max(1.0, estimate)

    def estimate_with_confidence(self, char_count: int) -> tuple:
        """Estimate duration and return confidence level (0-1).
        
        Returns (estimated_seconds, confidence)
        """
        estimate = self.estimate(char_count)
        # Confidence based on sample count
        if self._count == 0:
            confidence = 0.0  # No data, pure guess
        elif self._count < 5:
            confidence = self._count / 10.0  # 0.1 - 0.5
        elif self._count < 20:
            confidence = 0.5 + (self._count - 5) / 30.0  # 0.5 - 0.65
        else:
            confidence = min(0.95, 0.65 + (self._count - 20) / 100.0)

        return estimate, confidence

    def get_stats(self) -> dict:
        """Get statistics about the estimator."""
        if not self._samples:
            return {"sample_count": 0, "model": "default"}

        durations = [s["duration"] for s in self._samples]
        return {
            "sample_count": self._count,
            "avg_duration": round(sum(durations) / len(durations), 2),
            "min_duration": round(min(durations), 2),
            "max_duration": round(max(durations), 2),
            "model": f"duration = {self._slope:.4f} * chars + {self._intercept:.2f}",
        }
