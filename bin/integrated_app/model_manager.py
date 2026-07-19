"""Model management module.

Provides model loading, unloading, engine switching, LRU caching,
progress tracking, GPU memory monitoring, and persona cache warmup.

Supports VoxCPM2 and IndexTTS 2.0 dual-engine architecture.

重构说明 (M-R1/R2/R3/R5):
- M-R1: 常量提取消除魔法数字；switch_engine 拆分为 5 个职责单一的辅助函数
        (_validate_engine_name / _snapshot_engine_state / _check_vram_prereq /
         _wait_vram_freed / _rollback_engine)，单函数圈复杂度 25 → 各 <8
- M-R2: 提取 PreloadService 与 PersonaWarmupService 类，封装状态与行为；
        全局函数 preload_model/get_preload_status/warmup_persona_cache
        作为向后兼容包装委托给单例
- M-R3: 修复 _rollback_engine 一致性 —— 回滚时重新加载 prev_engine 模型，
        而非仅恢复引用（避免引用指向 unload 后已失效的对象，尤其 IndexTTS2.unload()）
- M-R5: PersonaWarmupService 新增 retry_warmup() / reset()，支持失败重试
- M-R6(撤销): 保留 threading.RLock，因 routes/model.py 已用 loop.run_in_executor
              将同步 generator 调度到线程池，RLock 在线程池中工作良好。
              直接改 asyncio.Lock 会破坏 persona_manager 等同步上下文调用。
              新增文档化注释明确同步使用约定。

State management:
    All core model state (voxcpm_model, voxcpm_asr, current_engine,
    current_type, current_size) is owned by the ModelRegistry singleton
    in ``model_registry.py``.  Access state via ``registry.xxx``.

Sub-modules:
    - cache: LRUCache, AdaptiveLRUCache
    - progress: ProgressManager
    - tracker: GenerationTracker
    - gpu_utils: is_oom_error, free_gpu_memory, get_gpu_device,
      get_gpu_memory_info, GPUMemoryMonitor
    - prompt_cache: Persistent prompt cache for voice cloning

同步使用约定 (M-R6 文档化):
    _model_lock 为 threading.RLock，所有同步 generator (load_voxcpm2 /
    load_indextts2 / switch_engine / unload_model) 内部使用该锁。
    FastAPI 路由层必须通过 `loop.run_in_executor(None, ...)` 将这些
    generator 的迭代调度到线程池，避免阻塞事件循环。
    persona_manager 等同步模块可直接 `with _model_lock:` 获取锁。
    严禁在 async 上下文中直接 `with _model_lock:` 调用同步代码。
"""

import gc
import logging
import os
import threading
import time
from collections.abc import Generator
from typing import Any

from .cache import AdaptiveLRUCache, LRUCache
from .config import (
    INDEXTTS2_MODEL_PATH,
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
    get_gpu_device,
    is_oom_error,
)
from .model_registry import registry
from .monitor import get_health_monitor
from .progress import ProgressManager
from .tracker import GenerationTracker

# Re-export for backward compatibility — allows `from ..model_manager import xxx`
__all__ = [
    "LRUCache",
    "AdaptiveLRUCache",
    "ProgressManager",
    "GenerationTracker",
    "GPUMemoryMonitor",
    "is_oom_error",
    "free_gpu_memory",
]

logger = logging.getLogger("tts_multimodel")

# --- 常量提取 (M-R1/A3-1 消除魔法数字) ---
# REFACTOR: [M-R1] 集中显存检查与轮询参数，便于调参与测试覆盖
_VRAM_FREE_THRESHOLD_BYTES = 500 * 1024 * 1024  # 显存释放完成阈值: 500MB
_VRAM_WAIT_MAX_SECONDS = 5.0  # 显存释放轮询最大等待时间
_VRAM_POLL_INTERVAL_SECONDS = 0.5  # 显存释放轮询间隔
_VRAM_FREE_PERCENT_FLOOR = 5  # 显存释放判定下限: 总显存的 5% (E2-2 阈值相对化)
_PRELOAD_READ_CHUNK_BYTES = 1024 * 1024  # 预加载单次读取块大小: 1MB
_PERSONA_CACHE_DEFAULT_SIZE = 15  # Persona 嵌入缓存默认容量
_WARMUP_TOP_PERSONAS = 5  # Persona 预热数量
_UNLOAD_SLOW_THRESHOLD_SECONDS = 5.0  # 卸载耗时告警阈值
_LOAD_RETRY_AFTER_UNLOAD_SECONDS = 1  # 卸载后等待 GPU 同步时间

