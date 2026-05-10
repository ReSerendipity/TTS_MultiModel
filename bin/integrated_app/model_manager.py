# -*- coding: utf-8 -*-
"""Model management: load, unload, engine switch, global state, LRU cache, progress tracking, preloading.
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
    def __init__(self, maxsize: int = 50) -> None:
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, key: str, value: Any) -> None:
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
        self._hits = 0
        self._misses = 0


class AdaptiveLRUCache(LRUCache):
    """LRU cache with adaptive capacity based on GPU memory usage."""

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
        gpu_pct = self._get_gpu_memory_percent()
        for threshold, capacity in self._CAPACITY_MAP:
            if gpu_pct > threshold:
                return capacity
        return 20

    def adapt_capacity(self) -> int:
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
        self.adapt_capacity()
        super().put(key, value)

    def clear(self) -> None:
        with self._adapt_lock:
            self._cache.clear()
            self.reset_stats()


# --- Generation Tracker ---
class GenerationTracker:
    def __init__(self):
        self.queue_depth = 0
        self.avg_gen_time = 15.0
        self._lock = threading.RLock()
        self.phase = "空闲"

    def start_generation(self):
        with self._lock:
            self.queue_depth += 1
            return self.queue_depth

    def end_generation(self, elapsed):
        with self._lock:
            self.avg_gen_time = 0.8 * self.avg_gen_time + 0.2 * elapsed
            self.queue_depth = max(0, self.queue_depth - 1)

    def estimate_wait(self):
        with self._lock:
            return self.avg_gen_time * self.queue_depth

    def status_text(self):
        with self._lock:
            if self.queue_depth == 0:
                return "🟢 空闲"
            wait = self.estimate_wait()
            return f"🟡 队列: {self.queue_depth} | 预计等待: {wait:.0f}秒"


# --- Progress Manager ---
class ProgressManager:
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
        with self._lock:
            self._phase = phase

    def advance_segment(self, phase="推理中", segment_bytes=0):
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
        with self._lock:
            self._total_bytes_processed = total_bytes

    def get_progress_html(self):
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
        if seconds <= 0:
            return "0秒"
        if seconds < 60:
            return f"{int(seconds)}秒"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}分{secs}秒"

    def _estimate_remaining(self):
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
        with self._lock:
            self._is_cancelled = True

    def is_cancelled(self):
        with self._lock:
            return self._is_cancelled

    def add_chars_processed(self, char_count):
        with self._lock:
            self._total_chars_processed += char_count

    def get_speed_stats(self):
        with self._lock:
            elapsed = time.time() - self._start_time if self._start_time > 0 else 0
            chars_per_sec = (self._total_chars_processed / elapsed) if elapsed > 0 else 0
            return {
                "total_chars": self._total_chars_processed,
                "elapsed": elapsed,
                "chars_per_sec": round(chars_per_sec, 1),
            }

    def complete(self):
        with self._lock:
            self._current_segment = self._total_segments
            self._phase = "完成"
            self._is_complete = True

    def schedule_reset(self, delay_seconds=3):
        def _delayed_reset():
            time.sleep(delay_seconds)
            self.reset()
        t = threading.Thread(target=_delayed_reset, daemon=True)
        t.start()


def get_nvidia_gpu_device():
    """Find the NVIDIA GPU device index. ONLY supports NVIDIA GPUs with CUDA."""
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
    """Get memory info for the primary NVIDIA GPU."""
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
    @staticmethod
    def get_vram_info():
        if not torch.cuda.is_available():
            return {"total": 0, "used": 0, "free": 0}
        total, allocated, reserved, free = get_nvidia_gpu_memory_info()
        return {"total": total, "used": allocated, "free": free}

    @staticmethod
    def can_load_model(model_name="voxcpm2"):
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
    return _persona_embedding_cache.get_stats()


def warmup_persona_cache() -> None:
    """Asynchronously preload the 5 most recently used personas into cache."""
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
    """Check if model is ready (not locked)."""
    if not _model_lock.acquire(blocking=False):
        return False
    _model_lock.release()
    return True


def unload_model() -> None:
    """Unload current VoxCPM2 model and release VRAM."""
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
    """Load VoxCPM2 engine (generator mode for UI progress feedback)."""
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
    """Background preload model files into system RAM (not GPU VRAM)."""
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
    """Read model files into system page cache."""
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
    """Read single file into system cache, return bytes read."""
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
    """Get current preload task status."""
    with _preload_lock:
        return dict(_preload_state)


def switch_engine(engine_name="voxcpm2") -> Generator:
    """Switch engine (generator mode for UI progress feedback).
    Simplified for VoxCPM2-only architecture.
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
