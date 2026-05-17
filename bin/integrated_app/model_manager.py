"""Model management module.

Provides model loading, unloading, engine switching, LRU caching,
progress tracking, GPU memory monitoring, and persona cache warmup.

Refactored for VoxCPM2-only architecture.

State management:
    All core model state (voxcpm_model, voxcpm_asr, current_engine,
    current_type, current_size) is owned by the ModelRegistry singleton
    in ``model_registry.py``.  Module-level variables of the same names
    exist solely as backward-compatible aliases and are kept in sync by
    ``_sync_globals()`` after every mutation.

Sub-modules:
    - cache: LRUCache, AdaptiveLRUCache
    - progress: ProgressManager
    - tracker: GenerationTracker
    - gpu_utils: is_oom_error, free_gpu_memory, get_nvidia_gpu_device,
      get_nvidia_gpu_memory_info, GPUMemoryMonitor
    - prompt_cache: Persistent prompt cache for voice cloning
"""

import gc
import logging
import os
import threading
import time
from collections.abc import Generator

import torch

from .cache import AdaptiveLRUCache, LRUCache
from .config import (
    ROOT_DIR,
    VOXCPM2_ASR_PATH,
    VOXCPM2_DENOISER_PATH,
    VOXCPM2_MODEL_PATH,
)
from .estimator import GenerationTimeEstimator
from .exceptions import (
    EngineSwitchError,
    InsufficientVRAMError,
    TTSError,
)
from .gpu_utils import (
    GPUMemoryMonitor,
    free_gpu_memory,
    get_nvidia_gpu_device,
    get_nvidia_gpu_memory_info,
    is_oom_error,
)
from .model_registry import registry
from .monitor import get_health_monitor
from .progress import ProgressManager
from .tracker import GenerationTracker

# Re-export for backward compatibility — allows `from ..model_manager import xxx`
__all__ = [
    "LRUCache", "AdaptiveLRUCache",
    "ProgressManager",
    "GenerationTracker",
    "GPUMemoryMonitor",
    "get_nvidia_gpu_device", "get_nvidia_gpu_memory_info",
    "is_oom_error", "free_gpu_memory",
]

logger = logging.getLogger("tts_multimodel")

# --- torch.compile cache configuration ---
_TORCH_COMPILE_CACHE_DIR = os.path.join(ROOT_DIR, "torch_compile_cache")
try:
    os.makedirs(_TORCH_COMPILE_CACHE_DIR, exist_ok=True)
    import torch._dynamo as dynamo
    dynamo.config.cache_dir = _TORCH_COMPILE_CACHE_DIR
    logger.info(f"[torch.compile] 编译缓存目录: {_TORCH_COMPILE_CACHE_DIR}")
except Exception as e:
    logger.debug(f"[torch.compile] 缓存配置失败 (可忽略): {e}")




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


# --- Progress Manager --- (imported from .progress)

# --- GPU detection functions --- (imported from .gpu_utils)
# get_nvidia_gpu_device, get_nvidia_gpu_memory_info, GPUMemoryMonitor
# are now in .gpu_utils and re-exported at the top of this module.


# --- Backward-compatible global aliases ---
# These are synced from the ModelRegistry singleton after every mutation.
# External code that does ``from ..model_manager import voxcpm_model``
# will get the value at import time; lazy imports inside functions will
# always see the latest value.
voxcpm_model = registry.voxcpm_model       # None
voxcpm_asr = registry.voxcpm_asr           # None
current_engine = registry.current_engine    # "voxcpm2"
current_type = registry.current_type        # "voxcpm2"
current_size = registry.current_size        # "voxcpm2"

# 音色缓存：存储 (wav_path, ref_text)，由官方 API 在每次生成时计算嵌入
_persona_embedding_cache = AdaptiveLRUCache(default_maxsize=15)
_gen_tracker = GenerationTracker()
_progress_mgr = ProgressManager()
_model_lock = threading.RLock()
_persona_warmup_done = {"done": False}
_persona_warmup_lock = threading.Lock()