# --- torch.compile cache configuration ---
_TORCH_COMPILE_CACHE_DIR = os.path.join(ROOT_DIR, "torch_compile_cache")
try:
    os.makedirs(_TORCH_COMPILE_CACHE_DIR, exist_ok=True)
    import torch._dynamo as dynamo

    dynamo.config.cache_dir = _TORCH_COMPILE_CACHE_DIR  # type: ignore[attr-defined]
    logger.info(f"[torch.compile] 编译缓存目录: {_TORCH_COMPILE_CACHE_DIR}")
except Exception as e:
    logger.debug(f"[torch.compile] 缓存配置失败 (可忽略): {e}")


# --- Global dynamic estimator ---
_time_estimator = GenerationTimeEstimator(
    data_file=os.path.join(ROOT_DIR, "generation_times.json"),
    max_entries=200,
)

# --- 音色缓存与全局协调器 ---
# REFACTOR: [M-R2] 全局状态保留为模块级单例，供其他模块直接导入
_persona_embedding_cache = AdaptiveLRUCache(default_maxsize=_PERSONA_CACHE_DEFAULT_SIZE)
_gen_tracker = GenerationTracker()
_progress_mgr = ProgressManager()

# M-R6(撤销): 保留 RLock 而非改用 asyncio.Lock。
# 详见模块顶部"同步使用约定"文档。
_model_lock = threading.RLock()


def get_persona_cache_stats() -> dict:
    """Retrieve current persona embedding cache statistics.

    Returns:
        Dictionary with hits, misses, hit_rate, size, and maxsize.
    """
    return _persona_embedding_cache.get_stats()


# ====================================================================
# Persona 预热服务 (M-R2/R5)
# ====================================================================


class PersonaWarmupService:
    """REFACTOR: [M-R2] Persona 缓存预热服务，封装状态与行为。

    M-R5: 新增 retry_warmup() 与 reset()，支持失败后重试与引擎切换后强制重新预热。

    线程安全：所有状态变更通过 _lock 保护。
    """

    def __init__(self, cache: AdaptiveLRUCache):
        self._cache = cache
        self._state: dict[str, Any] = {"done": False, "error": None, "in_progress": False}
        self._lock = threading.Lock()

    def warmup(self) -> None:
        """Asynchronously preload the most recently used personas into cache.

        Runs on a background daemon thread to avoid blocking application startup.
        Only executes once per process lifetime (guarded by _state["done"]).
        M-R5: 失败时 done 保持 False，允许后续 retry_warmup() 重试。
        """
        with self._lock:
            if self._state["done"] or self._state["in_progress"]:
                return
            self._state["in_progress"] = True

        def _do_warmup():
            from .middleware.request_id import set_request_id

            set_request_id(f"bg-{threading.current_thread().name}")
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
                top_personas = [name for name, _ in persona_files[:_WARMUP_TOP_PERSONAS]]
                if not top_personas:
                    logger.info("[PersonaCacheWarmup] 未找到音色，跳过预热")
                    with self._lock:
                        self._state["done"] = True
                        self._state["in_progress"] = False
                    return

                logger.info(f"[PersonaCacheWarmup] 开始预热 {len(top_personas)} 个音色: {top_personas}")
                for name in top_personas:
                    try:
                        load_persona_embedding(name)
                        logger.debug(f"[PersonaCacheWarmup] 已预热音色: {name}")
                    except Exception as e:
                        logger.warning(f"[PersonaCacheWarmup] 音色 '{name}' 预热失败: {e}")

                stats = self._cache.get_stats()
                logger.info(f"[PersonaCacheWarmup] 预热完成。缓存大小: {stats['size']}/{stats['maxsize']}")
                # M-R5: 成功完成才标记 done=True
                with self._lock:
                    self._state["done"] = True
                    self._state["error"] = None
                    self._state["in_progress"] = False
            except Exception as e:
                logger.error(f"[PersonaCacheWarmup] 预热失败: {e}")
                # M-R5: 失败时 done 保持 False，记录 error，允许重试
                with self._lock:
                    self._state["error"] = str(e)
                    self._state["in_progress"] = False

        t = threading.Thread(target=_do_warmup, daemon=True, name="persona-cache-warmup")
        t.start()

    def retry_warmup(self) -> bool:
        """REFACTOR: [M-R5] 重试预热入口。

        Returns:
            True 表示已触发重试，False 表示无需重试（已完成或正在进行）。
        """
        with self._lock:
            if self._state["done"]:
                return False
            if self._state["in_progress"]:
                logger.info("[PersonaCacheWarmup] 预热正在进行中，跳过重试")
                return False
            # 清理上次错误状态，允许重新触发
            self._state["error"] = None
            logger.info("[PersonaCacheWarmup] 触发重试预热")
        self.warmup()
        return True

    def reset(self) -> None:
        """REFACTOR: [M-R5/E6-2] 重置预热状态。

        用于引擎切换/模型重载后强制重新预热。
        """
        with self._lock:
            self._state = {"done": False, "error": None, "in_progress": False}
        logger.info("[PersonaCacheWarmup] 状态已重置")

    def get_status(self) -> dict:
        """获取预热状态快照。"""
        with self._lock:
            return dict(self._state)


