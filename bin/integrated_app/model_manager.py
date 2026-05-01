# -*- coding: utf-8 -*-
"""模型管理：加载、卸载、引擎切换、全局状态、LRU缓存、进度追踪"""

import os
import gc
import time
import logging
import threading
from collections import OrderedDict

import torch

from .config import (
    ROOT_DIR, MODEL_PATHS, VOXCPM2_MODEL_PATH, VOXCPM2_ASR_PATH,
    VOXCPM2_DENOISER_PATH, SAVE_DIR, PERSONA_DIR,
)
from .exceptions import (
    TTSError, ModelLoadError, InsufficientVRAMError, EngineSwitchError,
)

logger = logging.getLogger("tts_multimodel")


# --- LRU 缓存 ---
class LRUCache:
    def __init__(self, maxsize: int = 50):
        self._cache = OrderedDict()
        self._maxsize = maxsize

    def get(self, key):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def __contains__(self, key):
        return key in self._cache

    def __delitem__(self, key):
        if key in self._cache:
            del self._cache[key]


# --- 生成追踪器 ---
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


# --- 进度管理器 ---
class ProgressManager:
    def __init__(self, max_history=5):
        self._phase = ""
        self._current_segment = 0
        self._total_segments = 1
        self._start_time = 0
        self._segment_times = []
        self._max_history = max_history
        self._lock = threading.RLock()

    def start(self, total_segments=1, phase="准备中"):
        with self._lock:
            self._phase = phase
            self._current_segment = 0
            self._total_segments = total_segments
            self._start_time = time.time()
            self._segment_times = []

    def update_phase(self, phase):
        with self._lock:
            self._phase = phase

    def advance_segment(self, phase="推理中"):
        with self._lock:
            if self._current_segment > 0:
                elapsed = time.time() - self._start_time
                self._segment_times.append(elapsed / self._current_segment)
                if len(self._segment_times) > self._max_history:
                    self._segment_times.pop(0)
            self._current_segment += 1
            self._phase = phase

    def get_progress_html(self):
        with self._lock:
            if self._total_segments <= 0:
                return ""
            progress = self._current_segment / self._total_segments
            pct = int(progress * 100)
            remaining = self._estimate_remaining()
            phase_display = self._phase
            if self._total_segments > 1:
                segment_info = f"第 {self._current_segment}/{self._total_segments} 段"
            else:
                segment_info = ""
            remaining_text = f"预计剩余 {remaining:.0f} 秒" if remaining > 0 else ""
            return (f'<div class="tts-progress-bar">'
                    f'<div class="tts-progress-fill" style="width:{pct}%"></div>'
                    f'</div>'
                    f'<div class="tts-progress-info">'
                    f'<span class="tts-progress-phase">{phase_display}</span>'
                    f'<span class="tts-progress-segment">{segment_info}</span>'
                    f'<span class="tts-progress-remaining">{remaining_text}</span>'
                    f'</div>')

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


# --- GPU 显存监控 ---
class GPUMemoryMonitor:
    @staticmethod
    def get_vram_info():
        if not torch.cuda.is_available():
            return {"total": 0, "used": 0, "free": 0}
        total = torch.cuda.get_device_properties(0).total_memory
        used = torch.cuda.memory_allocated(0)
        free = torch.cuda.mem_get_info()[0]
        return {"total": total, "used": used, "free": free}

    @staticmethod
    def can_load_model(size="1.7B"):
        info = GPUMemoryMonitor.get_vram_info()
        needed = int(4.5 * 1024**3 if size == "1.7B" else 2.0 * 1024**3)
        return info["free"] >= needed, info["free"]


# --- 全局状态 ---
current_model = None
current_type = None
current_size = None

# VoxCPM2 引擎全局变量
current_engine = "qwen3tts"  # "qwen3tts" 或 "voxcpm2"
voxcpm_model = None
voxcpm_asr = None

