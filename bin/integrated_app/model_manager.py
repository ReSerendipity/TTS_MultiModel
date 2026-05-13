# -*- coding: utf-8 -*-
"""Model management module.

Provides model loading, unloading, engine switching, LRU caching,
progress tracking, GPU memory monitoring, and persona cache warmup.

Refactored for VoxCPM2-only architecture.
"""

import os
import gc
import time
import logging
import threading
from collections import OrderedDict
from typing import Any, Generator, Optional, Tuple

import torch

from .config import (
    ROOT_DIR, VOXCPM2_MODEL_PATH, VOXCPM2_ASR_PATH,
    VOXCPM2_DENOISER_PATH, SAVE_DIR, PERSONA_DIR,
)
from .exceptions import (
    TTSError, ModelLoadError, InsufficientVRAMError, EngineSwitchError,
)
from .estimator import GenerationTimeEstimator
from .monitor import get_health_monitor

logger = logging.getLogger("tts_multimodel")


# --- Global dynamic estimator ---
_time_estimator = GenerationTimeEstimator(
    data_file=os.path.join(ROOT_DIR, "generation_times.json"),
    max_entries=200,
)


# --- Preload state ---
_preload_state = {
    "in_progress": False,
    "target_engine": None,
    "target_size": None,
    "completed": False,
    "error": None,
}
_preload_lock = threading.Lock()


# --- LRU Cache ---
class LRUCache:
    """Least Recently Used cache with fixed capacity.

    Uses OrderedDict to track access order. When capacity is exceeded,
    the least recently accessed item is evicted first.

    Attributes:
        _cache: OrderedDict storing cached items.
        _maxsize: Maximum number of items the cache can hold.
        _hits: Number of successful cache lookups.
        _misses: Number of failed cache lookups.
    """

    def __init__(self, maxsize: int = 50) -> None:
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a cached item by key.

        Moves the accessed item to the end (most recently used position).

        Args:
            key: Cache key to look up.

        Returns:
            Cached value if found, None otherwise.
        """
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, key: str, value: Any) -> None:
        """Insert or update a cached item.

        Moves existing key to the end. If cache exceeds maxsize,
        evicts least recently used items until within capacity.

        Args:
            key: Cache key.
            value: Value to cache.
        """
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def __delitem__(self, key: str) -> None:
        if key in self._cache:
            del self._cache[key]

    def get_stats(self) -> dict:
        """Return cache performance statistics.

        Returns:
            Dictionary with hits, misses, hit_rate (percentage),
            current size and maxsize.
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 1),
            "size": len(self._cache),
            "maxsize": self._maxsize,
        }

    def reset_stats(self) -> None:
        """Reset hit and miss counters to zero."""
        self._hits = 0
        self._misses = 0


class AdaptiveLRUCache(LRUCache):
    """LRU cache with adaptive capacity based on GPU memory usage.

    Automatically adjusts cache size inversely proportional to GPU
    memory utilization. High GPU usage triggers cache shrinkage
    to free system memory, low usage allows cache expansion.

    Capacity mapping:
        GPU > 90% -> 5 items
        GPU > 75% -> 10 items
        GPU > 50% -> 15 items
        Otherwise  -> 20 items

    Attributes:
        _CAPACITY_MAP: List of (gpu_threshold, cache_capacity) tuples.
        _adapt_lock: Thread lock for capacity adjustment.
    """

    _CAPACITY_MAP = [
        (90, 5),
        (75, 10),
        (50, 15),
        (0, 20),
    ]

    def __init__(self, default_maxsize: int = 15) -> None:
        super().__init__(maxsize=default_maxsize)
        self._adapt_lock = threading.Lock()

    @staticmethod
    def _get_gpu_memory_percent() -> float:
        """Query current GPU memory allocation percentage.

        Returns:
            Memory usage percentage (0.0 to 100.0), or 0.0 if CUDA unavailable.
        """
        try:
            if not torch.cuda.is_available():
                return 0.0
            device = get_nvidia_gpu_device()
            total = torch.cuda.get_device_properties(device).total_memory
            allocated = torch.cuda.memory_allocated(device)
            if total == 0:
                return 0.0
            return allocated / total * 100
        except Exception:
            return 0.0

    def _calculate_target_capacity(self) -> int:
        """Determine cache capacity based on current GPU memory usage.

        Returns:
            Target cache capacity (number of items).
        """
        gpu_pct = self._get_gpu_memory_percent()
        for threshold, capacity in self._CAPACITY_MAP:
            if gpu_pct > threshold:
                return capacity
        return 20

    def adapt_capacity(self) -> int:
        """Adjust cache capacity based on GPU memory and evict excess items.

        Returns:
            New cache capacity after adjustment.
        """
        target = self._calculate_target_capacity()
        with self._adapt_lock:
            old_max = self._maxsize
            self._maxsize = target
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)
            if old_max != target:
                logger.info(
                    f"[AdaptiveCache] capacity adjusted: {old_max} -> {target} "
                    f"(GPU usage: {self._get_gpu_memory_percent():.1f}%)"
                )
        return target

    def put(self, key: str, value: Any) -> None:
        """Insert item after adapting cache capacity if needed."""
        self.adapt_capacity()
        super().put(key, value)

    def clear(self) -> None:
        """Clear all cached items and reset statistics."""
        with self._adapt_lock:
            self._cache.clear()
            self.reset_stats()