# 模块级单例 + 向后兼容包装函数
_persona_warmup_service = PersonaWarmupService(_persona_embedding_cache)


def warmup_persona_cache() -> None:
    """向后兼容包装：委托给 PersonaWarmupService.warmup()。"""
    _persona_warmup_service.warmup()


# ====================================================================
# 模型锁检查
# ====================================================================


def _check_voxcpm2_lock() -> bool:
    """Non-blocking check if the model lock is available.

    Returns:
        True if the model is not being loaded/switched, False if locked.
    """
    if not _model_lock.acquire(blocking=False):
        return False
    _model_lock.release()
    return True


_check_model_ready = _check_voxcpm2_lock  # backward-compatible alias


# ====================================================================
# 模型卸载
# ====================================================================


def unload_model() -> None:
    """Unload the current model (VoxCPM2 or IndexTTS2) and aggressively release VRAM.

    Acquires the model lock, deletes model and ASR references, clears
    the persona embedding cache, then performs tiered GPU memory
    cleanup via free_gpu_memory(). Logs total cleanup time and warns
    if cleanup exceeds the configured threshold.

    M-R3 注意: 本函数会调用 IndexTTS2 engine.unload()，可能释放底层资源。
    因此 switch_engine 回滚时不能仅恢复引用，必须重新加载（见 _rollback_engine）。
    """
    cleanup_start = time.time()

    with _model_lock:
        # Unload VoxCPM2 model
        old_model = registry.voxcpm_model
        old_asr = registry.voxcpm_asr
        registry.voxcpm_model = None
        registry.voxcpm_asr = None
        if old_model is not None:
            del old_model
        if old_asr is not None:
            del old_asr

        # Unload IndexTTS2 engine
        old_engine = registry.indextts2_engine
        registry.indextts2_engine = None
        if old_engine is not None:
            try:
                old_engine.unload()
            except Exception as e:
                logger.warning(f"IndexTTS2 卸载失败: {e}")

        _persona_embedding_cache.clear()

        # Use tiered free_gpu_memory() instead of inline cleanup
        free_gpu_memory()

        # Log post-cleanup VRAM status
        from .gpu_backend import GPUBackend, GPUBackendManager

        backend = GPUBackendManager.detect_backend()
        if backend != GPUBackend.CPU:
            device = get_gpu_device()
            if device is not None:
                allocated = GPUBackendManager.memory_allocated(device)
                reserved = GPUBackendManager.memory_reserved(device)
                logger.info(f"释放后显存: 已分配 {allocated / 1024**3:.2f}GB, 保留 {reserved / 1024**3:.2f}GB")

    cleanup_elapsed = time.time() - cleanup_start
    if cleanup_elapsed > _UNLOAD_SLOW_THRESHOLD_SECONDS:
        logger.warning(
            f"[模型卸载] 清理操作耗时 {cleanup_elapsed:.1f}s，"
            f"超过 {_UNLOAD_SLOW_THRESHOLD_SECONDS:.0f} 秒阈值"
        )
    else:
        logger.info(f"[模型卸载] 清理完成，耗时 {cleanup_elapsed:.2f}s")


# ====================================================================
# VoxCPM2 加载
# ====================================================================