_persona_embedding_cache = LRUCache(maxsize=50)
_gen_tracker = GenerationTracker()
_progress_mgr = ProgressManager()
_model_lock = threading.RLock()


def _check_model_ready():
    """检查模型是否就绪（未被锁定）"""
    if not _model_lock.acquire(blocking=False):
        return False
    _model_lock.release()
    return True


def unload_model(keep_engine=False):
    """卸载当前模型，释放显存"""
    global current_model, current_type, current_size, current_engine, voxcpm_model, voxcpm_asr
    _model_lock.acquire()
    if current_engine == "voxcpm2":
        if voxcpm_model is not None:
            del voxcpm_model
            voxcpm_model = None
        if voxcpm_asr is not None:
            del voxcpm_asr
            voxcpm_asr = None
        current_type = None
        current_size = None
    else:
        if current_model is not None:
            logger.info(f"正在释放: {current_type} ({current_size}) 模型...")
            if hasattr(current_model, 'predictor_graph') and current_model.predictor_graph is not None:
                current_model.predictor_graph.graph = None
                current_model.predictor_graph.captured = False
            if hasattr(current_model, 'talker_graph') and current_model.talker_graph is not None:
                current_model.talker_graph.graph = None
                current_model.talker_graph.captured = False
            del current_model
            current_model = None
            current_type = None
            current_size = None
    _persona_embedding_cache._cache.clear()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
        # 尝试释放 CUDNN workspace 和 CUDA Graph
        try:
            torch._C._cuda_clearCublasWorkspaces()
        except AttributeError:
            pass
        torch.cuda.ipc_collect()
        time.sleep(2)
        torch.cuda.empty_cache()
        allocated = torch.cuda.memory_allocated(0)
        reserved = torch.cuda.memory_reserved(0)
        logger.info(f"释放后显存: 已分配 {allocated / 1024**3:.2f}GB, 保留 {reserved / 1024**3:.2f}GB")
    time.sleep(1)
    _model_lock.release()
    if not keep_engine:
        current_engine = None


def load_model(m_type, size="1.7B"):
    """加载指定类型的模型"""
    global current_model, current_type, current_size
    from faster_qwen3_tts import FasterQwen3TTS

    actual_size = "1.7B" if m_type == "声音设计" else size
    _model_lock.acquire()
    if current_type == m_type and current_size == actual_size and current_model is not None:
        _model_lock.release()
        return current_model

    prev_type = current_type
    prev_size = current_size
    prev_model = current_model
    unload_model()

    m_folder = MODEL_PATHS[m_type].format(size=actual_size)
    path = os.path.join(ROOT_DIR, "models", m_folder).replace("\\", "/")
    logger.info(f"正在准备加载: {m_folder}...")

    if torch.cuda.is_available() and not GPUMemoryMonitor.can_load_model(actual_size)[0]:
        current_type = None
        current_size = None
        current_model = None
        free_vram = GPUMemoryMonitor.get_vram_info()["free"]
        _model_lock.release()
        raise InsufficientVRAMError(
            f"显存不足，无法加载 {m_type} ({actual_size})。"
            f"需要约 {'4.5GB' if actual_size == '1.7B' else '2.0GB'}，当前可用 {free_vram / 1024**3:.2f}GB。"
        )

    try:
        dtype = torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16
        current_model = FasterQwen3TTS.from_pretrained(path, device="cuda", dtype=dtype)
        current_type = m_type
        current_size = actual_size
        logger.info("正在捕获 CUDA Graph 预热...")
        current_model._warmup(prefill_len=100)
        logger.info("CUDA Graph 捕获完成，后续生成将大幅加速！")
        _model_lock.release()
        return current_model
    except Exception as e:
        logger.error(f"模型加载失败: {e}")
        current_model = None
        current_type = None
        current_size = None
        _model_lock.release()
        raise ModelLoadError(f"模型加载失败: {e}") from e


