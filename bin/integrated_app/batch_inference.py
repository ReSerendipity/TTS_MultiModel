"""Batch Inference Module for TTS MultiModel.

Provides efficient batch processing for multiple text segments,
with support for torch.no_grad() context and pre-allocated tensor pools.
"""

import logging
import time
from typing import Any, Callable, Generator

import numpy as np

try:
    import torch
except ImportError:
    torch = None

logger = logging.getLogger("tts_multimodel")


class BatchInferencer:
    """Batch inferencer for TTS engines.
    
    Supports:
    - torch.no_grad() context for memory efficiency
    - Pre-allocated tensor pools for fixed sample rates
    - Progress tracking and cancellation
    """
    
    def __init__(
        self,
        sample_rate: int = 24000,
        max_batch_size: int = 8,
        use_tensor_pool: bool = True,
    ):
        """Initialize batch inferencer.
        
        Args:
            sample_rate: Audio sample rate for pre-allocation
            max_batch_size: Maximum batch size for processing
            use_tensor_pool: Whether to use pre-allocated tensor pool
        """
        self.sample_rate = sample_rate
        self.max_batch_size = max_batch_size
        self.use_tensor_pool = use_tensor_pool
        self._tensor_pool: list[np.ndarray] = []
        self._pool_size = 0
        
    def _ensure_tensor_pool(self, estimated_segments: int) -> None:
        """Ensure tensor pool has enough pre-allocated buffers.
        
        Args:
            estimated_segments: Estimated number of segments to process
        """
        if not self.use_tensor_pool:
            return
            
        needed = min(estimated_segments, self.max_batch_size)
        if needed > self._pool_size:
            # Pre-allocate buffers for expected segments
            for _ in range(needed - self._pool_size):
                # Pre-allocate with estimated length (2 seconds)
                buffer = np.zeros(self.sample_rate * 2, dtype=np.float32)
                self._tensor_pool.append(buffer)
            self._pool_size = needed
            logger.debug(f"Tensor pool expanded to {self._pool_size} buffers")
    
    def _get_buffer(self, min_length: int = 0) -> np.ndarray:
        """Get a buffer from the pool or create new one.
        
        Args:
            min_length: Minimum required length
            
        Returns:
            numpy array buffer
        """
        if self._tensor_pool:
            buffer = self._tensor_pool.pop()
            if len(buffer) >= min_length:
                return buffer[:min_length] if min_length > 0 else buffer
        # Fallback to creating new buffer
        return np.zeros(max(min_length, self.sample_rate), dtype=np.float32)
    
    def _return_buffer(self, buffer: np.ndarray) -> None:
        """Return buffer to pool for reuse.
        
        Args:
            buffer: Buffer to return
        """
        if self.use_tensor_pool and len(self._tensor_pool) < self.max_batch_size:
            self._tensor_pool.append(buffer)
    
    def process(
        self,
        segments: list[str],
        generate_fn: Callable[[str], np.ndarray],
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> Generator[tuple[int, np.ndarray], None, None]:
        """Process multiple text segments in batch.
        
        Args:
            segments: List of text segments to process
            generate_fn: Function that generates audio from text
            progress_callback: Optional callback for progress updates
            cancel_check: Optional function to check for cancellation
            
        Yields:
            Tuple of (segment_index, audio_array) for each generated segment
        """
        total = len(segments)
        if total == 0:
            return
            
        logger.info(f"Starting batch inference for {total} segments")
        start_time = time.time()
        
        # Pre-allocate tensor pool
        self._ensure_tensor_pool(total)
        
        # Use torch.no_grad() context for memory efficiency if available
        if torch is not None:
            context = torch.no_grad()
        else:
            context = None
        
        if context is not None:
            context.__enter__()
        
        try:
            for i, segment in enumerate(segments):
                # Check for cancellation
                if cancel_check and cancel_check():
                    logger.info("Batch inference cancelled")
                    break
                    
                # Generate audio
                try:
                    audio = generate_fn(segment)
                    yield i, audio
                except Exception as e:
                    logger.error(f"Failed to generate segment {i}: {e}")
                    # Yield empty audio on failure
                    yield i, np.array([], dtype=np.float32)
                
                # Report progress
                if progress_callback:
                    progress_callback(i + 1, total)
        finally:
            if context is not None:
                context.__exit__(None, None, None)
        
        elapsed = time.time() - start_time
        logger.info(f"Batch inference completed in {elapsed:.2f}s ({total/elapsed:.2f} segments/sec)")
    
    def _batch_generate_sequential(
        self,
        text_list: list[str],
        generate_fn: Callable[[str], np.ndarray],
    ) -> list[np.ndarray]:
        """Sequential batch generation for engines without native batch support.
        
        Args:
            text_list: List of texts to generate
            generate_fn: Function that generates audio from text
            
        Returns:
            List of audio arrays
        """
        results = []
        for text in text_list:
            results.append(generate_fn(text))
        return results
    
    def clear_pool(self) -> None:
        """Clear the tensor pool to free memory."""
        self._tensor_pool.clear()
        self._pool_size = 0
        logger.debug("Tensor pool cleared")


class BatchInferenceManager:
    """Manager for batch inference operations."""
    
    def __init__(self):
        """Initialize batch inference manager."""
        self._inferencers: dict[str, BatchInferencer] = {}
    
    def get_inferencer(
        self,
        engine_name: str,
        sample_rate: int = 24000,
    ) -> BatchInferencer:
        """Get or create inferencer for engine.
        
        Args:
            engine_name: Name of the TTS engine
            sample_rate: Audio sample rate
            
        Returns:
            BatchInferencer instance
        """
        if engine_name not in self._inferencers:
            self._inferencers[engine_name] = BatchInferencer(
                sample_rate=sample_rate,
            )
        return self._inferencers[engine_name]
    
    def clear_all(self) -> None:
        """Clear all inferencers and their pools."""
        for inferencer in self._inferencers.values():
            inferencer.clear_pool()
        self._inferencers.clear()


# Module-level manager instance
batch_manager = BatchInferenceManager()