# --- Generation Tracker ---
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


# --- Progress Manager ---
class ProgressManager:
    """Manages generation progress tracking and renders HTML progress bars.

    Tracks segment-by-segment progress with phase labels, timing,
    byte throughput, and character throughput. Generates HTML for
    frontend rendering via HTMX partial updates.

    Supports single-segment mode (animated progress 5%→95%) and
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

    def update_phase(self, phase):
        """Update the current phase label.

        Args:
            phase: New phase label string.
        """
        with self._lock:
            self._phase = phase

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
                return ('<div class="tts-progress-bar">'
                        '<div class="tts-progress-fill tts-progress-complete" style="width:100%"></div>'
                        '</div>'
                        '<div class="tts-progress-info tts-progress-complete-info">'
                        '<span class="tts-progress-phase">生成完成</span>'
                        '<span class="tts-progress-percentage">100%</span>'
                        '</div>')
            if self._total_segments <= 0:
                return ""
            if self._total_segments == 1:
                elapsed = time.time() - self._start_time if self._start_time > 0 else 0
                if elapsed < 0.5:
                    return ""
                estimated_total = 20.0
                raw_progress = elapsed / estimated_total
                pct = max(5, min(95, int(5 + raw_progress * 90)))
                remaining = max(0, estimated_total - elapsed)
                speed_items = self._get_speed_info(elapsed)
                phase_display = self._phase
                return (f'<div class="tts-progress-bar">'
                        f'<div class="tts-progress-fill" style="width:{pct}%"></div>'
                        f'</div>'
                        f'<div class="tts-progress-info">'
                        f'<span class="tts-progress-phase">{phase_display}</span>'
                        f'<span class="tts-progress-percentage">{pct}%</span>'
                        f'<span class="tts-progress-speed">{speed_items}</span>'
                        f'</div>')
            progress = self._current_segment / self._total_segments
            pct = int(progress * 100)
            elapsed = time.time() - self._start_time if self._start_time > 0 else 0
            remaining = self._estimate_remaining()
            speed_items = self._get_speed_info(elapsed)
            phase_display = self._phase
            segment_info = f"第 {self._current_segment}/{self._total_segments} 段"
            remaining_text = f"预计剩余 {self._format_duration(remaining)}" if remaining > 0 else ""
            return (f'<div class="tts-progress-bar">'
                    f'<div class="tts-progress-fill" style="width:{pct}%"></div>'
                    f'</div>'
                    f'<div class="tts-progress-info">'
                    f'<span class="tts-progress-phase">{phase_display}</span>'
                    f'<span class="tts-progress-segment">{segment_info}</span>'
                    f'<span class="tts-progress-percentage">{pct}%</span>'
                    f'<span class="tts-progress-speed">{speed_items}</span>'
                    f'<span class="tts-progress-remaining">{remaining_text}</span>'
                    f'</div>')

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
                speed_text += f" | ~{remaining_bytes / (1024*1024):.1f}MB 待处理"
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

    def cancel(self):
        """Mark the current operation as cancelled."""
        with self._lock:
            self._is_cancelled = True

    def is_cancelled(self):
        """Check if the current operation has been cancelled.

        Returns:
            True if cancelled, False otherwise.
        """
        with self._lock:
            return self._is_cancelled

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


def get_nvidia_gpu_device():
    """Find the NVIDIA GPU device index with the most available VRAM.

    Only supports NVIDIA GPUs with CUDA. Iterates through all available
    GPU devices and filters by name patterns (NVIDIA, GeForce, RTX,
    GTX, Quadro, Tesla). If multiple GPUs are found, selects the one
    with the largest total VRAM.

    Returns:
        GPU device index for the best available NVIDIA GPU.

    Raises:
        RuntimeError: If CUDA is not available or no NVIDIA GPU is detected.
    """
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA 不可用，请确认已安装支持 CUDA 的 NVIDIA 显卡和驱动。")
    
    nvidia_devices = []
    for i in range(torch.cuda.device_count()):
        try:
            props = torch.cuda.get_device_properties(i)
            name_lower = props.name.lower()
            if "nvidia" in name_lower or "geforce" in name_lower or "rtx" in name_lower or "gtx" in name_lower or "quadro" in name_lower or "tesla" in name_lower:
                nvidia_devices.append((i, props.total_memory, props.name))
            else:
                logger.debug(f"忽略非 NVIDIA GPU {i}: {props.name}")
        except Exception as e:
            logger.debug(f"无法获取 GPU {i} 信息: {e}")
    
    if not nvidia_devices:
        raise RuntimeError("未检测到可用的 NVIDIA 显卡。本项目仅支持 NVIDIA GPU (CUDA 加速)，不支持 Intel/AMD 显卡。")
    
    best_idx, best_mem, best_name = max(nvidia_devices, key=lambda x: x[1])
    
    if torch.cuda.device_count() > 1:
        logger.info(f"多 GPU 环境，选择 NVIDIA GPU {best_idx}: {best_name} (VRAM: {best_mem / 1024**3:.1f}GB)")
    
    return best_idx


def get_nvidia_gpu_memory_info():
    """Get memory information for the primary NVIDIA GPU.

    Returns:
        Tuple of (total_bytes, allocated_bytes, reserved_bytes, free_bytes),
        or (0, 0, 0, 0) if GPU memory info cannot be retrieved.
    """
    device = get_nvidia_gpu_device()
    if not torch.cuda.is_available():
        return (0, 0, 0, 0)
    try:
        props = torch.cuda.get_device_properties(device)
        total = props.total_memory
        allocated = torch.cuda.memory_allocated(device)
        reserved = torch.cuda.memory_reserved(device)
        free = total - allocated
        return (total, allocated, reserved, free)
    except Exception as e:
        logger.error(f"Failed to get GPU memory info: {e}")
        return (0, 0, 0, 0)


# --- GPU VRAM Monitor ---
class GPUMemoryMonitor:
    """Static utility class for GPU VRAM monitoring and capacity checks.

    Provides methods to query current VRAM usage and determine if
    there is sufficient free VRAM to load the model.
    """

    @staticmethod
    def get_vram_info():
        """Query current VRAM usage statistics.

        Returns:
            Dictionary with 'total', 'used', and 'free' keys in bytes.
            Returns zeroed dict if CUDA is unavailable.
        """
        if not torch.cuda.is_available():
            return {"total": 0, "used": 0, "free": 0}
        total, allocated, reserved, free = get_nvidia_gpu_memory_info()
        return {"total": total, "used": allocated, "free": free}

    @staticmethod
    def can_load_model(model_name="voxcpm2"):
        """Check if there is enough free VRAM to load the specified model.

        Args:
            model_name: Model identifier (currently only "voxcpm2" is supported).

        Returns:
            Tuple of (can_load: bool, free_bytes: int).
        """
        info = GPUMemoryMonitor.get_vram_info()
        needed = int(6.5 * 1024**3)  # VoxCPM2 needs ~6.5GB
        return info["free"] >= needed, info["free"]


# --- Global State ---
voxcpm_model = None
voxcpm_asr = None
current_engine = "voxcpm2"
current_type = "voxcpm2"
current_size = "voxcpm2"

# 音色缓存：存储 (wav_path, ref_text)，由官方 API 在每次生成时计算嵌入
_persona_embedding_cache = AdaptiveLRUCache(default_maxsize=15)
_gen_tracker = GenerationTracker()
_progress_mgr = ProgressManager()
_model_lock = threading.RLock()
_persona_warmup_done = {"done": False}
_persona_warmup_lock = threading.Lock()


def get_persona_cache_stats() -> dict:
    """Retrieve current persona embedding cache statistics.

    Returns:
        Dictionary with hits, misses, hit_rate, size, and maxsize.
    """
    return _persona_embedding_cache.get_stats()


def warmup_persona_cache() -> None:
    """Asynchronously preload the 5 most recently used personas into cache.

    Runs on a background daemon thread to avoid blocking application startup.
    Only executes once per process lifetime (guarded by _persona_warmup_lock).
    Logs a summary of cache state after warmup completes.
    """
    with _persona_warmup_lock:
        if _persona_warmup_done["done"]:
            return
        _persona_warmup_done["done"] = True

    def _do_warmup():
        try:
            from .persona_manager import get_persona_list, load_persona_embedding
            from .config import PERSONA_DIR

            persona_files = []
            if os.path.isdir(PERSONA_DIR):
                for f in os.listdir(PERSONA_DIR):
                    if f.endswith(".wav"):
                        full_path = os.path.join(PERSONA_DIR, f)
                        mtime = os.path.getmtime(full_path)
                        persona_files.append((f[:-4], mtime))

            persona_files.sort(key=lambda x: x[1], reverse=True)
            top_personas = [name for name, _ in persona_files[:5]]
            if not top_personas:
                logger.info("[PersonaCacheWarmup] No personas found to warm up")
                return

            logger.info(f"[PersonaCacheWarmup] Starting warmup for {len(top_personas)} personas: {top_personas}")
            for name in top_personas:
                try:
                    load_persona_embedding(name)
                    logger.debug(f"[PersonaCacheWarmup] Warmed up persona: {name}")
                except Exception as e:
                    logger.warning(f"[PersonaCacheWarmup] Failed to warmup persona '{name}': {e}")

            stats = _persona_embedding_cache.get_stats()
            logger.info(
                f"[PersonaCacheWarmup] Warmup complete. Cache size: {stats['size']}/{stats['maxsize']}"
            )
        except Exception as e:
            logger.error(f"[PersonaCacheWarmup] Warmup failed: {e}")

    t = threading.Thread(target=_do_warmup, daemon=True, name="persona-cache-warmup")
    t.start()


def _check_model_ready() -> bool:
    """Non-blocking check if the model lock is available.

    Returns:
        True if the model is not being loaded/switched, False if locked.
    """
    if not _model_lock.acquire(blocking=False):
        return False
    _model_lock.release()
    return True


def unload_model() -> None:
    """Unload the current VoxCPM2 model and aggressively release VRAM.

    Acquires the model lock, deletes model and ASR references, clears
    the persona embedding cache, then performs multi-step GPU memory
    cleanup: synchronize, empty cache, clear cuBLAS workspaces,
    IPC collect, sleep, and final empty cache.
    """
    global voxcpm_model, voxcpm_asr
    with _model_lock:
        if voxcpm_model is not None:
            del voxcpm_model
            voxcpm_model = None
        if voxcpm_asr is not None:
            del voxcpm_asr
            voxcpm_asr = None
        _persona_embedding_cache.clear()
        gc.collect()
        if torch.cuda.is_available():
            device = get_nvidia_gpu_device()
            torch.cuda.synchronize(device)
            torch.cuda.empty_cache()
            try:
                torch._C._cuda_clearCublasWorkspaces()
            except AttributeError:
                pass
            torch.cuda.ipc_collect()
            time.sleep(0.5)
            torch.cuda.empty_cache()
            allocated = torch.cuda.memory_allocated(device)
            reserved = torch.cuda.memory_reserved(device)
            logger.info(f"释放后显存: 已分配 {allocated / 1024**3:.2f}GB, 保留 {reserved / 1024**3:.2f}GB")
        time.sleep(0.3)


def load_voxcpm2() -> Generator:
    """Load the VoxCPM2 engine with generator-based progress feedback.

    Yields status text tuples suitable for UI display at each loading stage:
    1. Unload existing model and clear GPU memory
    2. Load VoxCPM2 main model via voxcpm.VoxCPM.from_pretrained()
    3. Move all model sub-components (tts_model, model, codecs, vocoder) to GPU
    4. Load ASR model via funasr.AutoModel
    5. Record VRAM usage to health monitor

    On failure, cleans up partial state and yields error status.

    Yields:
        Tuple of (status_text, audio, sample_rate, format) at each stage.
    """
    global voxcpm_model, voxcpm_asr, current_engine, current_type, current_size
    import voxcpm
    from funasr import AutoModel

    _model_lock.acquire()
    try:
        # Unload current engine if any
        if voxcpm_model is not None:
            del voxcpm_model
            voxcpm_model = None
        if voxcpm_asr is not None:
            del voxcpm_asr
            voxcpm_asr = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        time.sleep(1)

        status_text = "正在加载 VoxCPM2 模型..."
        yield status_text, None, None, None
        try:
            voxcpm_model = voxcpm.VoxCPM.from_pretrained(
                VOXCPM2_MODEL_PATH,
                optimize=True,
                local_files_only=True,
            )
            # 显式将模型子组件移至 GPU（与引擎切换逻辑保持一致）
            cuda_device = f"cuda:{get_nvidia_gpu_device()}"
            if torch.cuda.is_available():
                for attr in ('tts_model', 'model', 'codecs', 'vocoder'):
                    sub = getattr(voxcpm_model, attr, None)
                    if sub is not None and hasattr(sub, 'to'):
                        sub.to(cuda_device)
                        logger.info(f"  VoxCPM2.{attr} -> {cuda_device}")
                # 确保 CUDA 缓存同步
                torch.cuda.synchronize()
                allocated_mb = torch.cuda.memory_allocated() / (1024 ** 2)
                logger.info(f"  VoxCPM2 加载完成，GPU 显存已分配: {allocated_mb:.0f} MB")

            status_text = "正在加载 ASR 模型..."
            yield status_text, None, None, None
            voxcpm_asr = AutoModel(
                model=VOXCPM2_ASR_PATH,
                disable_pbar=True,
                device=cuda_device,
            )
            current_engine = "voxcpm2"
            current_type = "voxcpm2"
            current_size = "voxcpm2"
            status_text = "VoxCPM2 引擎就绪"
            
            try:
                monitor = get_health_monitor()
                if torch.cuda.is_available():
                    vram_mb = torch.cuda.memory_allocated() / (1024 ** 2)
                    monitor.record_vram_usage(vram_mb)
                    monitor.set_model_status("ready")
            except Exception as e:
                logger.debug(f"VRAM recording after VoxCPM2 load failed: {e}")
            
            yield status_text, None, None, None
        except Exception as e:
            if voxcpm_model is not None:
                del voxcpm_model
                voxcpm_model = None
            if voxcpm_asr is not None:
                del voxcpm_asr
                voxcpm_asr = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            current_engine = None
            status_text = f"VoxCPM2 加载失败: {e}"
            yield status_text, None, None, None
    finally:
        _model_lock.release()


def preload_model(engine="voxcpm2", size="voxcpm2") -> None:
    """Background preload of model files into system RAM page cache.

    Reads the first 1MB of each model file to warm up the OS page cache,
    reducing disk I/O latency when the model is subsequently loaded into
    GPU VRAM. Does NOT load model into VRAM.

    Runs on a background daemon thread to avoid blocking application startup.
    Only one preload task runs at a time (guarded by _preload_lock).

    Args:
        engine: Target engine name (currently only "voxcpm2" is supported).
        size: Model size variant (currently ignored for VoxCPM2).
    """
    global _preload_state

    with _preload_lock:
        if _preload_state["in_progress"]:
            logger.info("[预加载] 已有预加载任务在进行中，跳过")
            return
        _preload_state["in_progress"] = True
        _preload_state["target_engine"] = engine
        _preload_state["target_size"] = size
        _preload_state["completed"] = False
        _preload_state["error"] = None

    def _do_preload():
        try:
            if engine == "voxcpm2":
                logger.info(f"[预加载] 开始预读 VoxCPM2 模型文件到系统内存...")
                if os.path.exists(VOXCPM2_MODEL_PATH):
                    _read_files_to_cache(VOXCPM2_MODEL_PATH)
                    logger.info(f"[预加载] VoxCPM2 模型文件已预读到系统缓存")
                else:
                    logger.warning(f"[预加载] VoxCPM2 模型路径不存在: {VOXCPM2_MODEL_PATH}")

                if os.path.exists(VOXCPM2_ASR_PATH):
                    _read_files_to_cache(VOXCPM2_ASR_PATH)
                    logger.info(f"[预加载] VoxCPM2 ASR 模型文件已预读到系统缓存")

            with _preload_lock:
                _preload_state["completed"] = True
                _preload_state["in_progress"] = False
                logger.info("[预加载] 预加载完成")

        except Exception as e:
            logger.error(f"[预加载] 预加载失败: {e}")
            with _preload_lock:
                _preload_state["error"] = str(e)
                _preload_state["in_progress"] = False

    t = threading.Thread(target=_do_preload, daemon=True, name="model-preload")
    t.start()


def _read_files_to_cache(directory_path):
    """Recursively read model files into system page cache.

    For each file in the directory tree, reads the first 1MB (or full file
    if smaller) to warm up the OS page cache. Skips dot-files and
    __pycache__ directories.

    Args:
        directory_path: Path to directory or single file to preload.

    Returns:
        Total bytes read into cache.
    """
    if os.path.isfile(directory_path):
        _read_single_file(directory_path)
        return
    if not os.path.isdir(directory_path):
        return
    total_bytes = 0
    for root, dirs, files in os.walk(directory_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        for fname in sorted(files):
            if fname.startswith('.'):
                continue
            fpath = os.path.join(root, fname)
            total_bytes += _read_single_file(fpath)
    if total_bytes > 0:
        logger.info(f"[预加载] 已预读 {total_bytes / (1024*1024):.1f}MB 到系统缓存")


def _read_single_file(filepath):
    """Read a single file into system cache to warm up page cache.

    Reads the first 1MB of the file (or full file if smaller).
    This primes the OS page cache so subsequent reads are served from RAM.

    Args:
        filepath: Absolute path to the file to read.

    Returns:
        Number of bytes actually read, or 0 on failure.
    """
    try:
        size = os.path.getsize(filepath)
        if size == 0:
            return 0
        read_size = min(size, 1024 * 1024)
        with open(filepath, 'rb') as f:
            f.read(read_size)
        return read_size
    except (IOError, OSError) as e:
        logger.debug(f"[预加载] 读取文件失败 {filepath}: {e}")
        return 0


def get_preload_status() -> dict:
    """Retrieve the current preload task status.

    Returns:
        Dictionary with keys: in_progress, target_engine, target_size,
        completed, and error.
    """
    with _preload_lock:
        return dict(_preload_state)


def switch_engine(engine_name="voxcpm2") -> Generator:
    """Switch the active engine with full rollback on failure.

    Performs a 5-step engine switch:
    1. VRAM pre-check: verify at least 6.5GB free VRAM is available
    2. Unload current model with aggressive VRAM cleanup
    3. Load new VoxCPM2 model and move sub-components to GPU
    4. Load ASR model
    5. Update global engine state and log success

    If any step fails, automatically rolls back to the previous engine
    state (model, ASR, engine name). All TTSError subclasses are
    re-raised as-is; other exceptions are wrapped as EngineSwitchError.

    Args:
        engine_name: Target engine name (currently only "voxcpm2").

    Yields:
        Tuple of (status_text, audio, sample_rate, format) at each stage.

    Raises:
        InsufficientVRAMError: If free VRAM is below the 6.5GB threshold.
        EngineSwitchError: If the switch fails and rollback is attempted.
    """
    global voxcpm_model, voxcpm_asr, current_engine, current_type, current_size

    import voxcpm
    from funasr import AutoModel

    engine_name = engine_name.strip()
    logger.info(f"[引擎切换] 目标: {engine_name}")

    _model_lock.acquire()
    try:
        prev_engine = current_engine
        prev_voxcpm_model = voxcpm_model
        prev_voxcpm_asr = voxcpm_asr

        # Step 1: VRAM pre-check
        needed_gb = 6.5
        logger.info(f"[引擎切换] 开始 VRAM 预检查...")
        gpu_device = get_nvidia_gpu_device()
        logger.info(f"[引擎切换] 使用 GPU {gpu_device} 进行显存检查")

        if torch.cuda.is_available():
            total = torch.cuda.get_device_properties(gpu_device).total_memory
            allocated = torch.cuda.memory_allocated(gpu_device)
            free = total - allocated
            free_gb = free / 1024**3
        else:
            free_gb = 0

        logger.info(f"[引擎切换] VRAM 检查: 需要 {needed_gb}GB, 可用 {free_gb:.2f}GB")

        if free_gb < needed_gb:
            error_msg = f"显存不足，无法加载 VoxCPM2。需要约 {needed_gb}GB，当前可用 {free_gb:.2f}GB。"
            logger.error(f"[引擎切换] {error_msg}")
            raise InsufficientVRAMError(error_msg)

        # Step 2: Unload current model
        _progress_mgr.update_phase("正在卸载旧引擎...")
        unload_model()

        if torch.cuda.is_available():
            torch.cuda.synchronize(gpu_device)
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            time.sleep(2)
            torch.cuda.empty_cache()
            _progress_mgr.update_phase("正在清理 VRAM...")

        # Step 3: Load VoxCPM2 model
        status_text = "正在加载 VoxCPM2 模型..."
        logger.info(f"[引擎切换] {status_text}")
        _progress_mgr.update_phase("正在加载新引擎...")
        yield status_text, None, None, None

        cuda_device = f"cuda:{get_nvidia_gpu_device()}"
        voxcpm_model = voxcpm.VoxCPM.from_pretrained(
            VOXCPM2_MODEL_PATH,
            optimize=True,
            local_files_only=True,
            zipenhancer_model_id=VOXCPM2_DENOISER_PATH,
        )
        if hasattr(voxcpm_model, 'tts_model'):
            voxcpm_model.tts_model.to(cuda_device)
        if hasattr(voxcpm_model, 'model'):
            voxcpm_model.model.to(cuda_device)
        if hasattr(voxcpm_model, 'codecs'):
            voxcpm_model.codecs.to(cuda_device)
        if hasattr(voxcpm_model, 'vocoder'):
            voxcpm_model.vocoder.to(cuda_device)
        logger.info(f"[引擎切换] VoxCPM 模型加载成功，已移动到 {cuda_device}")

        # Step 4: Load ASR model
        status_text = "正在加载 ASR 模型..."
        logger.info(f"[引擎切换] {status_text}")
        yield status_text, None, None, None

        voxcpm_asr = AutoModel(
            model=VOXCPM2_ASR_PATH,
            disable_pbar=True,
            device=cuda_device,
        )

        # Step 5: Complete
        current_engine = "voxcpm2"
        current_type = "voxcpm2"
        current_size = "voxcpm2"
        status_text = "VoxCPM2 引擎就绪"
        logger.info(f"[引擎切换] {status_text}")
        yield status_text, None, None, None

    except TTSError:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        error_msg = f"引擎切换失败: {type(e).__name__}: {e}\n\n详细错误:\n{tb}"
        logger.error(f"[引擎切换] {error_msg}")

        # Auto-rollback
        logger.info(f"[引擎切换] 开始回滚到之前的引擎状态...")
        try:
            current_engine = prev_engine
            voxcpm_model = prev_voxcpm_model
            voxcpm_asr = prev_voxcpm_asr
            if prev_engine:
                logger.info(f"[引擎切换] 回滚成功: 引擎已恢复为 {prev_engine}")
            else:
                logger.warning(f"[引擎切换] 回滚: 之前没有已加载的引擎，所有状态已置空")
        except Exception as rollback_err:
            logger.error(f"[引擎切换] 回滚失败: {rollback_err}")

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        raise EngineSwitchError(error_msg) from e
    finally:
        _model_lock.release()