def _sync_globals() -> None:
    """Synchronize module-level variables from the ModelRegistry singleton.

    Must be called after every mutation to registry state so that
    external code using ``from ..model_manager import <name>`` inside
    functions sees the latest values.
    """
    global voxcpm_model, voxcpm_asr, current_engine, current_type, current_size
    voxcpm_model = registry.voxcpm_model
    voxcpm_asr = registry.voxcpm_asr
    current_engine = registry.current_engine
    current_type = registry.current_type
    current_size = registry.current_size


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
            from .config import PERSONA_DIR
            from .persona_manager import load_persona_embedding

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
    with _model_lock:
        # Grab references before clearing registry
        old_model = registry.voxcpm_model
        old_asr = registry.voxcpm_asr
        registry.voxcpm_model = None
        registry.voxcpm_asr = None
        if old_model is not None:
            del old_model
        if old_asr is not None:
            del old_asr
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
        _sync_globals()


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
    import voxcpm
    from funasr import AutoModel

    _model_lock.acquire()
    try:
        # Unload current engine if any
        old_model = registry.voxcpm_model
        old_asr = registry.voxcpm_asr
        registry.voxcpm_model = None
        registry.voxcpm_asr = None
        if old_model is not None:
            del old_model
        if old_asr is not None:
            del old_asr
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        time.sleep(1)

        status_text = "正在加载 VoxCPM2 模型..."
        yield status_text, None, None, None
        try:
            new_model = voxcpm.VoxCPM.from_pretrained(
                VOXCPM2_MODEL_PATH,
                optimize=True,
                local_files_only=True,
            )
            # 显式将模型子组件移至 GPU（与引擎切换逻辑保持一致）
            cuda_device = f"cuda:{get_nvidia_gpu_device()}"
            if torch.cuda.is_available():
                for attr in ('tts_model', 'model', 'codecs', 'vocoder'):
                    sub = getattr(new_model, attr, None)
                    if sub is not None and hasattr(sub, 'to'):
                        sub.to(cuda_device)
                        logger.info(f"  VoxCPM2.{attr} -> {cuda_device}")
                # 确保 CUDA 缓存同步
                torch.cuda.synchronize()
                allocated_mb = torch.cuda.memory_allocated() / (1024 ** 2)
                logger.info(f"  VoxCPM2 加载完成，GPU 显存已分配: {allocated_mb:.0f} MB")

            registry.voxcpm_model = new_model

            status_text = "正在加载 ASR 模型..."
            yield status_text, None, None, None
            new_asr = AutoModel(
                model=VOXCPM2_ASR_PATH,
                disable_pbar=True,
                device=cuda_device,
            )
            registry.voxcpm_asr = new_asr
            registry.current_engine = "voxcpm2"
            registry.current_type = "voxcpm2"
            registry.current_size = "voxcpm2"
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
            failed_model = registry.voxcpm_model
            failed_asr = registry.voxcpm_asr
            registry.clear_all()
            if failed_model is not None:
                del failed_model
            if failed_asr is not None:
                del failed_asr
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            status_text = f"VoxCPM2 加载失败: {e}"
            yield status_text, None, None, None
    finally:
        _sync_globals()
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
                logger.info("[预加载] 开始预读 VoxCPM2 模型文件到系统内存...")
                if os.path.exists(VOXCPM2_MODEL_PATH):
                    _read_files_to_cache(VOXCPM2_MODEL_PATH)
                    logger.info("[预加载] VoxCPM2 模型文件已预读到系统缓存")
                else:
                    logger.warning(f"[预加载] VoxCPM2 模型路径不存在: {VOXCPM2_MODEL_PATH}")

                if os.path.exists(VOXCPM2_ASR_PATH):
                    _read_files_to_cache(VOXCPM2_ASR_PATH)
                    logger.info("[预加载] VoxCPM2 ASR 模型文件已预读到系统缓存")

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
    except OSError as e:
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
    import voxcpm
    from funasr import AutoModel

    engine_name = engine_name.strip()
    logger.info(f"[引擎切换] 目标: {engine_name}")

    _model_lock.acquire()
    try:
        # Snapshot previous state for potential rollback
        prev_engine = registry.current_engine
        prev_voxcpm_model = registry.voxcpm_model
        prev_voxcpm_asr = registry.voxcpm_asr

        # Step 1: VRAM pre-check
        needed_gb = 6.5
        logger.info("[引擎切换] 开始 VRAM 预检查...")
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
        new_model = voxcpm.VoxCPM.from_pretrained(
            VOXCPM2_MODEL_PATH,
            optimize=True,
            local_files_only=True,
            zipenhancer_model_id=VOXCPM2_DENOISER_PATH,
        )
        if hasattr(new_model, 'tts_model'):
            new_model.tts_model.to(cuda_device)
        if hasattr(new_model, 'model'):
            new_model.model.to(cuda_device)
        if hasattr(new_model, 'codecs'):
            new_model.codecs.to(cuda_device)
        if hasattr(new_model, 'vocoder'):
            new_model.vocoder.to(cuda_device)
        registry.voxcpm_model = new_model
        logger.info(f"[引擎切换] VoxCPM 模型加载成功，已移动到 {cuda_device}")

        # Step 4: Load ASR model
        status_text = "正在加载 ASR 模型..."
        logger.info(f"[引擎切换] {status_text}")
        yield status_text, None, None, None

        new_asr = AutoModel(
            model=VOXCPM2_ASR_PATH,
            disable_pbar=True,
            device=cuda_device,
        )
        registry.voxcpm_asr = new_asr

        # Step 5: Complete
        registry.current_engine = "voxcpm2"
        registry.current_type = "voxcpm2"
        registry.current_size = "voxcpm2"
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
        logger.info("[引擎切换] 开始回滚到之前的引擎状态...")
        try:
            registry.current_engine = prev_engine
            registry.voxcpm_model = prev_voxcpm_model
            registry.voxcpm_asr = prev_voxcpm_asr
            if prev_engine:
                logger.info(f"[引擎切换] 回滚成功: 引擎已恢复为 {prev_engine}")
            else:
                logger.warning("[引擎切换] 回滚: 之前没有已加载的引擎，所有状态已置空")
        except Exception as rollback_err:
            logger.error(f"[引擎切换] 回滚失败: {rollback_err}")

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        raise EngineSwitchError(error_msg) from e
    finally:
        _sync_globals()
        _model_lock.release()