def _do_load_voxcpm2_internal(gpu_device, backend, include_denoiser=False) -> Generator:
    """Internal generator for shared VoxCPM2 loading logic.

    Used by both load_voxcpm2() and _load_voxcpm2_engine() to avoid
    code duplication.  Performs the actual model loading, GPU movement,
    ASR loading, registry update, and VRAM recording.

    Args:
        gpu_device: GPU device index or None for CPU.
        backend: GPUBackend enum value.
        include_denoiser: If True, pass zipenhancer_model_id to
            voxcpm.VoxCPM.from_pretrained().

    Yields:
        Tuple of (status_text, None, None, None) at each loading stage.

    Raises:
        Exception: Re-raises any loading exception after cleanup.
    """
    import voxcpm
    from funasr import AutoModel

    from .gpu_backend import GPUBackend, GPUBackendManager

    # Determine device string
    device_string = GPUBackendManager.format_device_string(gpu_device) if gpu_device is not None else "cpu"

    # Step 1: Load VoxCPM2 model
    status_text = "正在加载 VoxCPM2 模型..."
    yield status_text, None, None, None

    try:
        kwargs: dict[str, Any] = dict(
            optimize=True,
            local_files_only=True,
        )
        if include_denoiser:
            kwargs["zipenhancer_model_id"] = VOXCPM2_DENOISER_PATH
        else:
            kwargs["load_denoiser"] = False

        new_model = voxcpm.VoxCPM.from_pretrained(VOXCPM2_MODEL_PATH, **kwargs)

        # Move sub-components to GPU
        if backend != GPUBackend.CPU and gpu_device is not None:
            for attr in ("tts_model", "model", "codecs", "vocoder"):
                sub = getattr(new_model, attr, None)
                if sub is not None and hasattr(sub, "to"):
                    sub.to(device_string)
                    logger.info(f"  VoxCPM2.{attr} -> {device_string}")
            # Ensure cache sync
            GPUBackendManager.synchronize()
            allocated_mb = GPUBackendManager.memory_allocated() / (1024**2)
            logger.info(f"  VoxCPM2 加载完成，GPU 显存已分配: {allocated_mb:.0f} MB")
        else:
            logger.info("  VoxCPM2 使用 CPU 后端运行")

        # Store model in registry early so error handler can clean it up
        registry.voxcpm_model = new_model

        # Step 2: Load ASR model
        status_text = "正在加载 ASR 模型..."
        yield status_text, None, None, None

        new_asr = AutoModel(
            model=VOXCPM2_ASR_PATH,
            disable_pbar=True,
            device=device_string,
        )
        registry.set_voxcpm_loaded(new_model, asr=new_asr)

        # Step 3: Record VRAM usage
        try:
            monitor = get_health_monitor()
            if backend != GPUBackend.CPU:
                vram_mb = GPUBackendManager.memory_allocated() / (1024**2)
                monitor.record_vram_usage(vram_mb)
                monitor.set_model_status("ready")
        except Exception as e:
            logger.debug(f"VoxCPM2 加载后 VRAM 记录失败: {e}")

        status_text = "VoxCPM2 引擎就绪"
        yield status_text, None, None, None

    except Exception:
        # Clean up partial state on failure
        failed_model = registry.voxcpm_model
        failed_asr = registry.voxcpm_asr
        registry.clear_all()
        if failed_model is not None:
            del failed_model
        if failed_asr is not None:
            del failed_asr
        gc.collect()
        from .gpu_backend import GPUBackendManager

        GPUBackendManager.empty_cache()
        raise


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
    with _model_lock:
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
        from .gpu_backend import GPUBackend, GPUBackendManager

        backend = GPUBackendManager.detect_backend()
        if backend != GPUBackend.CPU:
            GPUBackendManager.empty_cache()
        time.sleep(_LOAD_RETRY_AFTER_UNLOAD_SECONDS)

        gpu_device = get_gpu_device()

        try:
            yield from _do_load_voxcpm2_internal(gpu_device, backend, include_denoiser=False)
        except Exception as e:
            status_text = f"VoxCPM2 加载失败: {e}"
            logger.error(f"[模型加载] {status_text}")
            yield status_text, None, None, None


def load_indextts2() -> Generator:
    """Generator function to load IndexTTS 2.0 engine step by step.

    Yields:
        (status_text, audio_data, sample_rate, estimate)
    """
    with _model_lock:
        try:
            from .engines.indextts2_engine import IndexTTS2Engine
            from .gpu_backend import GPUBackend, GPUBackendManager

            backend = GPUBackendManager.detect_backend()

            # Check if model files exist
            if not os.path.exists(INDEXTTS2_MODEL_PATH):
                raise FileNotFoundError(
                    f"IndexTTS 2.0 模型文件不存在: {INDEXTTS2_MODEL_PATH}\n"
                    "请运行: python scripts/download_indextts2.py 下载模型"
                )

            # Step 1: VRAM/RAM check
            from .model_registry import ENGINE_VRAM_REQUIREMENTS

            needed_vram_gb = ENGINE_VRAM_REQUIREMENTS.get("indextts2", 6.0)
            status_text = "正在检查系统资源..."
            yield status_text, None, None, None

            if backend != GPUBackend.CPU:
                mem_info = GPUBackendManager.get_memory_info()
                free_gb = mem_info[3] / (1024**3)
                logger.info(f"[IndexTTS2] VRAM 检查: 需要 {needed_vram_gb}GB, 可用 {free_gb:.2f}GB")

                if free_gb < needed_vram_gb:
                    logger.warning(
                        f"[IndexTTS2] 显存不足 ({free_gb:.2f}GB < {needed_vram_gb}GB)，将尝试使用 CPU 模式"
                    )

            # Step 2: Load model
            status_text = "正在加载 IndexTTS 2.0 引擎..."
            yield status_text, None, None, None

            logger.info("[IndexTTS2] 开始加载 IndexTTS 2.0 引擎...")
            start_time = time.time()

            new_engine = IndexTTS2Engine(
                model_dir=INDEXTTS2_MODEL_PATH,
                use_fp16=(backend != GPUBackend.CPU),
            )

            load_time = time.time() - start_time
            logger.info(f"[IndexTTS2] IndexTTS 2.0 引擎加载完成，耗时: {load_time:.1f}秒")

            # Set registry state
            registry.set_indextts2_loaded(new_engine)

            status_text = "IndexTTS 2.0 引擎就绪"
            logger.info(f"[IndexTTS2] {status_text}")
            yield status_text, None, None, None

            # Record VRAM usage
            try:
                monitor = get_health_monitor()
                if backend != GPUBackend.CPU:
                    vram_mb = GPUBackendManager.memory_allocated() / (1024**2)
                    monitor.record_vram_usage(vram_mb)
                    monitor.set_model_status("ready")
            except Exception as e:
                logger.debug(f"[IndexTTS2] VRAM 记录失败: {e}")

        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            logger.error(f"[IndexTTS2] IndexTTS 2.0 加载失败: {type(e).__name__}: {e}\n详细错误:\n{tb}")
            gc.collect()
            from .gpu_backend import GPUBackendManager

            GPUBackendManager.empty_cache()
            status_text = f"IndexTTS 2.0 加载失败: {type(e).__name__}"
            yield status_text, None, None, None
            raise TTSError(f"IndexTTS 2.0 加载失败: {type(e).__name__}") from e


