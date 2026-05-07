# -*- coding: utf-8 -*-
"""Dynamic batching for long text TTS inference.

Groups text segments into batches to maximize GPU utilization.
Falls back to sequential processing when batching is not suitable.
"""

import logging
import time
from typing import List, Tuple, Callable, Optional
from dataclasses import dataclass

logger = logging.getLogger("tts_multimodel")


@dataclass
class BatchResult:
    """Result of a batch inference."""
    audio_segments: List  # List of audio arrays
    total_chars: int
    batch_time: float
    segment_count: int


class BatchInferencer:
    """Dynamically batches text segments for efficient TTS inference.
    
    Strategy:
    - Collect 2-4 segments at a time
    - Group segments with similar character counts to minimize padding
    - Fall back to sequential if segments are too diverse
    """

    def __init__(
        self,
        max_batch_size: int = 4,
        max_chars_per_batch: int = 600,
        similarity_threshold: float = 0.5,
    ):
        self._max_batch_size = max_batch_size
        self._max_chars_per_batch = max_chars_per_batch
        self._similarity_threshold = similarity_threshold

    def _should_batch(self, segments: List[str]) -> bool:
        """Check if batching is beneficial for these segments."""
        if len(segments) < 2:
            return False
        
        lengths = [len(s) for s in segments]
        avg_len = sum(lengths) / len(lengths)
        
        # Check length similarity (coefficient of variation)
        if avg_len == 0:
            return False
        variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
        cv = (variance ** 0.5) / avg_len
        
        return cv <= self._similarity_threshold

    def _create_batches(self, segments: List[str]) -> List[List[str]]:
        """Group segments into optimal batches."""
        if not segments:
            return []
        
        # Sort by length to group similar-length segments
        indexed = [(i, s) for i, s in enumerate(segments)]
        indexed.sort(key=lambda x: len(x[1]))
        
        batches = []
        current_batch = []
        current_chars = 0
        
        for idx, segment in indexed:
            if (len(current_batch) >= self._max_batch_size or
                current_chars + len(segment) > self._max_chars_per_batch):
                if current_batch:
                    batches.append(current_batch)
                current_batch = [(idx, segment)]
                current_chars = len(segment)
            else:
                current_batch.append((idx, segment))
                current_chars += len(segment)
        
        if current_batch:
            batches.append(current_batch)
        
        # Sort each batch back by original index for correct ordering
        for batch in batches:
            batch.sort(key=lambda x: x[0])
        
        return batches

    def process(
        self,
        segments: List[str],
        generate_fn: Callable[[str], object],
        merge_fn: Optional[Callable[[List], object]] = None,
    ) -> BatchResult:
        """Process text segments with dynamic batching.
        
        Args:
            segments: List of text segments to process.
            generate_fn: Function to generate audio for a single segment.
                         Should return an audio array.
            merge_fn: Optional function to merge batch results.
                     If None, results are concatenated.
        
        Returns:
            BatchResult with all audio segments.
        """
        if not segments:
            return BatchResult([], 0, 0.0, 0)
        
        all_results = [None] * len(segments)
        start_time = time.monotonic()
        total_chars = 0
        
        batches = self._create_batches(segments)
        
        if self._should_batch(segments) and len(batches) > 0:
            logger.info(f"Using dynamic batching: {len(batches)} batches for {len(segments)} segments")
            
            for batch in batches:
                batch_segments = [s for _, s in batch]
                batch_chars = sum(len(s) for s in batch_segments)
                
                # Check if batch is suitable
                if self._should_batch(batch_segments):
                    # Try batch inference
                    try:
                        batch_result = self._batch_generate(batch_segments, generate_fn)
                        for i, (_, orig_idx) in enumerate(batch):
                            all_results[orig_idx] = batch_result[i]
                        total_chars += batch_chars
                        continue
                    except Exception as e:
                        logger.warning(f"Batch inference failed, falling back to sequential: {e}")
                
                # Fall back to sequential for this batch
                for _, orig_idx in batch:
                    segment = segments[orig_idx]
                    all_results[orig_idx] = generate_fn(segment)
                    total_chars += len(segment)
        else:
            # Sequential processing
            logger.info(f"Using sequential processing for {len(segments)} segments")
            for i, segment in enumerate(segments):
                all_results[i] = generate_fn(segment)
                total_chars += len(segment)
        
        elapsed = time.monotonic() - start_time
        valid_results = [r for r in all_results if r is not None]
        
        return BatchResult(valid_results, total_chars, elapsed, len(valid_results))

    def _batch_generate(
        self,
        segments: List[str],
        generate_fn: Callable[[str], object],
    ) -> List[object]:
        """Attempt batch generation for a group of segments.
        
        This is a placeholder that calls generate_fn sequentially but
        provides the interface for future true batch implementation.
        """
        return [generate_fn(s) for s in segments]