def load_voxcpm2():
    """加载 VoxCPM2 引擎（生成器模式，用于 UI 进度反馈）"""
    global current_model, current_engine, voxcpm_model, voxcpm_asr
    import voxcpm
    from funasr import AutoModel

    _model_lock.acquire()
    try:
        # 先卸载当前引擎
        if current_engine == "qwen3tts":
            if current_model is not None:
                del current_model
                current_model = None
            current_type = None
            current_size = None
        elif current_engine == "voxcpm2":
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
                device="cuda:0",
            )
            voxcpm_model.model.to(dtype=torch.bfloat16)
            status_text = "正在加载 ASR 模型..."
            yield status_text, None, None, None
            voxcpm_asr = AutoModel(
                model=VOXCPM2_ASR_PATH,
                disable_pbar=True,
                device="cuda:0",
            )
            current_engine = "voxcpm2"
            status_text = "VoxCPM2 引擎就绪"
            yield status_text, None, None, None
        except Exception as e:
            # 清理失败加载
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


def switch_engine(engine_name, qwen_size="1.7B"):
    """切换引擎（生成器模式，用于 UI 进度反馈）"""
    global current_model, current_engine, voxcpm_model, voxcpm_asr, current_type, current_size

    from faster_qwen3_tts import FasterQwen3TTS
    import voxcpm
    from funasr import AutoModel

    engine_name = engine_name.strip()
    logger.info(f"[引擎切换] 目标: {engine_name}, Qwen 尺寸: {qwen_size}")

    _model_lock.acquire()
    try:
        # 保存当前引擎状态以便失败时恢复
        prev_engine = current_engine
        prev_model = current_model
        prev_type = current_type
        prev_size = current_size
        prev_voxcpm_model = voxcpm_model
        prev_voxcpm_asr = voxcpm_asr

        if engine_name in ("Qwen3TTS 1.7B", "Qwen3TTS 0.6B"):
            # Step 1: VRAM 预检查
            needed_gb = 4.5 if qwen_size == "1.7B" else 2.0
            logger.info(f"[引擎切换] 开始 VRAM 预检查...")
            can_load, free_vram = GPUMemoryMonitor.can_load_model(qwen_size)
            logger.info(f"[引擎切换] 显存检查: 需要 {needed_gb}GB, 可用 {free_vram / 1024**3:.2f}GB")

            if not can_load:
                error_msg = f"显存不足，无法加载 Qwen3TTS {qwen_size}。需要约 {needed_gb}GB，当前可用 {free_vram / 1024**3:.2f}GB。请关闭其他占用显存的程序或选择 0.6B 版本。"
                logger.error(f"[引擎切换] {error_msg}")
                raise InsufficientVRAMError(error_msg)

            # Step 2: 卸载当前模型
            logger.info(f"[引擎切换] 开始卸载当前模型...")
            _progress_mgr.update_phase("正在卸载旧引擎...")
            unload_model(keep_engine=False)

            # Step 3: 清理 VRAM
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                time.sleep(1)
                torch.cuda.empty_cache()
            _progress_mgr.update_phase("正在清理 VRAM...")

            status_text = f"正在加载 Qwen3TTS {qwen_size}..."
            logger.info(f"[引擎切换] {status_text}")
            _progress_mgr.update_phase("正在加载新引擎...")
            yield status_text, None, None, None

            model_type = "语音克隆"
            model_path = MODEL_PATHS[model_type].format(size=qwen_size)
            model_full_path = os.path.join(ROOT_DIR, "models", model_path)

            if not os.path.exists(model_full_path):
                raise FileNotFoundError(f"模型路径不存在: {model_full_path}")

            logger.info(f"[引擎切换] 模型路径: {model_full_path}")

            dtype = torch.bfloat16 if qwen_size == "1.7B" else torch.float16
            current_model = FasterQwen3TTS.from_pretrained(model_full_path, device="cuda", dtype=dtype)
            current_engine = "qwen3tts"
            current_type = model_type
            current_size = qwen_size

            # CUDA Graph 预热
            logger.info(f"[引擎切换] 正在进行 CUDA Graph 预热...")
            _progress_mgr.update_phase("CUDA Graph 预热中...")
            current_model._warmup(prefill_len=100)

            status_text = f"Qwen3TTS {qwen_size} 引擎就绪"
            logger.info(f"[引擎切换] {status_text}")
            yield status_text, None, None, None

        elif engine_name == "VoxCPM2":
            # Step 1: 使用 unload_model 完全卸载当前引擎
            logger.info(f"[引擎切换] 开始卸载当前引擎...")
            _progress_mgr.update_phase("正在卸载旧引擎...")
            unload_model(keep_engine=False)
            # 额外强制释放
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                time.sleep(2)
                torch.cuda.empty_cache()
                _progress_mgr.update_phase("正在清理 VRAM...")
                allocated = torch.cuda.memory_allocated(0)
                reserved = torch.cuda.memory_reserved(0)
                logger.info(f"[引擎切换] 卸载后显存: 已分配 {allocated / 1024**3:.2f}GB, 保留 {reserved / 1024**3:.2f}GB")

            # Step 2: VRAM 预检查
            needed_gb = 6.5
            logger.info(f"[引擎切换] 开始 VRAM 预检查...")
            if torch.cuda.is_available():
                total = torch.cuda.get_device_properties(0).total_memory
                reserved = torch.cuda.memory_reserved(0)
                free = total - reserved
                free_gb = free / 1024**3
            else:
                free_gb = 0
            logger.info(f"[引擎切换] VRAM 检查: 需要 {needed_gb}GB, 可用 {free_gb:.2f}GB")

            if free_gb < needed_gb:
                error_msg = f"显存不足，无法加载 VoxCPM2。需要约 {needed_gb}GB，当前可用 {free_gb:.2f}GB。请关闭其他占用显存的程序或尝试使用 Qwen3TTS 0.6B。"
                logger.error(f"[引擎切换] {error_msg}")
                # 重置为 None，不恢复旧引用（旧引用已被卸载，不可用）
                current_model = None
                current_engine = None
                current_type = None
                current_size = None
                voxcpm_model = None
                voxcpm_asr = None
                raise InsufficientVRAMError(error_msg)

            logger.info(f"[引擎切换] VRAM 检查通过，开始加载 VoxCPM2...")

            # Step 3: 加载 VoxCPM 模型
            status_text = "正在加载 VoxCPM2 模型..."
            logger.info(f"[引擎切换] {status_text}")
            _progress_mgr.update_phase("正在加载新引擎...")
            yield status_text, None, None, None

            voxcpm_model = voxcpm.VoxCPM.from_pretrained(
                VOXCPM2_MODEL_PATH,
                optimize=True,
                local_files_only=True,
                zipenhancer_model_id=VOXCPM2_DENOISER_PATH,
            )
            logger.info(f"[引擎切换] VoxCPM 模型加载成功")

            # Step 4: 加载 ASR 模型
            status_text = "正在加载 ASR 模型..."
            logger.info(f"[引擎切换] {status_text}")
            yield status_text, None, None, None

            voxcpm_asr = AutoModel(
                model=VOXCPM2_ASR_PATH,
                disable_pbar=True,
                device="cuda:0",
            )

            # Step 5: 完成
            current_engine = "voxcpm2"
            status_text = "VoxCPM2 引擎就绪"
            logger.info(f"[引擎切换] {status_text}")
            yield status_text, None, None, None
        else:
            error_msg = f"未知引擎: {engine_name}"
            logger.error(f"[引擎切换] {error_msg}")
            raise EngineSwitchError(error_msg)

    except TTSError:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        error_msg = f"引擎切换失败: {type(e).__name__}: {e}\n\n详细错误:\n{tb}"
        logger.error(f"[引擎切换] {error_msg}")

        current_model = None
        current_engine = None
        current_type = None
        current_size = None
        voxcpm_model = None
        voxcpm_asr = None

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        raise EngineSwitchError(error_msg) from e
    finally:
        _model_lock.release()