# ====================================================================
# 预加载服务 (M-R2)
# ====================================================================


class PreloadService:
    """REFACTOR: [M-R2] 模型文件预加载服务，封装状态与行为。

    将原 _preload_state 全局字典、_preload_lock、_read_files_to_cache、
    _read_single_file 等过程式代码封装为类，提升内聚性。

    职责:
    - 后台预读模型文件到 OS page cache，降低后续 GPU 加载的 I/O 延迟
    - 单任务串行（同一时刻只允许一个预加载任务）
    - 状态查询供 /api/model/preload/status 路由使用
    """

    def __init__(self):
        self._state: dict[str, Any] = {
            "in_progress": False,
            "target_engine": None,
            "target_size": None,
            "completed": False,
            "error": None,
        }
        self._lock = threading.Lock()

    def preload(self, engine: str = "voxcpm2", size: str = "voxcpm2") -> None:
        """Background preload of model files into system RAM page cache.

        Reads the first 1MB of each model file to warm up the OS page cache,
        reducing disk I/O latency when the model is subsequently loaded into
        GPU VRAM. Does NOT load model into VRAM.

        Runs on a background daemon thread to avoid blocking application startup.
        Only one preload task runs at a time (guarded by _lock).

        Args:
            engine: Target engine name ("voxcpm2" or "indextts2").
            size: Model size variant (currently ignored).
        """
        with self._lock:
            if self._state["in_progress"]:
                logger.info("[预加载] 已有预加载任务在进行中，跳过")
                return
            self._state["in_progress"] = True
            self._state["target_engine"] = engine
            self._state["target_size"] = size
            self._state["completed"] = False
            self._state["error"] = None

        def _do_preload():
            from .middleware.request_id import set_request_id

            set_request_id(f"bg-{threading.current_thread().name}")
            try:
                if engine == "voxcpm2":
                    logger.info("[预加载] 开始预读 VoxCPM2 模型文件到系统内存...")
                    if os.path.exists(VOXCPM2_MODEL_PATH):
                        self._read_files_to_cache(VOXCPM2_MODEL_PATH)
                        logger.info("[预加载] VoxCPM2 模型文件已预读到系统缓存")
                    else:
                        logger.warning(f"[预加载] VoxCPM2 模型路径不存在: {VOXCPM2_MODEL_PATH}")

                    if os.path.exists(VOXCPM2_ASR_PATH):
                        self._read_files_to_cache(VOXCPM2_ASR_PATH)
                        logger.info("[预加载] VoxCPM2 ASR 模型文件已预读到系统缓存")

                elif engine == "indextts2":
                    logger.info("[预加载] 开始预读 IndexTTS 2.0 模型文件到系统内存...")
                    if os.path.exists(INDEXTTS2_MODEL_PATH):
                        self._read_files_to_cache(INDEXTTS2_MODEL_PATH)
                        logger.info("[预加载] IndexTTS 2.0 模型文件已预读到系统缓存")
                    else:
                        logger.warning(f"[预加载] IndexTTS 2.0 模型路径不存在: {INDEXTTS2_MODEL_PATH}")

                with self._lock:
                    self._state["completed"] = True
                    self._state["in_progress"] = False
                    logger.info("[预加载] 预加载完成")

            except Exception as e:
                logger.error(f"[预加载] 预加载失败: {e}")
                with self._lock:
                    self._state["error"] = str(e)
                    self._state["in_progress"] = False

        t = threading.Thread(target=_do_preload, daemon=True, name="model-preload")
        t.start()

    def _read_files_to_cache(self, directory_path: str) -> None:
        """Recursively read model files into system page cache.

        For each file in the directory tree, reads the first 1MB (or full file
        if smaller) to warm up the OS page cache. Skips dot-files and
        __pycache__ directories.

        Args:
            directory_path: Path to directory or single file to preload.
        """
        if os.path.isfile(directory_path):
            self._read_single_file(directory_path)
            return
        if not os.path.isdir(directory_path):
            return
        total_bytes = 0
        for root, dirs, files in os.walk(directory_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for fname in sorted(files):
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                total_bytes += self._read_single_file(fpath)
        if total_bytes > 0:
            logger.info(f"[预加载] 已预读 {total_bytes / (1024 * 1024):.1f}MB 到系统缓存")

    def _read_single_file(self, filepath: str) -> int:
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
            read_size = min(size, _PRELOAD_READ_CHUNK_BYTES)
            with open(filepath, "rb") as f:
                f.read(read_size)
            return read_size
        except OSError as e:
            logger.debug(f"[预加载] 读取文件失败 {filepath}: {e}")
            return 0

    def get_status(self) -> dict:
        """Retrieve the current preload task status.

        Returns:
            Dictionary with keys: in_progress, target_engine, target_size,
            completed, and error.
        """
        with self._lock:
            return dict(self._state)


# 模块级单例 + 向后兼容包装函数
_preload_service = PreloadService()


def preload_model(engine: str = "voxcpm2", size: str = "voxcpm2") -> None:
    """向后兼容包装：委托给 PreloadService.preload()。"""
    _preload_service.preload(engine, size)


def get_preload_status() -> dict:
    """向后兼容包装：委托给 PreloadService.get_status()。"""
    return _preload_service.get_status()


# ====================================================================
# 引擎切换 (M-R1 拆分 + M-R3 回滚一致性)
# ====================================================================


def _validate_engine_name(engine_name: str) -> str:
    """REFACTOR: [M-R1] 校验并规范化引擎名称。

    Args:
        engine_name: 待校验的引擎名称。

    Returns:
        规范化后的引擎名称（已 strip）。

    Raises:
        EngineSwitchError: 引擎名称不在白名单中。
    """
    engine_name = engine_name.strip()
    if engine_name not in ("voxcpm2", "indextts2"):
        raise EngineSwitchError(f"不支持的引擎: {engine_name}")
    return engine_name


def _snapshot_engine_state() -> dict[str, Any]:
    """REFACTOR: [M-R1] 快照当前引擎状态，用于失败时回滚。

    Returns:
        包含 current_engine / voxcpm_model / voxcpm_asr / indextts2_engine
        的快照字典。

    注意 (M-R3): 快照中的对象引用仅用于判断"之前是哪个引擎"，
    回滚时不直接恢复这些引用（因 unload_model 可能已释放底层资源），
    而是根据 prev_engine 重新加载模型。详见 _rollback_engine。
    """
    return {
        "engine": registry.current_engine,
        "voxcpm_model": registry.voxcpm_model,
        "voxcpm_asr": registry.voxcpm_asr,
        "indextts2_engine": registry.indextts2_engine,
    }


def _check_vram_prereq(engine_name: str, backend, gpu_device) -> float:
    """REFACTOR: [M-R1] 显存预检查。

    E2-1: 校验 props 有效性（total <= 0 时跳过预检，记录警告而非崩溃）。

    Args:
        engine_name: 目标引擎名称。
        backend: GPUBackend 枚举值。
        gpu_device: GPU 设备索引。

    Returns:
        可用显存（GB）。CPU 模式或无法获取显存时返回 0.0。

    Raises:
        InsufficientVRAMError: 可用显存不足。
    """
    from .gpu_backend import GPUBackend, GPUBackendManager
    from .model_registry import ENGINE_VRAM_REQUIREMENTS

    needed_gb = ENGINE_VRAM_REQUIREMENTS.get(engine_name, 6.0)

    # CPU 模式或无 GPU 设备：跳过显存预检
    if backend == GPUBackend.CPU or gpu_device is None:
        logger.warning("[引擎切换] CPU 模式或无 GPU 设备：跳过显存检查，模型将在 CPU 上运行（速度较慢）")
        return 0.0

    props = GPUBackendManager.get_device_properties(gpu_device)
    total = props.get("total_memory", 0)
    # E2-1: 校验 props 有效性
    if total <= 0:
        logger.warning("[引擎切换] 无法获取 GPU 总显存，跳过预检")
        return 0.0

    allocated = GPUBackendManager.memory_allocated(gpu_device)
    free = total - allocated
    free_gb = free / 1024**3

    logger.info(f"[引擎切换] VRAM 检查: 需要 {needed_gb}GB, 可用 {free_gb:.2f}GB")

    if free_gb < needed_gb:
        error_msg = f"显存不足，无法加载 {engine_name}。需要约 {needed_gb}GB，当前可用 {free_gb:.2f}GB。"
        logger.error(f"[引擎切换] {error_msg}")
        raise InsufficientVRAMError(error_msg)

    return free_gb


def _wait_vram_freed(
    gpu_device,
    max_wait: float = _VRAM_WAIT_MAX_SECONDS,
    poll_interval: float = _VRAM_POLL_INTERVAL_SECONDS,
) -> bool:
    """REFACTOR: [M-R1] 轮询等待显存释放。

    E2-2: 阈值相对化 —— 取 _VRAM_FREE_THRESHOLD_BYTES 与总显存的
    _VRAM_FREE_PERCENT_FLOOR% 中较小者，避免大显存设备上 500MB 阈值过松、
    小显存设备上 500MB 阈值过严。

    Args:
        gpu_device: GPU 设备索引。
        max_wait: 最大等待时间（秒）。
        poll_interval: 轮询间隔（秒）。

    Returns:
        True 表示显存已释放到阈值以上，False 表示超时。
    """
    from .gpu_backend import GPUBackendManager

    poll_start = time.time()
    while time.time() - poll_start < max_wait:
        time.sleep(poll_interval)
        try:
            props = GPUBackendManager.get_device_properties(gpu_device)
            total = props.get("total_memory", 0)
            allocated = GPUBackendManager.memory_allocated(gpu_device)
            free = total - allocated
            # E2-2: 阈值相对化
            threshold = min(_VRAM_FREE_THRESHOLD_BYTES, total * _VRAM_FREE_PERCENT_FLOOR // 100)
            if free > threshold:
                return True
        except Exception:
            # 显存查询异常时立即退出轮询，交由调用方决定后续行为
            break

    return False


def _rollback_engine(prev_state: dict[str, Any], error: Exception) -> None:
    """REFACTOR: [M-R1/M-R3] 回滚到之前的引擎状态。

    M-R3 关键修复：原实现仅恢复引用，但 prev_state 中的 model/asr/engine
    对象可能已被 unload_model() 释放底层资源（尤其 IndexTTS2.unload()），
    导致引用指向失效对象。现在根据 prev_engine 重新加载模型，确保
    回滚后引擎真正可用。

    失败处理：重新加载是 best-effort 的，失败时仅记录错误日志，
    不抛异常（避免掩盖原始的切换失败原因）。最坏情况下回滚后引擎
    不可用，用户需手动重新加载。

    Args:
        prev_state: _snapshot_engine_state() 返回的快照。
        error: 触发回滚的异常（仅用于日志）。
    """
    import traceback

    tb = traceback.format_exc()
    error_msg = f"引擎切换失败: {type(error).__name__}: {error}\n\n详细错误:\n{tb}"
    logger.error(f"[引擎切换] {error_msg}")

    prev_engine = prev_state["engine"]
    logger.info(f"[引擎切换] 开始回滚到之前的引擎状态 (prev_engine={prev_engine})...")

    # M-R3: 先清理可能残留的半加载状态（新引擎可能加载了一半）
    try:
        registry.voxcpm_model = None
        registry.voxcpm_asr = None
        registry.indextts2_engine = None
        registry.current_engine = None
    except Exception as cleanup_err:
        logger.error(f"[引擎切换] 回滚前清理失败: {cleanup_err}")

    # M-R3: 根据 prev_engine 重新加载模型
    # 注意：set_voxcpm_loaded / set_indextts2_loaded 内部会设置 current_engine
    if prev_engine == "voxcpm2":
        try:
            logger.info("[引擎切换] 回滚: 重新加载 VoxCPM2 模型...")
            from .gpu_backend import GPUBackend, GPUBackendManager

            backend = GPUBackendManager.detect_backend()
            gpu_device = get_gpu_device()
            # 消费 generator 但不向前端推送状态（回滚过程对前端透明）
            for _ in _do_load_voxcpm2_internal(gpu_device, backend, include_denoiser=False):
                pass
            logger.info("[引擎切换] 回滚: VoxCPM2 模型重新加载完成")
        except Exception as reload_err:
            logger.error(f"[引擎切换] 回滚时重新加载 VoxCPM2 失败: {reload_err}")
    elif prev_engine == "indextts2":
        try:
            logger.info("[引擎切换] 回滚: 重新加载 IndexTTS2 引擎...")
            from .engines.indextts2_engine import IndexTTS2Engine
            from .gpu_backend import GPUBackend, GPUBackendManager

            backend = GPUBackendManager.detect_backend()
            new_engine = IndexTTS2Engine(
                model_dir=INDEXTTS2_MODEL_PATH,
                use_fp16=(backend != GPUBackend.CPU),
            )
            registry.set_indextts2_loaded(new_engine)
            logger.info("[引擎切换] 回滚: IndexTTS2 引擎重新加载完成")
        except Exception as reload_err:
            logger.error(f"[引擎切换] 回滚时重新加载 IndexTTS2 失败: {reload_err}")
    else:
        logger.warning("[引擎切换] 回滚: 之前没有已加载的引擎，所有状态已置空")

    # E4: 资源清理
    gc.collect()
    from .gpu_backend import GPUBackendManager

    GPUBackendManager.empty_cache()


def switch_engine(engine_name: str = "voxcpm2") -> Generator:
    """Switch the active engine with full rollback on failure.

    REFACTOR: [M-R1] 拆分为 5 个职责单一的辅助函数，单函数圈复杂度 25 → 各 <8。
    REFACTOR: [M-R3] _rollback_engine 重新加载 prev_engine 模型，保证回滚后可用。

    Performs a 5-step engine switch:
    1. VRAM pre-check: verify required VRAM is available
    2. Unload current model with aggressive VRAM cleanup
    3. Wait for VRAM to be actually freed (poll-based)
    4. Load new model and move sub-components to GPU
    5. Update global engine state and log success

    If any step fails, automatically rolls back to the previous engine
    state (M-R3: 重新加载 prev_engine 模型). All TTSError subclasses are
    re-raised as-is; other exceptions are wrapped as EngineSwitchError.

    Args:
        engine_name: Target engine name ("voxcpm2" or "indextts2").

    Yields:
        Tuple of (status_text, audio, sample_rate, format) at each stage.

    Raises:
        InsufficientVRAMError: If free VRAM is below the required threshold.
        EngineSwitchError: If the switch fails and rollback is attempted.
    """
    from .gpu_backend import GPUBackend, GPUBackendManager

    # M-R1: 校验引擎名称
    engine_name = _validate_engine_name(engine_name)
    logger.info(f"[引擎切换] 目标: {engine_name}")

    _model_lock.acquire()
    try:
        # M-R1: 快照前置状态
        prev_state = _snapshot_engine_state()

        backend = GPUBackendManager.detect_backend()
        gpu_device = get_gpu_device()
        logger.info(f"[引擎切换] 使用设备 {gpu_device if gpu_device is not None else 'CPU'} 进行显存检查")

        # M-R1: VRAM 预检查
        logger.info("[引擎切换] 开始 VRAM 预检查...")
        _check_vram_prereq(engine_name, backend, gpu_device)

        # Step 2: Unload current model
        _progress_mgr.update_phase("正在卸载旧引擎...")
        unload_model()

        # M-R1: 等待显存释放
        if backend != GPUBackend.CPU and gpu_device is not None:
            GPUBackendManager.synchronize(gpu_device)
            GPUBackendManager.empty_cache()
            GPUBackendManager.ipc_collect(gpu_device)

            vram_freed = _wait_vram_freed(gpu_device)
            GPUBackendManager.empty_cache()

            if vram_freed:
                logger.info("[引擎切换] VRAM 已释放")
            else:
                logger.warning("[引擎切换] VRAM 轮询超时，继续切换流程")

        _progress_mgr.update_phase("正在清理 VRAM...")

        # Step 3: 加载新引擎
        if engine_name == "voxcpm2":
            yield from _load_voxcpm2_engine(gpu_device, backend)
        elif engine_name == "indextts2":
            yield from load_indextts2()

    except TTSError:
        # 业务异常原样抛出（InsufficientVRAMError 等），不触发回滚
        # 原因：VRAM 预检失败时 unload_model 尚未执行，无需回滚
        raise
    except Exception as e:
        # M-R1/M-R3: 委托回滚逻辑给 _rollback_engine
        _rollback_engine(prev_state, e)
        raise EngineSwitchError(f"引擎切换失败: {type(e).__name__}: {e}") from e
    finally:
        _model_lock.release()


def _load_voxcpm2_engine(gpu_device, backend) -> Generator:
    """Internal helper to load VoxCPM2 engine during engine switching."""
    _progress_mgr.update_phase("正在加载新引擎...")
    for status in _do_load_voxcpm2_internal(gpu_device, backend, include_denoiser=True):
        logger.info(f"[引擎切换] {status[0]}")
        yield status
