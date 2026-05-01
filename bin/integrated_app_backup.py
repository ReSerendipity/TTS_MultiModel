import os
import sys
import gc
import glob
import time
import threading
import re
import base64
import logging
from collections import OrderedDict
from typing import List, Any, Tuple, Optional
from datetime import datetime

import torch
import numpy as np
import gradio as gr
import soundfile as sf

from faster_qwen3_tts import FasterQwen3TTS
from faster_qwen3_tts.generate import fast_generate
import voxcpm
from funasr import AutoModel

logger = logging.getLogger("tts_multimodel")
logger.setLevel(logging.DEBUG)
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_console_handler)

# --- 【1. 环境与补丁设置】 ---
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['MODELSCOPE_OFFLINE'] = '1'
os.environ['PYTHONHTTPSVERIFY'] = '0'

try:
    from qwen_tts.inference.qwen3_tts_model import VoiceClonePromptItem
    torch.serialization.add_safe_globals([VoiceClonePromptItem])
except ImportError:
    pass

import ssl
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

# --- 【2. 路径配置】 ---
def get_project_root():
    current_path = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(current_path).lower() == 'bin':
        return os.path.dirname(current_path)
    return current_path

ROOT_DIR = get_project_root()
CACHE_DIR = os.path.join(ROOT_DIR, "cache")
PRETRAINED_DIR = os.path.join(ROOT_DIR, "pretrained_models")
SAVE_DIR = os.path.join(ROOT_DIR, "outputs")
PERSONA_DIR = os.path.join(ROOT_DIR, "personas")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(PERSONA_DIR, exist_ok=True)

MODEL_PATHS = {
    "声音设计": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "语音克隆": "Qwen3-TTS-12Hz-{size}-Base",
    "官方精品": "Qwen3-TTS-12Hz-{size}-CustomVoice",
}

VOXCPM2_MODEL_PATH = os.path.join(PRETRAINED_DIR, "VoxCPM2")
VOXCPM2_ASR_PATH = os.path.join(PRETRAINED_DIR, "SenseVoiceSmall")
VOXCPM2_DENOISER_PATH = os.path.join(PRETRAINED_DIR, "speech_zipenhancer")

OFFICIAL_SPEAKERS = {"Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric", "Ryan", "Aiden", "Ono_Anna", "Sohee"}
_OFFICIAL_SPEAKERS_LOWER = {s.lower() for s in OFFICIAL_SPEAKERS}

OFFICIAL_SPEAKER_INFO = {
    "Vivian": ("薇薇安", "甜美少女音，活泼热情，适合年轻女性角色配音。擅长日常对话和情感表达。", "少女音", "年轻活泼，语速轻快"),
    "Serena": ("塞雷娜", "优雅成熟女性声线，知性大方。适合专业播报、教学讲解和商务场景。", "御姐音", "沉稳知性，语速适中"),
    "Uncle_Fu": ("傅叔叔", "中年男性沉稳声线，温和可靠。适合长辈角色、纪录片旁白和故事讲述。", "中年男音", "沉稳厚重，语速较慢"),
    "Dylan": ("迪伦", "年轻男性活力声线，阳光开朗。适合青年角色、广告配音和娱乐内容。", "青年男音", "阳光活力，语速较快"),
    "Eric": ("埃里克", "磁性低沉男声，深沉有魅力。适合悬疑叙事、有声书和电影预告。", "低音炮", "深沉磁性，语速缓慢"),
    "Ryan": ("瑞恩", "清脆少年音，干净纯粹。适合动漫角色、儿童内容和轻快解说。", "少年音", "清脆明亮，语速轻快"),
    "Aiden": ("艾登", "温暖青年男声，亲切自然。适合播客、自媒体和日常交流场景。", "暖男音", "温和亲切，语速适中"),
    "Ono_Anna": ("小野安娜", "日式甜美女声，日系二次元风格。适合动漫角色、游戏配音和轻小说。", "日系甜音", "甜美可爱，语速轻快"),
    "Sohee": ("秀熙", "韩式清甜女声，韩流风格。适合韩剧风格内容、韩语学习辅助。", "韩系甜音", "清甜温柔，语速适中"),
}

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
    if not _model_lock.acquire(blocking=False):
        return False
    _model_lock.release()
    return True

# --- 【3. 核心调度与工具逻辑】 ---
def save_audio(wav, sr, prefix="audio", format="wav"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if format == "mp3":
        try:
            from pydub import AudioSegment
            import io
            buf = io.BytesIO()
            sf.write(buf, wav, sr, format="WAV")
            buf.seek(0)
            audio = AudioSegment.from_wav(buf)
            file_path = os.path.join(SAVE_DIR, f"{prefix}_{timestamp}.mp3")
            audio.export(file_path, format="mp3", bitrate="192k")
            return file_path
        except ImportError:
            pass
    file_path = os.path.join(SAVE_DIR, f"{prefix}_{timestamp}.wav")
    sf.write(file_path, wav, sr)
    return file_path

def cleanup_temp_files():
    """清理临时音频文件"""
    try:
        for f in glob.glob(os.path.join(SAVE_DIR, "temp_*.wav")):
            try:
                os.remove(f)
            except OSError:
                pass
    except Exception:
        pass

# --- 【1.5 统一异常层次结构】 ---
class TTSError(Exception):
    """TTS 基础异常"""
    def __init__(self, message="", error_code="TTS_ERROR"):
        self.error_code = error_code
        super().__init__(message)

class ModelLoadError(TTSError):
    """模型加载失败"""
    def __init__(self, message="模型加载失败"):
        super().__init__(message, "MODEL_LOAD_ERROR")

class InsufficientVRAMError(TTSError):
    """显存不足"""
    def __init__(self, message="显存不足"):
        super().__init__(message, "INSUFFICIENT_VRAM")

class PersonaError(TTSError):
    """音色操作失败"""
    def __init__(self, message="音色操作失败"):
        super().__init__(message, "PERSONA_ERROR")

class GenerationError(TTSError):
    """生成失败"""
    def __init__(self, message="生成失败"):
        super().__init__(message, "GENERATION_ERROR")

class EngineSwitchError(TTSError):
    """引擎切换失败"""
    def __init__(self, message="引擎切换失败"):
        super().__init__(message, "ENGINE_SWITCH_ERROR")

def tts_error_handler(func):
    import functools
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except TTSError as e:
            import gradio as gr
            raise gr.Error(f"[{e.error_code}] {str(e)}")
        except Exception as e:
            import gradio as gr
            raise gr.Error(f"未知错误: {type(e).__name__}: {e}")
    return wrapper

# --- 【2. 路径配置】 ---

def unload_model(keep_engine=False):
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

def load_model(m_type, size="1.7B"):
    global current_model, current_type, current_size
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
        current_type = prev_type
        current_size = prev_size
        current_model = prev_model
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
        current_model = prev_model
        current_type = prev_type
        current_size = prev_size
        _model_lock.release()
        raise ModelLoadError(f"模型加载失败: {e}") from e

def load_voxcpm2():
    global current_model, current_engine, voxcpm_model, voxcpm_asr
    # 先卸载当前引擎（不设置 current_engine=None，保留原引擎信息以便失败时恢复）
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

def switch_engine(engine_name, qwen_size="1.7B"):
    global current_model, current_engine, voxcpm_model, voxcpm_asr, current_type, current_size
    engine_name = engine_name.strip()
    logger.info(f"[引擎切换] 目标: {engine_name}, Qwen 尺寸: {qwen_size}")
    
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
            
            # Step 2: VRAM 预检查（使用 memory_reserved 更准确）
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
                # 尝试恢复之前的引擎状态
                current_model = prev_model
                current_engine = prev_engine
                current_type = prev_type
                current_size = prev_size
                voxcpm_model = prev_voxcpm_model
                voxcpm_asr = prev_voxcpm_asr
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

def preprocess_and_save_temp(audio_input, filename="temp_ref.wav"):
    if isinstance(audio_input, str): wav, sr = sf.read(audio_input)
    else: sr, wav = audio_input
    wav_p = wav.astype(np.float32)
    if wav.dtype == np.int16: wav_p = wav_p / 32768.0
    max_val = np.max(np.abs(wav_p))
    if max_val > 1.0: wav_p = wav_p / max_val
    if wav_p.ndim > 1: wav_p = np.mean(wav_p, axis=-1)
    tmp_path = os.path.join(SAVE_DIR, filename)
    sf.write(tmp_path, wav_p, sr)
    return tmp_path, sr, wav_p

# --- 【4. 固化逻辑】 ---
# 音色名称验证正则：仅允许字母、数字、下划线、连字符、中文字符
_PERSONA_NAME_RE = re.compile(r'^[a-zA-Z0-9_\-\u4e00-\u9fff]{1,50}$')

def _validate_persona_name(name):
    """验证音色名称合法性，防止路径遍历和注入"""
    if not name:
        return False, "名称不能为空"
    if not _PERSONA_NAME_RE.match(name):
        return False, "名称格式不合法（仅支持字母、数字、下划线、连字符、中文，1-50字符）"
    return True, ""

def fn_save_persona(name, audio_input, ref_text, overwrite=False):
    if not name or audio_input is None:
        return "❌ 失败：需输入名称及音频", gr.update(visible=False)

    # 输入验证
    valid, err_msg = _validate_persona_name(name)
    if not valid:
        return f"❌ {err_msg}", gr.update(visible=False)

    try:
        # 使用 realpath 防止路径遍历
        wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
        txt_path = os.path.join(PERSONA_DIR, f"{name}.txt")
        wav_real = os.path.realpath(wav_path)
        if not wav_real.startswith(os.path.realpath(PERSONA_DIR)):
            return "❌ 非法路径", gr.update(visible=False)
        # 名称冲突检测
        existing = os.path.exists(wav_path) or os.path.exists(os.path.join(PERSONA_DIR, f"{name}.pt"))
        if existing and not overwrite:
            return f"⚠️ 音色 [{name}] 已存在，再次点击保存将覆盖原有音色", gr.update(visible=True)
        tmp_p, sr_p, wav_p = preprocess_and_save_temp(audio_input, f"{name}.wav")
        os.replace(tmp_p, wav_path)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(ref_text if ref_text else "")
        model = load_model("语音克隆", "1.7B")
        # 修正：FasterQwen3TTS 内部使用 .model 访问原始方法
        items = model.model.create_voice_clone_prompt(ref_audio=(wav_p, sr_p), ref_text=ref_text if ref_text else "", x_vector_only_mode=False)
        payload = {"items": [{"ref_code": it.ref_code, "ref_spk_embedding": it.ref_spk_embedding, "x_vector_only_mode": it.x_vector_only_mode, "icl_mode": it.icl_mode, "ref_text": it.ref_text} for it in items]}
        torch.save(payload, os.path.join(PERSONA_DIR, f"{name}.pt"))
        return f"✅ 音色 [{name}] 已成功固化！", gr.update(visible=False)
    except Exception as e:
        logger.error(f"音色固化失败: {e}")
        return f"❌ 固化失败: {str(e)}", gr.update(visible=False)

def split_text_for_tts(text, max_chars=200):
    """将长文本分割成适合 TTS 处理的短段落"""
    if len(text) <= max_chars:
        return [text]
    
    segments = []
    current = []
    current_len = 0
    
    for char in text:
        current.append(char)
        current_len += 1
        
        if current_len >= max_chars:
            joined = "".join(current)
            split_idx = max(joined.rfind("。"), joined.rfind("！"), joined.rfind("？"), joined.rfind("；"), joined.rfind(","), joined.rfind("，"), 0)
            if split_idx > max_chars // 2:
                segments.append(joined[:split_idx + 1])
                current = list(joined[split_idx + 1:])
                current_len = len(current)
            else:
                segments.append(joined)
                current = []
                current_len = 0
    
    if current:
        segments.append("".join(current))
    
    return segments if segments else [text]

def merge_audio_segments(audio_segments, sr):
    """合并音频段，段间添加静音"""
    if not audio_segments:
        return None, sr
    
    if len(audio_segments) == 1:
        return audio_segments[0], sr
    
    silence_samples = int(sr * 0.3)
    result = [audio_segments[0]]
    for seg in audio_segments[1:]:
        result.append(np.zeros(silence_samples))
        result.append(seg)
    
    return np.concatenate(result), sr

def get_persona_list(include_official=False, search_keyword=""):
    """获取音色列表，可选择包含官方音色，支持搜索过滤"""
    wav_files = [f[:-4] for f in os.listdir(PERSONA_DIR) if f.endswith(".wav")]
    custom = sorted(wav_files) if wav_files else []

    if search_keyword:
        kw = search_keyword.lower()
        custom = [c for c in custom if kw in c.lower()]

    if include_official:
        official_list = ["[官方] " + OFFICIAL_SPEAKER_INFO.get(s, (s, "", "", ""))[0] + " (" + s + ")" for s in OFFICIAL_SPEAKERS]
        if search_keyword:
            kw = search_keyword.lower()
            official_list = [o for o in official_list if kw in o.lower()]
        return official_list + (custom if custom else [])
    return custom if custom else ["(暂无音色)"]

def get_total_persona_count():
    files = [f for f in os.listdir(PERSONA_DIR) if f.endswith(".wav")]
    return len(files)

def get_persona_detail_table(search_keyword=""):
    files = [f.replace(".wav", "") for f in os.listdir(PERSONA_DIR) if f.endswith(".wav")]
    files = sorted(files)
    
    if search_keyword:
        kw = search_keyword.lower()
        files = [f for f in files if kw in f.lower()]
    
    table = []
    for name in files:
        pt_path = os.path.join(PERSONA_DIR, f"{name}.pt")
        wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
        txt_path = os.path.join(PERSONA_DIR, f"{name}.txt")
        
        has_pt = "✅ 已固化" if os.path.exists(pt_path) else "❌ 未固化"
        has_wav = "✅" if os.path.exists(wav_path) else "❌"
        
        ref_text = ""
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                ref_text = f.read()
            if len(ref_text) > 50:
                ref_text = ref_text[:50] + "..."
        
        stat = os.stat(wav_path) if os.path.exists(wav_path) else None
        wav_size = f"{stat.st_size / 1024:.1f} KB" if stat else "-"
        wav_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M") if stat else "-"
        
        table.append([
            name,
            has_pt,
            wav_size,
            wav_time,
            ref_text if ref_text else "-"
        ])
    return table if table else [["暂无音色", "-", "-", "-", "-"]]

def get_persona_desc(name):
    """获取音色描述信息"""
    if name in OFFICIAL_SPEAKERS:
        info = OFFICIAL_SPEAKER_INFO.get(name, ("", "", "", ""))
        return f"🎙️ **{info[0]} ({name})**\n\n**音色类型**：{info[2]}\n**声音特点**：{info[3]}\n\n**详细说明**：{info[1]}"
    wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
    if os.path.exists(wav_path):
        return f"🎵 **{name}**（自定义音色）\n\n自定义音色，适用于个性化语音合成。"
    return ""

def load_persona_embedding(name):
    """加载已保存音色的预计算嵌入数据，支持官方音色"""
    cached = _persona_embedding_cache.get(name)
    if cached is not None:
        return cached

    if name in OFFICIAL_SPEAKERS:
        result = (None, "__official__", name)
        _persona_embedding_cache.put(name, result)
        return result

    pt_path = os.path.join(PERSONA_DIR, f"{name}.pt")
    wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
    txt_path = os.path.join(PERSONA_DIR, f"{name}.txt")

    wav_exists = os.path.exists(wav_path)
    pt_exists = os.path.exists(pt_path)
    txt_exists = os.path.exists(txt_path)

    ref_text = ""
    if txt_exists:
        with open(txt_path, "r", encoding="utf-8") as f:
            ref_text = f.read()

    if pt_exists and wav_exists:
        vcp_data = torch.load(pt_path, map_location="cpu", weights_only=False)
        result = (vcp_data, wav_path, ref_text)
    elif wav_exists:
        result = (None, wav_path, ref_text)
    else:
        return None

    _persona_embedding_cache.put(name, result)
    return result

@tts_error_handler
def fn_voice_clone_with_persona(text, lang, persona_name, size, output_format="wav", use_upload=False, ref_audio=None, ref_text=""):
    """使用已保存音色进行语音克隆，支持跨模式调用（含官方音色），支持长文本自动分割"""
    _gen_tracker.start_generation()
    segments = split_text_for_tts(text)
    _progress_mgr.start(total_segments=len(segments), phase="加载模型中...")
    start_time = time.time()
    try:
        return _fn_voice_clone_with_persona_impl(text, lang, persona_name, size, output_format, use_upload, ref_audio, ref_text, start_time)
    finally:
        elapsed = time.time() - start_time
        _gen_tracker.end_generation(elapsed)
        _progress_mgr.reset()
        cleanup_temp_files()
        logger.info(f"生成耗时 {elapsed:.1f} 秒")

def _fn_voice_clone_with_persona_impl(text, lang, persona_name, size, output_format="wav", use_upload=False, ref_audio=None, ref_text="", start_time=0):
    if not persona_name or persona_name == "(暂无音色)":
        if use_upload and ref_audio is not None:
            model = load_model("语音克隆", size)
            tmp_path, _, _ = preprocess_and_save_temp(ref_audio)
            audio_list, sr = model.generate_voice_clone(text=text, language=lang, ref_audio=tmp_path, ref_text=ref_text)
            save_audio(audio_list[0], sr, f"clone_{size}")
            return (sr, audio_list[0]), f"完成！({size}核心，上传音频)"
        raise PersonaError("请先选择音色或上传参考音频")
    
    real_name = persona_name
    if persona_name.startswith("[官方]"):
        match = re.search(r'\((\w+)\)$', persona_name)
        real_name = match.group(1) if match else persona_name.replace("[官方] ", "").split(" (")[0]
    
    persona_data = load_persona_embedding(real_name)
    if persona_data is None:
        raise PersonaError(f"音色 [{real_name}] 文件不存在")
    
    vcp_data, wav_path, stored_ref_text = persona_data
    
    if wav_path == "__official__":
        model = load_model("官方精品", size)
        speaker_id = stored_ref_text.lower()
        segments = split_text_for_tts(text)
        audio_segments = []
        total = len(segments)
        for i, seg in enumerate(segments):
            elapsed = time.time() - start_time
            if i > 0:
                avg = elapsed / i
                remaining = avg * (total - i)
                logger.info(f"官方音色生成: 第 {i+1}/{total} 段，预计剩余 {remaining:.1f}s")
            _progress_mgr.advance_segment(f"第 {i+1}/{total} 段推理中...")
            al, sr = model.generate_custom_voice(text=seg, language=lang, speaker=speaker_id, instruct=None)
            audio_segments.append(al[0])
        merged, sr = merge_audio_segments(audio_segments, sr)
        if merged is None:
            raise GenerationError("官方音色生成失败")
        save_audio(merged, sr, f"official_{speaker_id}")
        zh_name = OFFICIAL_SPEAKER_INFO.get(stored_ref_text, (speaker_id, "", "", ""))[0]
        if len(segments) > 1:
            return (sr, merged), f"✅ 完成！官方音色: {zh_name} ({stored_ref_text})，分段: {len(segments)}"
        return (sr, merged), f"✅ 完成！官方音色: {zh_name} ({stored_ref_text})"
    
    model = load_model("语音克隆", size)
    segments = split_text_for_tts(text)
    audio_segments = []
    total = len(segments)

    m = model.model.model
    talker = m.talker
    config = m.config.talker_config
    speech_tokenizer = m.speech_tokenizer

    voice_clone_prompt = None
    ref_codes_tensor = None
    if vcp_data is not None:
        try:
            items = vcp_data["items"]
            voice_clone_prompt = {
                "ref_code": [torch.tensor(it["ref_code"]) if it.get("ref_code") is not None else None for it in items],
                "ref_spk_embedding": [torch.tensor(it["ref_spk_embedding"]) if it.get("ref_spk_embedding") is not None else None for it in items],
                "x_vector_only_mode": [it.get("x_vector_only_mode", False) for it in items],
                "icl_mode": [it.get("icl_mode", False) for it in items],
            }
            if voice_clone_prompt["ref_code"] and voice_clone_prompt["ref_code"][0] is not None:
                ref_codes_tensor = voice_clone_prompt["ref_code"][0]
        except Exception as e:
            logger.warning(f"构建 voice_clone_prompt 失败: {e}")
            voice_clone_prompt = None

    for idx, seg_text in enumerate(segments):
        seg_text = seg_text.strip()
        if not seg_text: continue

        _progress_mgr.advance_segment(f"第 {idx+1}/{total} 段推理中...")

        elapsed = time.time() - start_time
        if idx > 0:
            avg = elapsed / idx
            remaining = avg * (total - idx)
            logger.info(f"第 {idx+1}/{total} 段，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"第 1/{total} 段...")

        if voice_clone_prompt is not None:
            try:
                input_texts = [model.model._build_assistant_text(seg_text)]
                input_ids = model.model._tokenize_texts(input_texts)
                ref_ids = [None] * len(input_ids)

                tie, tam, tth, tpe = model.model._build_talker_inputs_local(
                    m=m,
                    input_ids=input_ids,
                    ref_ids=ref_ids,
                    voice_clone_prompt=voice_clone_prompt,
                    languages=[lang] if lang is not None else ["Auto"],
                    speakers=None,
                    non_streaming_mode=True,
                    instruct_ids=[None],
                )

                if not model.model._warmed_up:
                    model.model._warmup(tie.shape[1])

                talker.rope_deltas = None

                codec_ids, timing = fast_generate(
                    talker=talker,
                    talker_input_embeds=tie,
                    attention_mask=tam,
                    trailing_text_hiddens=tth,
                    tts_pad_embed=tpe,
                    config=config,
                    predictor_graph=model.model.predictor_graph,
                    talker_graph=model.model.talker_graph,
                    max_new_tokens=2048,
                    min_new_tokens=2,
                    temperature=0.9,
                    top_k=50,
                    top_p=1.0,
                    do_sample=True,
                    repetition_penalty=1.05,
                )

                if codec_ids is None:
                    continue

                if ref_codes_tensor is not None:
                    codes_for_decode = torch.cat([ref_codes_tensor.to(codec_ids.device), codec_ids], dim=0)
                else:
                    codes_for_decode = codec_ids

                al, sr = speech_tokenizer.decode({"audio_codes": codes_for_decode.unsqueeze(0)})

                ref_len = ref_codes_tensor.shape[0] if ref_codes_tensor is not None else 0
                total_len = codes_for_decode.shape[0]
                audio_arrays = []
                for a in al:
                    if hasattr(a, 'cpu'):
                        a = a.flatten().cpu().numpy()
                    else:
                        a = a.flatten() if hasattr(a, 'flatten') else a
                    if ref_len > 0:
                        cut = int(ref_len / max(total_len, 1) * len(a))
                        a = a[cut:]
                    audio_arrays.append(a)

                audio_segments.append(audio_arrays[0])
                continue
            except Exception as e:
                logger.warning(f"快速路径推理失败，回退标准模式: {e}")

        al, sr = model.generate_voice_clone(
            text=seg_text, language=lang, ref_audio=wav_path, ref_text=stored_ref_text
        )
        audio_segments.append(al[0])
    
    if not audio_segments:
        raise GenerationError("语音克隆生成失败：无有效音频段")
    
    merged, sr = merge_audio_segments(audio_segments, sr)
    if merged is None:
        raise GenerationError("语音克隆生成失败：音频合并失败")
    
    save_audio(merged, sr, f"clone_persona_{persona_name}")
    if len(segments) > 1:
        return (sr, merged), f"✅ 完成！({size}核心，音色: {persona_name}，分段: {len(segments)})"
    return (sr, merged), f"✅ 完成！({size}核心，音色: {persona_name})"

# --- 【5. 业务生成逻辑】 ---
@tts_error_handler
def fn_voice_design(text, lang, instruct, output_format="wav"):
    if not _check_model_ready():
        raise GenerationError("模型正在加载或切换中，请稍后再试")
    _gen_tracker.start_generation()
    _progress_mgr.start(total_segments=1, phase="加载模型中...")
    start_time = time.time()
    try:
        _progress_mgr.update_phase("加载声音设计模型...")
        model = load_model("声音设计")
        _progress_mgr.update_phase("CUDA Graph 预热中...")
        _progress_mgr.update_phase("推理生成中...")
        audio_list, sr = model.generate_voice_design(text=text, language=lang, instruct=instruct)
        _progress_mgr.update_phase("音频后处理...")
        save_audio(audio_list[0], sr, "design", format=output_format)
        _progress_mgr.advance_segment("完成")
        return (sr, audio_list[0]), "生成成功！"
    except TTSError:
        raise
    except Exception as e:
        _progress_mgr.update_phase(f"出错: {e}")
        raise GenerationError(f"声音设计生成失败: {e}") from e
    finally:
        elapsed = time.time() - start_time
        _gen_tracker.end_generation(elapsed)
        _progress_mgr.reset()
        cleanup_temp_files()

def fn_voice_clone(text, lang, ref_audio, ref_text, size):
    if not _check_model_ready():
        raise GenerationError("模型正在加载或切换中，请稍后再试")
    model = load_model("语音克隆", size)
    if ref_audio is None: raise GenerationError("需上传参考音频")
    tmp_path, _, _ = preprocess_and_save_temp(ref_audio)
    audio_list, sr = model.generate_voice_clone(text=text, language=lang, ref_audio=tmp_path, ref_text=ref_text)
    save_audio(audio_list[0], sr, f"clone_{size}")
    return (sr, audio_list[0]), f"完成！({size}核心)"

@tts_error_handler
def fn_custom_voice(text, lang, speaker, instruct, size):
    if not _check_model_ready():
        raise GenerationError("模型正在加载或切换中，请稍后再试")
    try:
        model = load_model("官方精品", size)
        if '[' in text and ']' in text:
            lines = text.strip().split('\n')
            combined_wav, sr_final = [], 24000
            for line in lines:
                match = re.match(r"\[([^\]]+)\]\s*(?:\[([^\]]+)\])?\s*(.*)", line)
                if match:
                    spk, ins, content = match.groups()
                    if not content.strip(): continue
                    segments = split_text_for_tts(content.strip())
                    for seg in segments:
                        wavs, sr = model.generate_custom_voice(text=seg.strip(), language=lang, speaker=spk.strip().lower(), instruct=ins.strip() if ins else None)
                        combined_wav.append(wavs[0])
                    combined_wav.append(np.zeros(int(sr * 0.4))); sr_final = sr
            if combined_wav:
                res_wav = np.concatenate(combined_wav)
                save_audio(res_wav, sr_final, "custom_dialogue")
                return (sr_final, res_wav), "多人对话生成成功！"
        audio_list, sr = model.generate_custom_voice(text=text, language=lang, speaker=speaker.lower(), instruct=instruct)
        save_audio(audio_list[0], sr, f"custom_{speaker}")
        return (sr, audio_list[0]), "生成成功！"
    finally:
        cleanup_temp_files()

def fn_custom_voice_v2(text, lang, speaker, instruct, size, persona_name="(暂无音色)"):
    """官方精品模式增强版：支持官方音色和已保存音色"""
    if persona_name and persona_name != "(暂无音色)":
        return fn_voice_clone_with_persona(text, lang, persona_name, size)
    return fn_custom_voice(text, lang, speaker, instruct, size)

@tts_error_handler
def fn_script_studio(script_text, lang, size):
    if not _check_model_ready():
        raise GenerationError("模型正在加载或切换中，请稍后再试")
    _gen_tracker.start_generation()
    start_time = time.time()
    valid_lines = [l for l in script_text.strip().split('\n') if ']' in l]
    _progress_mgr.start(total_segments=len(valid_lines), phase="剧本合成中...")
    try:
        return _fn_script_studio_impl(script_text, lang, size, start_time)
    finally:
        elapsed = time.time() - start_time
        _gen_tracker.end_generation(elapsed)
        _progress_mgr.reset()
        cleanup_temp_files()
        logger.info(f"剧本合成耗时 {elapsed:.1f} 秒")

def _fn_script_studio_impl(script_text, lang, size, start_time):
    lines = script_text.strip().split('\n')
    valid_lines = [l for l in lines if ']' in l]
    total_roles = len(valid_lines)
    combined_wav, sr_final = [], 24000
    persona_cache = {}
    model_clone = None
    model_custom = None
    role_idx = 0
    
    for line in lines:
        if ']' not in line: continue
        role_idx += 1
        _progress_mgr.advance_segment(f"角色 [{line.split(']')[0].replace('[', '').strip()}] 合成中...")
        elapsed = time.time() - start_time
        if role_idx > 1:
            avg = elapsed / (role_idx - 1)
            remaining = avg * (total_roles - role_idx + 1)
            logger.info(f"剧本进度: 第 {role_idx}/{total_roles} 角色，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"剧本进度: 第 {role_idx}/{total_roles} 角色...")
        try:
            role_part, content = line.split(']', 1)
            role_name = role_part.replace('[', '').strip()
            if not content.strip(): continue
            
            is_official = role_name.lower() in _OFFICIAL_SPEAKERS_LOWER
            real_name = role_name
            
            if is_official:
                if model_custom is None:
                    model_custom = load_model("官方精品", size)
                
                if role_name not in persona_cache:
                    persona_cache[role_name] = ("__official__", role_name.lower())
                
                speaker_id = persona_cache[role_name][1]
                audio_list, sr = model_custom.generate_custom_voice(text=content.strip(), language=lang, speaker=speaker_id, instruct=None)
                combined_wav.append(audio_list[0])
                combined_wav.append(np.zeros(int(sr * 0.4)))
                sr_final = sr
                continue
            
            if model_clone is None:
                model_clone = load_model("语音克隆", size)
            
            ref_wav = os.path.join(PERSONA_DIR, f"{role_name}.wav")
            if not os.path.exists(ref_wav): continue
            
            if role_name not in persona_cache:
                persona_data = load_persona_embedding(role_name)
                persona_cache[role_name] = persona_data
            else:
                persona_data = persona_cache[role_name]
            
            if persona_data is None: continue
            
            vcp_data, wav_path, ref_text = persona_data
            
            if vcp_data is not None:
                try:
                    if role_name not in persona_cache:
                        items = vcp_data["items"]
                        voice_clone_prompt = {
                            "ref_code": [torch.tensor(it["ref_code"]) if it.get("ref_code") is not None else None for it in items],
                            "ref_spk_embedding": [torch.tensor(it["ref_spk_embedding"]) if it.get("ref_spk_embedding") is not None else None for it in items],
                            "x_vector_only_mode": [it.get("x_vector_only_mode", False) for it in items],
                            "icl_mode": [it.get("icl_mode", False) for it in items],
                        }
                        ref_codes_tensor = None
                        if voice_clone_prompt["ref_code"] and voice_clone_prompt["ref_code"][0] is not None:
                            ref_codes_tensor = voice_clone_prompt["ref_code"][0]
                        m = model_clone.model.model
                        talker = m.talker
                        config = m.config.talker_config
                        speech_tokenizer = m.speech_tokenizer
                        persona_cache[role_name] = (persona_data, voice_clone_prompt, ref_codes_tensor, m, talker, config, speech_tokenizer)
                    else:
                        _, voice_clone_prompt, ref_codes_tensor, m, talker, config, speech_tokenizer = persona_cache[role_name]

                    input_texts = [model_clone.model._build_assistant_text(content.strip())]
                    input_ids = model_clone.model._tokenize_texts(input_texts)
                    ref_ids = [None] * len(input_ids)

                    tie, tam, tth, tpe = model_clone.model._build_talker_inputs_local(
                        m=m, input_ids=input_ids, ref_ids=ref_ids,
                        voice_clone_prompt=voice_clone_prompt,
                        languages=[lang] if lang is not None else ["Auto"],
                        speakers=None, non_streaming_mode=True, instruct_ids=[None],
                    )

                    if not model_clone.model._warmed_up:
                        model_clone.model._warmup(tie.shape[1])

                    talker.rope_deltas = None

                    codec_ids, timing = fast_generate(
                        talker=talker, talker_input_embeds=tie, attention_mask=tam,
                        trailing_text_hiddens=tth, tts_pad_embed=tpe, config=config,
                        predictor_graph=model_clone.model.predictor_graph, talker_graph=model_clone.model.talker_graph,
                        max_new_tokens=2048, min_new_tokens=2, temperature=0.9, top_k=50,
                        top_p=1.0, do_sample=True, repetition_penalty=1.05,
                    )

                    if codec_ids is None:
                        continue

                    if ref_codes_tensor is not None:
                        codes_for_decode = torch.cat([ref_codes_tensor.to(codec_ids.device), codec_ids], dim=0)
                    else:
                        codes_for_decode = codec_ids

                    audio_list, sr = speech_tokenizer.decode({"audio_codes": codes_for_decode.unsqueeze(0)})

                    ref_len = ref_codes_tensor.shape[0] if ref_codes_tensor is not None else 0
                    total_len = codes_for_decode.shape[0]
                    audio_arrays = []
                    for a in audio_list:
                        if hasattr(a, 'cpu'): a = a.flatten().cpu().numpy()
                        else: a = a.flatten() if hasattr(a, 'flatten') else a
                        if ref_len > 0:
                            cut = int(ref_len / max(total_len, 1) * len(a))
                            a = a[cut:]
                        audio_arrays.append(a)

                    combined_wav.append(audio_arrays[0])
                    combined_wav.append(np.zeros(int(sr * 0.4)))
                    sr_final = sr
                    continue
                except Exception as e:
                    logger.warning(f"剧本快速推理失败 [{role_name}]: {e}")
                    pass
            
            audio_list, sr = model_clone.generate_voice_clone(
                text=content.strip(), language=lang, ref_audio=wav_path, ref_text=ref_text
            )
            combined_wav.append(audio_list[0])
            combined_wav.append(np.zeros(int(sr * 0.4)))
            sr_final = sr
        except Exception as e: logger.error(f"剧本出错: {e}")
    
    if not combined_wav: raise GenerationError("剧本合成失败：无匹配角色或生成失败")
    res_wav = np.concatenate(combined_wav)
    save_audio(res_wav, sr_final, "script")
    return (sr_final, res_wav), f"✅ 合成完成！规格: {size}"

def add_tag(text, tag, is_speaker=True):
    if not tag or tag == "(暂无音色)": return text
    prefix = "\n" if text.strip() and is_speaker else ""
    result = f"{text.rstrip()}{prefix}[{tag}] "
    # 通过 JS 在光标位置插入（Gradio 回调中无法直接操作光标，此处优化末尾追加逻辑）
    return result

# 角色颜色映射
_ROLE_COLOR_MAP = {
    "御姐": ("pink", "#EC4899"),
    "旁白": ("gray", "#6B7280"),
    "萝莉": ("pink", "#F472B6"),
    "萝莉音": ("pink", "#F472B6"),
    "御姐音": ("pink", "#EC4899"),
    "少年": ("blue", "#3B82F6"),
    "少年音": ("blue", "#3B82F6"),
    "大叔": ("purple", "#8B5CF6"),
    "正太": ("green", "#22C55E"),
    "女王": ("red", "#EF4444"),
    "暖男": ("orange", "#FB923C"),
    "暖男音": ("orange", "#FB923C"),
    "低音炮": ("purple", "#8B5CF6"),
    "少女音": ("pink", "#F472B6"),
    "青年男音": ("blue", "#3B82F6"),
    "中年男音": ("purple", "#8B5CF6"),
    "日系甜音": ("pink", "#F9A8D4"),
    "韩系甜音": ("pink", "#F9A8D4"),
}

def get_role_color(role_name):
    """获取角色对应的颜色标识"""
    clean_name = role_name.strip("[]）")
    return _ROLE_COLOR_MAP.get(clean_name, ("blue", "#3B82F6"))

def generate_speaker_card_grid(selected_speaker_key="Vivian"):
    """生成官方精品音色卡片网格HTML"""
    cards = []
    for key in _OFFICIAL_SPEAKERS_ORDERED:
        info = OFFICIAL_SPEAKER_INFO[key]
        display_name = info[0]
        style_tag = info[2]
        is_selected = "selected" if key == selected_speaker_key else ""
        cards.append(f'''<div class="speaker-card {is_selected}" data-speaker="{key}" onclick="selectSpeakerCard('{key}')">
    <h4 class="speaker-card-name">{display_name}</h4>
    <div class="speaker-card-tags">
        <span class="speaker-card-tag">{style_tag}</span>
        <span class="speaker-card-tag">{key}</span>
    </div>
    <div class="speaker-card-actions">
        <span class="speaker-card-btn" onclick="event.stopPropagation(); previewSpeaker('{key}')">🔊 试听</span>
        <span class="speaker-card-btn btn-use" onclick="event.stopPropagation(); useSpeaker('{key}')">使用</span>
    </div>
</div>''')
    return '<div class="speaker-card-grid">' + '\n'.join(cards) + '</div>'

_AUDIO_EXTS = {'.wav', '.mp3', '.ogg', '.flac'}

def get_generation_history(search_keyword=""):
    kw_lower = search_keyword.lower() if search_keyword else ""
    history = []
    for f in glob.glob(os.path.join(SAVE_DIR, "*.*")):
        if os.path.isdir(f): continue
        ext = os.path.splitext(f)[1].lower()
        if ext not in _AUDIO_EXTS: continue
        basename = os.path.basename(f)
        if kw_lower and kw_lower not in basename.lower():
            continue
        stat = os.stat(f)
        history.append([
            basename,
            datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            f"{stat.st_size / 1024 / 1024:.1f} MB"
        ])
    history.sort(key=lambda x: x[1], reverse=True)
    return history if history else [["暂无记录", "-", "-"]]

def get_total_history_count():
    count = 0
    for f in glob.glob(os.path.join(SAVE_DIR, "*.*")):
        if os.path.isdir(f): continue
        ext = os.path.splitext(f)[1].lower()
        if ext in _AUDIO_EXTS:
            count += 1
    return count

import time as _time_module
def get_generation_history_enhanced(search_keyword="", time_filter="all"):
    """增强的历史记录获取，支持时间筛选"""
    kw_lower = search_keyword.lower() if search_keyword else ""
    now = _time_module.time()
    history = []
    for f in glob.glob(os.path.join(SAVE_DIR, "*.*")):
        if os.path.isdir(f): continue
        ext = os.path.splitext(f)[1].lower()
        if ext not in _AUDIO_EXTS: continue
        basename = os.path.basename(f)
        if kw_lower and kw_lower not in basename.lower():
            continue
        stat = os.stat(f)
        mtime = stat.st_mtime
        # 时间筛选
        if time_filter == "today":
            if now - mtime > 86400: continue
        elif time_filter == "week":
            if now - mtime > 604800: continue
        elif time_filter == "month":
            if now - mtime > 2592000: continue
        # 估算时长 (基于文件大小粗略估算)
        duration = f"{stat.st_size / 1024 / 150:.1f}s" if stat.st_size > 1024 else "<1s"
        history.append({
            "basename": basename,
            "time": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
            "size": f"{stat.st_size / 1024 / 1024:.1f} MB",
            "duration": duration,
            "path": f,
            "mtime": mtime,
        })
    history.sort(key=lambda x: x["mtime"], reverse=True)
    return history

def get_history_table_data(search_keyword="", time_filter="all"):
    """获取历史记录表格数据"""
    records = get_generation_history_enhanced(search_keyword, time_filter)
    if not records:
        return [["暂无记录", "-", "-", "-"]]
    return [[r["basename"], r["time"], r["duration"], r["size"]] for r in records]

MODEL_TYPE_ALIASES = {
    "voice_design": "声音设计",
    "voice_clone": "语音克隆",
    "custom_voice": "官方精品",
    "design": "声音设计",
    "clone": "语音克隆",
    "official": "官方精品",
}

def api_load_model(m_type="声音设计", size="1.7B"):
    try:
        resolved = MODEL_TYPE_ALIASES.get(m_type, m_type)
        m = load_model(resolved, size)
        if m is not None:
            return {"status": "ok", "message": f"Model loaded: {resolved} ({size})"}
        else:
            return {"status": "error", "message": "Model load returned None"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def api_unload_model():
    try:
        unload_model()
        return {"status": "ok", "message": "Model unloaded, VRAM released"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def api_model_status():
    return {
        "loaded": current_model is not None,
        "type": current_type,
        "size": current_size,
    }

# --- 【VoxCPM2 引擎生成函数】 ---
def _save_wav_compatible(wav_data, out_path, sample_rate=48000):
    """将音频数据保存为浏览器兼容的 WAV 格式（int16 PCM）"""
    import numpy as np
    # 确保数据在 [-1, 1] 范围内
    if wav_data.max() > 1.0 or wav_data.min() < -1.0:
        wav_data = wav_data / max(abs(wav_data.max()), abs(wav_data.min()))
    # 转换为 int16
    wav_int16 = (wav_data * 32767).astype(np.int16)
    sf.write(out_path, wav_int16, sample_rate, subtype='PCM_16')
    return out_path

def fn_voxcpm_design(text, instruction):
    global voxcpm_model
    if voxcpm_model is None:
        raise gr.Error("请先切换并加载 VoxCPM2 引擎")
    import time as _time
    import logging
    logger = logging.getLogger("tts_multimodel")
    try:
        wav = voxcpm_model.generate(
            text=text,
            normalize=True,
            cfg_value=2.0,
            inference_timesteps=10,
            denoise=True,
            retry_badcase=False,
        )
        logger.info(f"[VoxCPM生成] wav 类型: {type(wav)}, 形状: {wav.shape if hasattr(wav, 'shape') else 'N/A'}, dtype: {wav.dtype if hasattr(wav, 'dtype') else 'N/A'}")
        # 保存到 output 文件夹
        timestamp = int(_time.time())
        out_path = os.path.join(SAVE_DIR, f"voxcpm_design_{timestamp}.wav")
        _save_wav_compatible(wav, out_path, 48000)
        logger.info(f"[VoxCPM生成] 音频已保存: {out_path}")
        return (48000, wav), "生成成功！"
    except Exception as e:
        import traceback
        error_msg = f"VoxCPM 生成失败: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"[VoxCPM生成] {error_msg}")
        raise gr.Error(error_msg)


def fn_voxcpm_clone(text, instruction, ref_audio_path):
    global voxcpm_model
    if voxcpm_model is None:
        raise gr.Error("请先切换并加载 VoxCPM2 引擎")
    import time as _time
    import logging
    logger = logging.getLogger("tts_multimodel")
    try:
        wav = voxcpm_model.generate(
            text=text,
            reference_wav_path=ref_audio_path if ref_audio_path else None,
            normalize=True,
            cfg_value=2.0,
            inference_timesteps=10,
            denoise=True,
            retry_badcase=False,
        )
        logger.info(f"[VoxCPM生成] wav 类型: {type(wav)}, 形状: {wav.shape if hasattr(wav, 'shape') else 'N/A'}, dtype: {wav.dtype if hasattr(wav, 'dtype') else 'N/A'}")
        timestamp = int(_time.time())
        out_path = os.path.join(SAVE_DIR, f"voxcpm_clone_{timestamp}.wav")
        _save_wav_compatible(wav, out_path, 48000)
        logger.info(f"[VoxCPM生成] 音频已保存: {out_path}")
        return (48000, wav), "生成成功！"
    except Exception as e:
        import traceback
        error_msg = f"VoxCPM 生成失败: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"[VoxCPM生成] {error_msg}")
        raise gr.Error(error_msg)


def fn_voxcpm_ultimate_clone(text, instruction, ref_audio_path, advanced_cfg, advanced_norm, advanced_denoise, advanced_steps, advanced_seed):
    global voxcpm_model, voxcpm_asr
    if voxcpm_model is None:
        raise gr.Error("请先切换并加载 VoxCPM2 引擎")
    import time as _time
    import librosa
    # ASR 识别参考音频文本
    ref_text = ""
    if ref_audio_path:
        try:
            res = voxcpm_asr.generate(input=ref_audio_path)
            if res and len(res) > 0 and "text" in res[0]:
                ref_text = res[0]["text"]
        except Exception:
            ref_text = ""
    # 极致克隆生成
    wav = voxcpm_model.generate(
        text=text,
        reference_wav_path=ref_audio_path if ref_audio_path else None,
        normalize=bool(advanced_norm),
        cfg_value=advanced_cfg,
        inference_timesteps=advanced_steps,
        denoise=bool(advanced_denoise),
        retry_badcase=False,
    )
    # 保存到 output 文件夹
    timestamp = int(_time.time())
    out_path = os.path.join(SAVE_DIR, f"voxcpm_ultimate_{timestamp}.wav")
    _save_wav_compatible(wav, out_path, 48000)
    return (48000, wav), ref_text



def get_persona_map():
    """获取音色名称到 wav 路径的映射"""
    persona_map = {}
    if not os.path.exists(PERSONA_DIR):
        return persona_map
    for f in os.listdir(PERSONA_DIR):
        if f.endswith(".wav"):
            name = f[:-4]
            wav_path = os.path.join(PERSONA_DIR, f)
            persona_map[name] = {"wav": wav_path}
    return persona_map

def fn_voxcpm_script_studio(script_text, advanced_cfg, advanced_norm, advanced_denoise, advanced_steps, advanced_seed, lang="中文"):
    global voxcpm_model, voxcpm_asr
    if voxcpm_model is None:
        raise gr.Error("请先切换并加载 VoxCPM2 引擎")
    import re
    import numpy as np
    try:
        persona_map = get_persona_map()
        lines = script_text.strip().split("\n")
        combined_wav = []
        sr_final = 48000
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = re.match(r"\[([^\]]+)\](?:\(([^)]+)\))?\s*(.*)", line)
            if not match:
                continue
            role_name = match.group(1).strip()
            emotion = match.group(2)
            content = match.group(3).strip()
            role_lower = role_name.lower()
            persona_key = next((k for k in persona_map if k.lower() == role_lower), None)
            if persona_key:
                ref_wav = persona_map[persona_key]["wav"]
            else:
                continue
            # 生成音频
            wav = voxcpm_model.generate(
                text=content,
                reference_wav_path=ref_wav,
                normalize=bool(advanced_norm),
                cfg_value=advanced_cfg,
                inference_timesteps=advanced_steps,
                denoise=bool(advanced_denoise),
                retry_badcase=False,
            )
            combined_wav.append(wav)
            # 添加 0.3 秒静音间隔
            combined_wav.append(np.zeros(int(48000 * 0.3)))
            sr_final = 48000
        if not combined_wav:
            return None, "❌ 匹配失败：请检查剧本格式或音色库"
        return (sr_final, np.concatenate(combined_wav)), "✅ 生成成功！"
    except Exception as e:
        logger.error(f"[VoxCPM剧本工坊] 错误: {e}")
        return None, f"❌ 生成失败: {e}"

# --- 【6. CSS 样式表（全面优化版）】 ---
ENHANCED_CSS = """

/* 1. output-panel 紫色背景（先注释掉，等调试完成后再启用） */
:root {
    --primary: #8B5CF6;
    --primary-hover: #7C3AED;
    --primary-light: #A78BFA;
    --primary-bg: rgba(139, 92, 246, 0.08);
    --primary-ring: rgba(139, 92, 246, 0.25);
    --primary-glow: rgba(139, 92, 246, 0.3);
    --primary-glow-strong: rgba(139, 92, 246, 0.5);

    --accent-success: #8B5CF6;
    --success-bg: rgba(139, 197, 94, 0.1);
    --accent-warning: #F59E0B;
    --warning-bg: rgba(245, 158, 11, 0.1);
    --warning-border: rgba(245, 158, 11, 0.3);
    --warning-text: #F59E0B;
    --accent-error: #EF4444;
    --error-bg: rgba(239, 68, 68, 0.1);
    --accent-info: #3B82F6;
    --info-bg: rgba(59, 130, 246, 0.1);

    --bg-primary: #0C0C18;
    --bg-secondary: #14142A;
    --bg-tertiary: #1E1E38;
    --bg-elevated: #282848;
    --bg-input: #1A1A34;
    --bg-input-focus: #202040;
    --bg-glass: rgba(20, 20, 42, 0.72);
    --bg-glass-light: rgba(30, 30, 56, 0.55);

    --border-subtle: rgba(255, 255, 255, 0.06);
    --border-medium: rgba(255, 255, 255, 0.12);
    --border-focus: #8B5CF6;
    --border-error: #EF4444;

    --text-primary: #F1F5F9;
    --text-secondary: #94A3B8;
    --text-muted: #9CA3AF;
    --text-disabled: #475569;
    --text-on-primary: #FFFFFF;

    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-5: 20px;
    --space-6: 24px;
    --space-8: 32px;
    --space-10: 40px;
    --space-12: 48px;
    --space-16: 64px;

    --radius-sm: 6px;
    --radius-md: 8px;
    --radius-lg: 12px;
    --radius-xl: 16px;
    --radius-2xl: 20px;
    --radius-full: 100px;

    --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
    --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.25);
    --shadow-card: 0 4px 16px rgba(0, 0, 0, 0.3);
    --shadow-elevated: 0 8px 32px rgba(0, 0, 0, 0.4);
    --shadow-glow: 0 0 16px var(--primary-glow);
    --shadow-glow-strong: 0 0 24px var(--primary-glow-strong);

    --ease-standard: cubic-bezier(0.4, 0, 0.2, 1);
    --ease-decelerate: cubic-bezier(0, 0, 0.2, 1);
    --ease-accelerate: cubic-bezier(0.4, 0, 1, 1);
    --duration-fast: 150ms;
    --duration-normal: 250ms;
    --duration-slow: 350ms;
    --duration-entrance: 400ms;

    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans SC', sans-serif;
    --font-display: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;

    --text-xs: 12px;
    --text-sm: 13px;
    --text-base: 14px;
    --text-md: 15px;
    --text-lg: 16px;
    --text-xl: 18px;
    --text-2xl: 20px;
    --text-3xl: 24px;
    --text-4xl: 28px;
    --text-5xl: 32px;

    --leading-tight: 1.25;
    --leading-normal: 1.5;
    --leading-relaxed: 1.6;
    --leading-loose: 1.8;

    --icon-sm: 16px;
    --icon-md: 20px;
    --icon-lg: 24px;
    --icon-xl: 32px;

    --blur-sm: 8px;
    --blur-md: 12px;
    --blur-lg: 16px;
    --blur-xl: 20px;

    --color-success: #10b981;
    --color-success-light: #34d399;
    --color-warning: #f59e0b;
    --color-warning-light: #fbbf24;
    --color-error: #ef4444;
    --color-error-light: #f87171;
    --color-info: #3b82f6;
    --color-info-light: #60a5fa;
    --spacing-1: 4px;
    --spacing-2: 8px;
    --spacing-3: 12px;
    --spacing-4: 16px;
    --spacing-5: 20px;
    --spacing-6: 24px;
    --spacing-8: 32px;
    --radius-sm: 4px;
    --radius-md: 8px;
    --radius-lg: 12px;
    --radius-xl: 16px;
    --radius-full: 9999px;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
    --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1);
    --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1);
    --ease-standard: cubic-bezier(0.4, 0, 0.2, 1);
    --ease-decelerate: cubic-bezier(0, 0, 0.2, 1);
    --ease-accelerate: cubic-bezier(0.4, 0, 1, 1);
}

/* --- 1.5 主题系统：白天/暗夜模式（修复版） --- */

/* 暗夜模式变量（默认） */
html, html.dark {
    --bg-primary: #0C0C18;
    --bg-secondary: #14142A;
    --bg-tertiary: #1E1E38;
    --bg-elevated: #282848;
    --bg-input: #1A1A34;
    --bg-input-focus: #202040;
    --bg-glass: rgba(20, 20, 42, 0.72);
    --bg-glass-light: rgba(30, 30, 56, 0.55);
    --bg-placeholder: #1a1a3e;
    --bg-card: #14142A;

    --border-subtle: rgba(255, 255, 255, 0.06);
    --border-medium: rgba(255, 255, 255, 0.12);
    --border-focus: #8B5CF6;
    --border-error: #EF4444;

    --text-primary: #F1F5F9;
    --text-secondary: #94A3B8;
    --text-muted: #9CA3AF;
    --text-disabled: #475569;
    --text-on-primary: #FFFFFF;

    --audio-border: rgba(139, 92, 246, 0.3);
    --audio-note-color: #8B5CF6;
}

/* 白天模式变量（修复版 - 正确的浅色主题） */
html.light {
    --bg-primary: #FAFBFC;
    --bg-secondary: #FFFFFF;
    --bg-tertiary: #F0F2F7;
    --bg-elevated: #E8EBF2;
    --bg-input: #FFFFFF;
    --bg-input-focus: #F5F7FA;
    --bg-glass: rgba(255, 255, 255, 0.85);
    --bg-glass-light: rgba(248, 249, 252, 0.7);
    --bg-placeholder: #f5f7fa;
    --bg-card: #FFFFFF;

    --border-subtle: rgba(0, 0, 0, 0.08);
    --border-medium: rgba(0, 0, 0, 0.15);
    --border-focus: #8B5CF6;
    --border-error: #EF4444;

    --text-primary: #1A1A2E;
    --text-secondary: #4A5568;
    --text-muted: #718096;
    --text-disabled: #A0AEC0;
    --text-on-primary: #FFFFFF;

    --audio-border: rgba(139, 92, 246, 0.2);
    --audio-note-color: #7C3AED;
}

/* 主题背景色 */
html, html.dark {
    background: var(--bg-primary) !important;
    margin: 0 !important;
    padding: 0 !important;
}

html.light {
    background: var(--bg-primary) !important;
    margin: 0 !important;
    padding: 0 !important;
}

body, body.dark {
    background: var(--bg-primary) !important;
    margin: 0 !important;
    padding: 0 !important;
}

body.light {
    background: var(--bg-primary) !important;
    margin: 0 !important;
    padding: 0 !important;
}

/* 全屏适配 */
.gradio-app, #__gradio__container__, gradio-app {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    background: var(--bg-primary) !important;
}

/* Gradio 容器 */
.gradio-container, .gradio-container.dark, .gradio-container.light {
    background: var(--bg-primary) !important;
    margin: 0 !important;
    padding: var(--space-4) var(--space-4) !important;
}

/* 区块/分组/卡片 */
form, .form, .block, .gradio-container form, .gradio-container .block,
.gradio-container .gradio-container-outer, .gradio-container .gradio-container-inner,
.gradio-container .gradio-container-inner > div,
.gradio-container .gradio-container-outer > div {
    background: var(--bg-primary) !important;
}

/* Group */
.gradio-container .gr-group, .gr-group {
    background: var(--bg-secondary) !important;
    border-color: var(--border-subtle) !important;
}

/* Panel / TabPanel */
.gradio-container .gr-panel, .gr-panel, .gradio-container .gr-tabpanel, .gr-tabpanel {
    background: var(--bg-secondary) !important;
}

/* Input 组件 */
.gradio-container input, .gradio-container select, .gradio-container textarea,
input, select, textarea {
    background: var(--bg-input) !important;
    color: var(--text-primary) !important;
    border-color: var(--border-medium) !important;
}

.gradio-container input:focus, .gradio-container select:focus, .gradio-container textarea:focus,
input:focus, select:focus, textarea:focus {
    background: var(--bg-input-focus) !important;
    border-color: var(--primary) !important;
}

/* Dropdown 列表 */
.gradio-container .gr-dropdown-list, .gr-dropdown-list {
    background: var(--bg-tertiary) !important;
    color: var(--text-primary) !important;
    border-color: var(--border-subtle) !important;
}

.gradio-container .gr-dropdown-list li, .gr-dropdown-list li {
    background: var(--bg-tertiary) !important;
    color: var(--text-primary) !important;
}

.gradio-container .gr-dropdown-list li:hover, .gr-dropdown-list li:hover {
    background: var(--bg-elevated) !important;
}

/* Markdown/HTML 区块 */
.gradio-container .prose, .gradio-container .markdown-body,
.prose, .markdown-body {
    background: var(--bg-secondary) !important;
    color: var(--text-primary) !important;
}

/* Accordion */
.gradio-container .gr-accordion, .gr-accordion {
    background: var(--bg-secondary) !important;
    border-color: var(--border-subtle) !important;
}

/* Table */
.gradio-container table, table {
    background: var(--bg-secondary) !important;
    color: var(--text-primary) !important;
}

.gradio-container th, .gradio-container td, th, td {
    background: var(--bg-tertiary) !important;
    color: var(--text-primary) !important;
    border-color: var(--border-subtle) !important;
}

/* label / legend */
.gradio-container label, .gradio-container .form-group-label,
.gradio-container legend, label, .form-group-label, legend {
    background: transparent !important;
}

/* Tab 区域 */
.gradio-container .tabs, .tabs {
    background: var(--bg-primary) !important;
}

.gradio-container .tab-nav, .tab-nav {
    background: var(--bg-primary) !important;
    border-bottom-color: var(--border-subtle) !important;
}

/* Footer */
.gradio-container .gradio-footer, .gradio-footer {
    background: var(--bg-primary) !important;
}

/* ===== 统一按钮体系 ===== */
.btn-primary {
    background: linear-gradient(135deg, var(--primary), var(--primary-hover)) !important;
    color: #fff !important;
    border: none !important;
    border-radius: var(--radius-lg) !important;
    padding: var(--spacing-3) var(--spacing-5) !important;
    font-weight: 600 !important;
    font-size: var(--text-sm) !important;
    cursor: pointer !important;
    transition: all 0.2s var(--ease-standard) !important;
    box-shadow: var(--shadow-sm) !important;
}
.btn-primary:hover:not(:disabled) {
    transform: translateY(-1px) !important;
    box-shadow: var(--shadow-md) !important;
}
.btn-primary:active:not(:disabled) {
    transform: translateY(0) !important;
}
.btn-primary:disabled {
    opacity: 0.5 !important;
    cursor: not-allowed !important;
    transform: none !important;
}
.btn-secondary {
    background: var(--bg-tertiary) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: var(--radius-lg) !important;
    padding: var(--spacing-3) var(--spacing-5) !important;
    font-weight: 500 !important;
    font-size: var(--text-sm) !important;
    cursor: pointer !important;
    transition: all 0.2s var(--ease-standard) !important;
}
.btn-secondary:hover:not(:disabled) {
    background: var(--bg-hover) !important;
    border-color: var(--primary) !important;
}
.btn-danger {
    background: var(--color-error) !important;
    color: #fff !important;
    border: none !important;
    border-radius: var(--radius-lg) !important;
    padding: var(--spacing-3) var(--spacing-5) !important;
    font-weight: 600 !important;
    font-size: var(--text-sm) !important;
    cursor: pointer !important;
    transition: all 0.2s var(--ease-standard) !important;
}
.btn-danger:hover:not(:disabled) {
    background: var(--color-error-light) !important;
}
.btn-ghost {
    background: transparent !important;
    color: var(--text-secondary) !important;
    border: 1px solid transparent !important;
    border-radius: var(--radius-lg) !important;
    padding: var(--spacing-3) var(--spacing-5) !important;
    font-weight: 500 !important;
    font-size: var(--text-sm) !important;
    cursor: pointer !important;
    transition: all 0.2s var(--ease-standard) !important;
}
.btn-ghost:hover:not(:disabled) {
    background: var(--bg-hover) !important;
    color: var(--text-primary) !important;
}

/* ===== 统一输入组件 ===== */
.tts-input-textbox input,
.tts-input-textarea textarea,
.tts-input-dropdown select {
    background: var(--bg-primary) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--spacing-3) var(--spacing-4) !important;
    color: var(--text-primary) !important;
    font-size: var(--text-sm) !important;
    transition: border-color 0.2s var(--ease-standard), box-shadow 0.2s var(--ease-standard) !important;
}
.tts-input-textbox input:focus,
.tts-input-textarea textarea:focus,
.tts-input-dropdown select:focus {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15) !important;
    outline: none !important;
}
.tts-input-textbox input::placeholder,
.tts-input-textarea textarea::placeholder {
    color: var(--text-muted) !important;
}
.tts-input-textbox input:disabled,
.tts-input-textarea textarea:disabled,
.tts-input-dropdown select:disabled {
    opacity: 0.5 !important;
    cursor: not-allowed !important;
    background: var(--bg-tertiary) !important;
}

/* ===== 统一卡片/面板 ===== */
.tts-card {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-xl) !important;
    padding: var(--spacing-5) !important;
    transition: all 0.2s var(--ease-standard) !important;
}
.tts-card:hover {
    border-color: var(--border-default) !important;
    box-shadow: var(--shadow-md) !important;
}
.tts-card-header {
    display: flex !important;
    align-items: center !important;
    gap: var(--spacing-3) !important;
    padding-bottom: var(--spacing-4) !important;
    border-bottom: 1px solid var(--border-subtle) !important;
    margin-bottom: var(--spacing-4) !important;
}
.tts-card-title {
    font-size: var(--text-lg) !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
}
.tts-panel {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-lg) !important;
    overflow: hidden !important;
}
.tts-panel-header {
    background: var(--bg-tertiary) !important;
    padding: var(--spacing-3) var(--spacing-4) !important;
    font-weight: 600 !important;
    font-size: var(--text-sm) !important;
    color: var(--text-primary) !important;
    border-bottom: 1px solid var(--border-subtle) !important;
}
.tts-panel-body {
    padding: var(--spacing-4) !important;
}

/* ===== 统一音频播放器 ===== */
.tts-audio-player audio {
    width: 100% !important;
    border-radius: var(--radius-lg) !important;
    border: 1px solid var(--border-subtle) !important;
    background: var(--bg-secondary) !important;
}
.tts-audio-player .audio-label {
    font-size: var(--text-xs) !important;
    color: var(--text-muted) !important;
    margin-top: var(--spacing-1) !important;
}

/* ===== 统一 Toast 通知 ===== */
.tts-toast {
    position: fixed !important;
    top: 20px !important;
    right: 20px !important;
    z-index: 10000 !important;
    padding: var(--spacing-3) var(--spacing-5) !important;
    border-radius: var(--radius-lg) !important;
    font-size: var(--text-sm) !important;
    font-weight: 500 !important;
    box-shadow: var(--shadow-lg) !important;
    animation: tts-toast-in 0.3s var(--ease-decelerate) !important;
    max-width: 400px !important;
}
.tts-toast-success {
    background: var(--color-success) !important;
    color: #fff !important;
}
.tts-toast-warning {
    background: var(--color-warning) !important;
    color: #000 !important;
}
.tts-toast-error {
    background: var(--color-error) !important;
    color: #fff !important;
}
.tts-toast-info {
    background: var(--color-info) !important;
    color: #fff !important;
}
@keyframes tts-toast-in {
    from { opacity: 0; transform: translateX(100px); }
    to { opacity: 1; transform: translateX(0); }
}

/* 状态条/进度条 */
.gradio-container .status-bar-container, .status-bar-container {
    background: var(--bg-secondary) !important;
}

/* HTML 组件 */
.gradio-container .gradio-html, .gradio-html {
    background: var(--bg-secondary) !important;
}

/* Card 组件 */
.gradio-container .card, .gradio-container .feature-card {
    background: var(--bg-secondary) !important;
    border-color: var(--border-subtle) !important;
}

/* Gradio 面板区域 */
.gradio-container [class*="wrap"], [class*="wrap"] {
    background: var(--bg-secondary) !important;
}

.gradio-container [class*="container"] [class*="wrap"],
.gradio-container .block [class*="wrap"] {
    background: var(--bg-secondary) !important;
}

/* 未设置背景的 div */
.gradio-container div:not([class]) {
    background: transparent !important;
}

/* Gradio 内部容器 */
.gradio-container [class*="block"],
.gradio-container [class*="container"] > div,
.gradio-container [class*="container"] > div > div,
.gradio-container [class*="form"] > div,
.gradio-container [class*="wrap"] > div,
.gradio-container .block > div,
.gradio-container .form > div {
    background: transparent !important;
}

/* ===== 合成结果板块 - 样式修复 ===== */
/* Gradio 完全忽略 elem_id 和 elem_classes，所有样式由 JavaScript 动态应用 */

/* ===== 隐藏 Gradio 下拉框箭头（白色三角形） ===== */
/* Gradio dropdown 使用 SVG 或 border 技巧创建箭头 */
select, .gradio-container select {
    appearance: none !important;
    -webkit-appearance: none !important;
    -moz-appearance: none !important;
    background-image: none !important;
}
/* 隐藏 Gradio dropdown 的默认箭头 */
.gradio-container .form select {
    appearance: none !important;
    -webkit-appearance: none !important;
    background-image: none !important;
}
/* 隐藏所有可能的三角形元素 */
svg[width="12"][height="12"],
svg[width="10"][height="10"],
svg[width="16"][height="16"] {
    display: none !important;
}
/* 隐藏通过 border 技巧创建的三角形 */
div::before, div::after,
span::before, span::after,
i::before, i::after {
    border-color: transparent !important;
}

/* ===== 强制隐藏 Gradio 折叠/展开指示器 ===== */
/* 使用通用选择器匹配所有可能的三角形 */
[class*="collapse"],
[class*="expand"],
[class*="toggle"],
[class*="arrow"],
[class*="chevron"],
[data-testid*="collapse"],
[data-testid*="expand"],
[data-testid*="toggle"] {
    display: none !important;
}
/* 隐藏 Gradio 面板的装饰元素 */
.gr-group > div:first-child::before,
.gr-group > div:first-child::after {
    display: none !important;
}
/* 移除所有白色小三角形 */
div[style*="border-top"],
div[style*="border-left"],
span[style*="border-top"],
span[style*="border-left"] {
    border-color: transparent !important;
}

/* ===== 强制隐藏页面右侧的白色三角形 ===== */
/* 使用位置检测 - 右侧边缘的小元素 */
/* deep DOM selector removed - fragile across Gradio versions */
/* 隐藏所有小尺寸白色SVG */
svg {
    max-width: 100%;
}
/* svg[viewBox] 通用选择器过于宽泛，已移除 - 改为针对性隐藏 */

/* ===== 隐藏 .gr-group 内的小SVG（三角形可能在这里） ===== */
.gr-group svg,
.gr-group [class*="svg"] {
    max-width: 100%;
}
/* 强制隐藏 gr-group 内所有非内容SVG */
.gr-group svg:not([master]):not([width="120"]):not([height="120"]) {
    display: none !important;
}

/* ===== 隐藏下拉框箭头 ===== */
/* Gradio 下拉框使用多种技术创建箭头 */
select option {
    appearance: none !important;
}
/* 隐藏所有表单内的下拉框箭头 */
.form select,
.wrap select,
.block select {
    appearance: none !important;
    -webkit-appearance: none !important;
    background-image: none !important;
}
/* select 不支持伪元素，已移除相关规则 */
/* 隐藏所有小尺寸三角形（通用） */
svg[width][height] {
    max-width: 100% !important;
}
/* 强制隐藏所有15x15以下的SVG - 改为仅隐藏溢出 */
svg:not([master]) {
    overflow: visible !important;
}

/* ===== 生成进度条 ===== */
.tts-progress-container {
    margin: 8px 0;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border-subtle);
}
.tts-progress-bar {
    width: 100%;
    height: 8px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-full);
    overflow: hidden;
    margin-bottom: 8px;
}
.tts-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--primary), var(--primary-light));
    border-radius: var(--radius-full);
    transition: width 0.3s var(--ease-standard);
    position: relative;
}
.tts-progress-fill::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
    animation: tts-progress-shimmer 1.5s infinite;
}
@keyframes tts-progress-shimmer {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(100%); }
}
.tts-progress-info {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    font-size: var(--text-sm);
    color: var(--text-secondary);
}
.tts-progress-phase {
    color: var(--primary-light);
    font-weight: 500;
}
.tts-progress-segment {
    color: var(--text-muted);
}
.tts-progress-remaining {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-xs);
}

/* 移除旧的强制深色 JS - 改为 CSS 变量驱动 */

/* 模型规格 Radio 按钮优化 - 选中状态实心填充 */
.gradio-container .form input[type="radio"],
input[type="radio"] {
    appearance: none !important;
    -webkit-appearance: none !important;
    width: 20px !important;
    height: 20px !important;
    border: 2px solid var(--border-medium) !important;
    border-radius: 50% !important;
    background: transparent !important;
    cursor: pointer !important;
    position: relative !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    flex-shrink: 0 !important;
}

.gradio-container .form input[type="radio"]:checked,
input[type="radio"]:checked {
    border-color: var(--primary) !important;
    background: var(--primary) !important;
    box-shadow: 0 0 0 3px var(--primary-ring), inset 0 0 0 3px var(--bg-secondary) !important;
}

.gradio-container .form input[type="radio"]:hover,
input[type="radio"]:hover {
    border-color: var(--primary-light) !important;
}

/* 音频组件 - 给予足够空间显示完整播放器 */
.gradio-container .form audio,
.gradio-container audio,
.gradio-container .gradio-audio,
.gradio-container .component.audio,
.purple-audio {
    min-height: 100px !important;
    max-height: none !important;
    height: auto !important;
}

/* 音频内部容器 */
.gradio-audio > div,
.component.audio > div {
    min-height: 80px !important;
    padding: 10px !important;
}

/* 音乐图标占位 - 缩小显示 */
.audio-placeholder, .audio-placeholder-icon {
    max-height: 80px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    font-size: 36px !important;
    opacity: 0.4 !important;
}

/* 历史记录/音色库面板 - 增大信息展示区域 */
.gradio-container .history-panel,
.gradio-container .persona-panel,
.gradio-container .list-panel {
    min-height: 300px !important;
}

/* Dropdown 选择器 - 增大可点击区域 */
.gradio-container select, select {
    min-height: 36px !important;
    padding: 6px 12px !important;
    font-size: var(--text-base) !important;
}

/* 音乐图标 SVG 占位 - 大幅缩小，仅作功能标识 */
.gradio-container .block.audio svg,
.gradio-container audio + svg,
.gradio-container [class*="audio"] svg,
.gradio-container .form svg[master],
.gradio-container .block[data-testid="audio"] svg,
.gradio-container svg[viewBox] {
    max-width: 100px !important;
    max-height: 100px !important;
    width: 100px !important;
    height: 100px !important;
    margin: 0 auto !important;
    display: block !important;
}

/* 音频容器整体缩小 */
.gradio-container .block.audio,
.gradio-container .form[data-testid="audio"],
.gradio-container [class*="audio"],
.gradio-container [class*="Audio"],
.gradio-container .wrap.audio {
    min-height: auto !important;
    max-height: 150px !important;
    padding: 8px !important;
}

/* 音频占位区域的 padding 压缩 */
.gradio-container .block.audio > div,
.gradio-container [class*="audio"] > div,
.gradio-container [data-testid="block-audio"] > div {
    padding: 0 !important;
    margin: 0 !important;
}

/* 音乐图标的主题色适配 */
html.dark .gradio-container .block.audio svg path,
html.dark .gradio-container audio + svg path {
    fill: var(--text-muted) !important;
}

html.light .gradio-container .block.audio svg path,
html.light .gradio-container audio + svg path {
    fill: var(--text-secondary) !important;
}

/* 横屏布局优化 - 充分利用宽屏 */
@media (min-width: 1200px) {
    .gradio-container {
        padding: var(--space-4) var(--space-6) !important;
    }
}

@media (min-width: 1400px) {
    .gradio-container {
        padding: var(--space-6) var(--space-8) !important;
    }
}

@media (min-width: 1600px) {
    .gradio-container {
        padding: var(--space-6) var(--space-10) !important;
    }
}

/* --- 2. 全局基础样式 --- */
*, *::before, *::after {
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
    -webkit-text-size-adjust: 100%;
}

body {
    font-family: var(--font-sans) !important;
    font-size: var(--text-base) !important;
    line-height: 1.7 !important;
    color: var(--text-primary) !important;
    background: var(--bg-primary) !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
}

.gradio-container {
    max-width: 100% !important;
    width: 100% !important;
    margin: 0 !important;
    padding: var(--space-4) var(--space-4) !important;
    background: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

/* 强制最外层 wrapper 全屏无留白 */
.gradio-container-outer, .gradio-container-inner,
.gradio-container > div:first-child {
    max-width: 100% !important;
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
}

/* 图片响应式适配 - 防止暴力拉伸变形 */
img, .gradio-container img, .hero-banner img, .feature-card img {
    max-width: 100% !important;
    height: auto !important;
    object-fit: contain !important;
    object-position: center !important;
}

/* 背景图片适配 - 保持比例覆盖 */
.hero-banner::before, .hero-banner::after {
    background-size: cover !important;
}

/* 所有带背景图的元素使用 cover 模式 */
[class*="banner"], [class*="hero"], [class*="feature"] {
    background-size: cover !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
}

/* --- 3. 滚动条样式 --- */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: var(--border-medium);
    border-radius: var(--radius-full);
    transition: background var(--duration-normal) var(--ease-standard);
}

::-webkit-scrollbar-thumb:hover {
    background: var(--primary);
}

/* --- 4. 字体排版系统（优化版） --- */
h1, h2, h3, h4, h5, h6 {
    font-family: var(--font-display) !important;
    color: var(--text-primary) !important;
    line-height: var(--leading-tight) !important;
    letter-spacing: -0.025em !important;
    margin-top: 0 !important;
}

h1 { font-size: var(--text-5xl) !important; font-weight: 800 !important; letter-spacing: -0.03em !important; }
h2 { font-size: var(--text-3xl) !important; font-weight: 700 !important; }
h3 { font-size: var(--text-2xl) !important; font-weight: 700 !important; line-height: 1.3 !important; }
h4 { font-size: var(--text-xl) !important; font-weight: 600 !important; }
h5 { font-size: var(--text-lg) !important; font-weight: 600 !important; }
h6 { font-size: var(--text-md) !important; font-weight: 600 !important; }

p {
    margin: 0 0 var(--space-3) 0 !important;
    line-height: var(--leading-relaxed) !important;
}

small, .text-small, .text-xs {
    font-size: var(--text-xs) !important;
    line-height: var(--leading-normal) !important;
}

.text-muted {
    color: var(--text-muted) !important;
}

.text-secondary {
    color: var(--text-secondary) !important;
}

/* --- 5. 简洁导航栏（替代 Hero Banner） --- */
.simple-nav {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    padding: 12px 20px !important;
    margin-bottom: 12px !important;
    background: linear-gradient(135deg, #4C1D95 0%, #5B21B6 50%, #7C3AED 100%) !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 16px rgba(76, 29, 149, 0.3) !important;
    border: 1px solid rgba(167, 139, 250, 0.3) !important;
    animation: hero-entrance 0.4s ease-out !important;
}

.nav-brand {
    font-size: 18px !important;
    font-weight: 800 !important;
    color: #ffffff !important;
    letter-spacing: -0.02em !important;
    text-shadow: 0 2px 10px rgba(0,0,0,0.2) !important;
}

.nav-badges {
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
}

.nav-badge {
    display: inline-flex !important;
    align-items: center !important;
    gap: 4px !important;
    padding: 4px 10px !important;
    border-radius: 20px !important;
    background: rgba(255,255,255,0.1) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    font-size: 11px !important;
    color: rgba(255,255,255,0.95) !important;
    font-weight: 600 !important;
    backdrop-filter: blur(8px) !important;
}

/* 状态指示点 */
.status-dot {
    width: 6px !important;
    height: 6px !important;
    border-radius: 50% !important;
    background: #8B5CF6 !important;
    box-shadow: 0 0 8px #8B5CF6 !important;
}

/* Hero Banner 和 Features Grid 旧样式保留但不使用（向后兼容） */
.hero-banner { display: none !important; }
.features-grid { display: none !important; }
.feature-card { display: none !important; }

/* --- 6. 功能特性卡片网格（已隐藏，原样式保留） --- */
.features-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 12px;
}

.feature-card {
    background: linear-gradient(145deg, rgba(20, 20, 42, 0.85) 0%, rgba(30, 30, 56, 0.75) 100%) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border: 1px solid rgba(139, 92, 246, 0.15) !important;
    border-radius: 12px !important;
    padding: 16px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    cursor: default;
    position: relative;
    overflow: hidden;
    animation: card-entrance 0.4s ease-out backwards;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3) !important;
}

.feature-card:nth-child(1) { animation-delay: 0.05s; }
.feature-card:nth-child(2) { animation-delay: 0.1s; }
.feature-card:nth-child(3) { animation-delay: 0.15s; }
.feature-card:nth-child(4) { animation-delay: 0.2s; }

@keyframes card-entrance {
    from {
        opacity: 0;
        transform: translateY(16px) scale(0.98);
    }
    to {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
}

.feature-card::before {
    content: '' !important;
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    height: 3px !important;
    background: linear-gradient(90deg, #8B5CF6 0%, #6366F1 50%, #A78BFA 100%) !important;
    transform: scaleX(0) !important;
    transform-origin: left !important;
    transition: transform 0.3s ease !important;
}

.feature-card::after {
    content: '' !important;
    position: absolute !important;
    inset: 0 !important;
    background: radial-gradient(circle at var(--mouse-x, 50%) var(--mouse-y, 50%), rgba(139,92,246,0.08) 0%, transparent 60%) !important;
    opacity: 0 !important;
    transition: opacity 0.3s ease !important;
    pointer-events: none !important;
}

.feature-card:hover {
    transform: translateY(-6px) scale(1.02) !important;
    border-color: rgba(139, 92, 246, 0.4) !important;
    box-shadow: 0 12px 40px rgba(139, 92, 246, 0.25), 0 0 20px rgba(139, 92, 246, 0.15) !important;
    background: linear-gradient(145deg, rgba(30, 30, 56, 0.95) 0%, rgba(40, 40, 72, 0.9) 100%) !important;
}

.feature-card:hover::before {
    transform: scaleX(1) !important;
}

.feature-card:hover::after {
    opacity: 1 !important;
}

.feature-icon {
    font-size: 28px !important;
    margin-bottom: 14px !important;
    display: block;
    transition: all 0.3s ease !important;
    filter: drop-shadow(0 2px 8px rgba(139, 92, 246, 0.3));
}

.feature-card:hover .feature-icon {
    transform: scale(1.15) rotate(-5deg) !important;
    filter: drop-shadow(0 4px 12px rgba(139, 92, 246, 0.5));
}

.feature-title {
    font-size: var(--text-md) !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    margin: 0 0 var(--space-2) 0 !important;
}

.feature-desc {
    font-size: var(--text-sm) !important;
    color: var(--text-secondary) !important;
    margin: 0 !important;
    line-height: var(--leading-relaxed) !important;
}

/* --- 7. 状态栏和进度指示器（优化版） --- */
.status-bar-container {
    background: var(--bg-glass);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: var(--space-3) var(--space-5);
    margin-bottom: var(--space-4);
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: var(--shadow-md);
    transition: all var(--duration-normal) var(--ease-standard);
    position: sticky;
    top: 0;
    z-index: 100;
}

.status-bar-container:hover {
    box-shadow: var(--shadow-glow);
    border-color: var(--primary-ring);
}

#status-bar {
    color: var(--text-primary) !important;
    font-size: var(--text-sm) !important;
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
}

@keyframes pulse-dot {
    0%, 100% {
        opacity: 1;
        box-shadow: 0 0 4px var(--accent-success);
        transform: scale(1);
    }
    50% {
        opacity: 0.6;
        box-shadow: 0 0 10px var(--accent-warning);
        transform: scale(1.15);
    }
}

.status-pulse {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent-success);
    animation: pulse-dot 2s ease-in-out infinite;
    margin-right: var(--space-2);
    box-shadow: 0 0 4px var(--accent-success);
}

.status-pulse.busy {
    background: var(--accent-warning);
    animation-duration: 1s;
    box-shadow: 0 0 4px var(--accent-warning);
}

.status-pulse.error {
    background: var(--accent-error);
    animation: none;
    box-shadow: 0 0 4px var(--accent-error);
}

.progress-container {
    background: var(--bg-glass);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: var(--space-2) var(--space-4);
    margin-bottom: var(--space-2);
    box-shadow: var(--shadow-md);
    transition: all var(--duration-normal) var(--ease-standard);
}

.progress-container:has(#progress-bar:not(:empty)) {
    border-color: var(--primary-ring);
    animation: progress-glow 2s ease-in-out infinite;
}

@keyframes progress-glow {
    0%, 100% { box-shadow: var(--shadow-md), 0 0 8px var(--primary-glow); }
    50% { box-shadow: var(--shadow-md), 0 0 16px var(--primary-glow-strong); }
}

#progress-bar {
    color: var(--text-primary) !important;
    font-size: var(--text-sm) !important;
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
}

@keyframes shimmer {
    0% { background-position: -200% center; }
    100% { background-position: 200% center; }
}

.progress-shimmer {
    background: linear-gradient(
        90deg,
        transparent 0%,
        rgba(139,92,246,0.06) 25%,
        rgba(99,102,241,0.12) 50%,
        rgba(139,92,246,0.06) 75%,
        transparent 100%
    );
    background-size: 200% 100%;
    animation: shimmer 3s linear infinite;
    border-radius: var(--radius-md);
}

/* --- 8. 标签页系统（优化版） --- */
.enhanced-tabs > .tab-nav {
    background: var(--bg-secondary) !important;
    border-radius: var(--radius-xl) var(--radius-xl) 0 0 !important;
    padding: var(--space-2) var(--space-2) 0 var(--space-2) !important;
    border: 1px solid var(--border-subtle) !important;
    border-bottom: none !important;
    gap: var(--space-1) !important;
    box-shadow: var(--shadow-sm);
}

.enhanced-tabs > .tab-nav button {
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: var(--radius-md) var(--radius-md) 0 0 !important;
    padding: var(--space-3) var(--space-4) !important;
    font-size: var(--text-sm) !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    position: relative;
    overflow: hidden;
    filter: grayscale(1) opacity(0.6);
}

.enhanced-tabs > .tab-nav button::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 50%;
    right: 50%;
    height: 2px;
    background: linear-gradient(90deg, #f97316, #fb923c);
    transition: all var(--duration-normal) var(--ease-standard);
    border-radius: 2px 2px 0 0;
}

.enhanced-tabs > .tab-nav button:hover {
    color: var(--text-primary) !important;
    background: var(--primary-bg) !important;
    filter: grayscale(0.5) opacity(0.8);
}

.enhanced-tabs > .tab-nav button:hover::after {
    left: 20%;
    right: 20%;
}

.enhanced-tabs > .tab-nav button.selected {
    background: var(--bg-tertiary) !important;
    color: #f97316 !important;
    border-color: var(--border-subtle) !important;
    border-bottom-color: var(--bg-tertiary) !important;
    filter: none;
}

.enhanced-tabs > .tab-nav button.selected::after {
    left: 0;
    right: 0;
}

@keyframes tab-content-enter {
    from {
        opacity: 0;
        transform: translateY(8px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.enhanced-tabs > .tab-item {
    animation: tab-content-enter var(--duration-slow) var(--ease-decelerate);
}

.enhanced-tabs > .tab-wrap {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 0 0 var(--radius-xl) var(--radius-xl) !important;
    padding: var(--space-6) !important;
    border-top: none !important;
    box-shadow: var(--shadow-card);
}

/* --- 9. 卡片组件系统（优化版） --- */
.card {
    background: var(--bg-glass);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xl);
    padding: var(--space-6);
    margin-bottom: var(--space-4);
    box-shadow: var(--shadow-card);
    transition: all var(--duration-normal) var(--ease-standard);
    position: relative;
    overflow: hidden;
}

.card:hover {
    box-shadow: var(--shadow-elevated);
    border-color: var(--border-medium);
}

.card-header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-3);
    padding-bottom: var(--space-2);
    border-bottom: 1px solid var(--border-subtle);
}

.card-header-icon {
    font-size: var(--icon-md);
    transition: transform var(--duration-normal) var(--ease-standard);
}

.card:hover .card-header-icon {
    transform: scale(1.06);
}

.card-header-title {
    font-size: var(--text-md) !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    margin: 0 !important;
}

/* --- 10. 输出面板（优化版） --- */
.output-panel {
    background: var(--bg-glass);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xl);
    padding: var(--space-6);
    box-shadow: var(--shadow-card);
    min-height: 180px;
    transition: all var(--duration-normal) var(--ease-standard);
    position: relative;
}

.output-panel:hover {
    border-color: var(--border-medium);
    box-shadow: var(--shadow-elevated);
}

.output-empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 24px 16px;
    color: #FFFFFF;
    font-size: 14px;
    text-align: center;
    opacity: 0.8;
}
.output-empty-state .empty-wave {
    display: flex;
    gap: 3px;
    margin-bottom: 12px;
    align-items: center;
}
.output-empty-state .empty-wave span {
    display: inline-block;
    width: 3px;
    height: 16px;
    background: rgba(255,255,255,0.4);
    border-radius: 2px;
    animation: empty-wave-bar 1.2s ease-in-out infinite;
}
.output-empty-state .empty-wave span:nth-child(2) { animation-delay: 0.1s; height: 20px; }
.output-empty-state .empty-wave span:nth-child(3) { animation-delay: 0.2s; height: 24px; }
.output-empty-state .empty-wave span:nth-child(4) { animation-delay: 0.3s; height: 20px; }
.output-empty-state .empty-wave span:nth-child(5) { animation-delay: 0.4s; height: 16px; }
@keyframes empty-wave-bar {
    0%, 100% { transform: scaleY(0.4); opacity: 0.4; }
    50% { transform: scaleY(1); opacity: 0.8; }
}

/* --- 11. 表单输入系统（优化版） --- */
textarea, input[type="text"], input[type="number"], input[type="password"], select {
    background: var(--bg-input) !important;
    border: 1px solid var(--border-medium) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    font-size: var(--text-base) !important;
    line-height: var(--leading-relaxed) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    padding: var(--space-3) var(--space-4) !important;
    font-family: var(--font-sans) !important;
}

textarea:hover, input[type="text"]:hover, input[type="number"]:hover, select:hover {
    border-color: var(--border-medium) !important;
    background: var(--bg-input-focus) !important;
}

textarea:focus, input[type="text"]:focus, input[type="number"]:focus, select:focus {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px var(--primary-ring) !important;
    outline: none !important;
    background: var(--bg-input-focus) !important;
}

textarea.is-error, input.is-error {
    border-color: var(--accent-error) !important;
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15) !important;
}

textarea::placeholder, input::placeholder {
    color: rgba(180, 170, 200, 0.9) !important;
    opacity: 0.9;
}

label, .gradio-container label {
    color: var(--text-secondary) !important;
    font-size: var(--text-sm) !important;
    font-weight: 600 !important;
    margin-bottom: var(--space-2) !important;
    display: block;
    letter-spacing: 0.01em;
}

/* --- 12. 按钮系统（优化版） --- */

/* --- 4.1 圆角规范统一 --- */
/* Small elements (inputs, buttons): border-radius: 8px */
input, select, textarea, button,
.gradio-container input, .gradio-container select, .gradio-container textarea, .gradio-container button {
    border-radius: 8px !important;
}

/* Cards (gr-group, .card): border-radius: 12px */
.gr-group, .card, .gradio-container .gr-group, .gradio-container .card {
    border-radius: 12px !important;
}

/* Audio components should not clip download button */
.gr-group .gradio-audio,
.gr-group audio,
.gr-group .component.audio,
.purple-audio,
.purple-audio > div,
.purple-audio > div > div,
.gradio-audio > div,
.gradio-audio > div > div {
    overflow: visible !important;
}

/* All gr-group should allow overflow for audio download button */
.gr-group, .gradio-container .gr-group, .gradio-container form .gr-group,
.gradio-container .form, .gradio-container .container,
.gradio-container .gap, .gradio-container .gradio-row,
.gradio-container .gradio-column {
    overflow: visible !important;
}

/* Audio component container - give top padding for download button */
.purple-audio,
.gradio-audio,
.purple-audio > div,
.gradio-audio > div {
    padding-top: 20px !important;
    padding-right: 20px !important;
    padding-bottom: 15px !important;
    padding-left: 10px !important;
    margin-top: 5px !important;
    overflow: visible !important;
}

/* Increase audio component area - output-panel IDs not defined in Python, removed */
/* All gr-group should allow overflow for audio download button */
.gr-group, .gradio-container .gr-group, .gradio-container form .gr-group {
    overflow: visible !important;
}

/* Audio component inner container - give more vertical space */
.gradio-container .gradio-audio > div,
.gradio-container .component.audio > div {
    padding: 10px 5px !important;
}

/* Pills/capsules keep 9999px (nav-badge, status-badge etc.) */

.primary-btn {
    background: linear-gradient(135deg, #8B5CF6, #6366F1) !important;
    color: var(--text-on-primary) !important;
    font-weight: 700 !important;
    font-size: 15px !important;
    border: none !important;
    border-radius: var(--radius-md) !important;
    box-shadow: 0 4px 16px var(--primary-glow-strong), var(--shadow-md) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    cursor: pointer;
    position: relative;
    overflow: hidden;
    padding: 12px 24px !important;
    letter-spacing: 0.02em;
    margin-top: 8px !important;
    margin-bottom: 8px !important;
}

.primary-btn::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(255,255,255,0.15) 0%, transparent 50%);
    opacity: 0;
    transition: opacity var(--duration-normal) var(--ease-standard);
}

.primary-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 20px var(--primary-glow-strong), var(--shadow-md) !important;
}

.primary-btn:hover::after {
    opacity: 1;
}

.primary-btn:active {
    transform: translateY(0) scale(0.97) !important;
    box-shadow: 0 1px 4px var(--primary-glow) !important;
    transition-duration: 100ms !important;
}

.primary-btn:disabled {
    opacity: 0.5 !important;
    cursor: not-allowed !important;
    transform: none !important;
    box-shadow: none !important;
}

.secondary-btn {
    background: transparent !important;
    color: var(--primary) !important;
    font-weight: 600 !important;
    font-size: var(--text-sm) !important;
    border: 1px solid var(--primary) !important;
    border-radius: var(--radius-md) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    cursor: pointer;
    padding: var(--space-2) var(--space-4) !important;
    letter-spacing: 0.01em;
}

.secondary-btn:hover {
    background: var(--primary-bg) !important;
    border-color: var(--primary-hover) !important;
    color: var(--primary-hover) !important;
}

.secondary-btn:active {
    background: var(--primary-bg) !important;
    transform: translateY(1px);
    transition-duration: 100ms !important;
}

.secondary-btn:disabled {
    opacity: 0.5 !important;
    cursor: not-allowed !important;
    transform: none !important;
}

.stop-btn {
    background: transparent !important;
    color: var(--accent-error) !important;
    border: 1px solid rgba(239, 68, 68, 0.4) !important;
    border-radius: var(--radius-md) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    cursor: pointer;
    padding: var(--space-2) var(--space-4) !important;
    font-size: var(--text-sm) !important;
    font-weight: 600 !important;
}

.stop-btn:hover {
    background: var(--error-bg) !important;
    border-color: var(--accent-error) !important;
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(239,68,68,0.2);
}

.stop-btn:active {
    transform: translateY(0) scale(0.97);
    transition-duration: 100ms !important;
}

/* --- 13. 内层标签页（优化版） --- */
.inner-tabs > .tab-nav {
    background: var(--bg-secondary) !important;
    padding: 8px !important;
    border-radius: var(--radius-lg) !important;
    margin-bottom: var(--space-4) !important;
    gap: var(--space-2) !important;
    border: none !important;
}

.inner-tabs > .tab-nav button {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-2) var(--space-4) !important;
    font-size: var(--text-sm) !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
}

.inner-tabs > .tab-nav button:hover {
    color: var(--text-primary) !important;
    border-color: var(--primary-ring) !important;
    background: var(--primary-bg) !important;
}

.inner-tabs > .tab-nav button.selected {
    background: var(--primary-bg) !important;
    color: var(--primary) !important;
    border-color: var(--primary) !important;
    box-shadow: 0 0 8px var(--primary-glow);
}

/* --- 14. 数据表格（优化版） --- */
.dataframe-container {
    border-radius: var(--radius-lg) !important;
    overflow: hidden;
    border: 1px solid var(--border-subtle) !important;
    box-shadow: var(--shadow-sm);
}

.dataframe-container thead th {
    background: var(--bg-elevated) !important;
    color: var(--text-primary) !important;
    font-weight: 700 !important;
    font-size: var(--text-sm) !important;
    padding: var(--space-3) var(--space-4) !important;
    border-bottom: 1px solid var(--border-medium) !important;
    text-align: left !important;
}

.dataframe-container tbody tr:nth-child(even) {
    background: rgba(30, 30, 56, 0.3);
}

.dataframe-container tbody tr {
    transition: background var(--duration-normal) var(--ease-standard);
}

.dataframe-container tbody tr:hover {
    background: var(--primary-bg) !important;
}

/* --- 15. 分割线和间距（优化版） --- */
.divider {
    height: 1px;
    background: var(--border-subtle);
    margin: var(--space-5) 0;
    border: none;
    position: relative;
}

.divider::after {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    width: 48px;
    height: 1px;
    background: linear-gradient(90deg, var(--primary), transparent);
}

/* --- 16. 状态文本框 --- */
.status-textbox {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-secondary) !important;
    font-size: var(--text-sm) !important;
    padding: var(--space-3) !important;
}

/* --- 17. 音频组件（优化版） --- */
.gradio-audio {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-lg) !important;
    overflow: hidden;
    transition: all var(--duration-normal) var(--ease-standard);
}

.gradio-audio:hover {
    border-color: var(--border-medium);
    box-shadow: var(--shadow-glow);
}

.gradio-audio svg[class*="music"],
.gradio-audio svg[class*="Music"],
.gradio-audio svg[class*="note"],
.gradio-audio svg[class*="Note"],
.gradio-audio svg[class*="audio-icon"],
.gradio-audio svg[class*="AudioIcon"],
.gradio-audio svg[class*="placeholder-icon"],
.gradio-audio svg[class*="PlaceholderIcon"] {
    display: none !important;
}

.gradio-audio audio {
    width: 100% !important;
    border-radius: var(--radius-md);
}

/* --- 18. Prose 文本样式 --- */
.gradio-container .prose p {
    color: var(--text-secondary) !important;
    line-height: var(--leading-relaxed) !important;
}

.gradio-container .prose a {
    color: var(--primary) !important;
    text-decoration: none !important;
    transition: color var(--duration-normal) var(--ease-standard);
}

.gradio-container .prose a:hover {
    text-decoration: underline !important;
    color: var(--primary-light) !important;
}

.gradio-container .prose strong {
    color: var(--text-primary) !important;
    font-weight: 700 !important;
}

/* --- 19. 增强型 Footer（优化版） --- */
.enhanced-footer {
    margin-top: var(--space-12);
    padding: var(--space-8) var(--space-6);
    background: var(--bg-glass);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xl);
    color: var(--text-muted);
    font-size: var(--text-sm) !important;
    box-shadow: var(--shadow-card);
}

.footer-grid {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr 1fr;
    gap: var(--space-8);
    margin-bottom: var(--space-6);
}

.footer-brand {
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    font-size: var(--text-lg) !important;
    margin-bottom: var(--space-3) !important;
}

.footer-title {
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    font-size: var(--text-sm) !important;
    margin-bottom: var(--space-3) !important;
    position: relative;
    padding-bottom: var(--space-2);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.footer-title::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    width: 24px;
    height: 2px;
    background: linear-gradient(90deg, var(--primary), #6366F1);
    border-radius: 2px;
}

.footer-link {
    color: var(--text-muted) !important;
    text-decoration: none !important;
    transition: all var(--duration-normal) var(--ease-standard);
    display: block;
    padding: var(--space-1) 0;
    font-size: var(--text-sm) !important;
}

.footer-link:hover {
    color: var(--primary-light) !important;
    padding-left: var(--space-2);
}

.footer-bottom {
    text-align: center;
    padding-top: var(--space-5);
    border-top: 1px solid var(--border-subtle);
    color: var(--text-muted) !important;
    font-size: var(--text-xs) !important;
    line-height: var(--leading-loose) !important;
}

.footer-bottom a {
    color: var(--primary) !important;
    text-decoration: none !important;
    transition: color var(--duration-normal) var(--ease-standard);
}

.footer-bottom a:hover {
    text-decoration: underline !important;
    color: var(--primary-light) !important;
}

/* --- 20. 响应式设计（优化版） --- */
@media (max-width: 1280px) {
    .footer-grid {
        grid-template-columns: 1fr 1fr;
        gap: var(--space-6);
    }

    .features-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media (max-width: 1024px) {
    .gradio-container {
        padding: var(--space-5) !important;
    }

    .features-grid {
        grid-template-columns: repeat(2, 1fr);
        gap: var(--space-3);
    }

    .hero-banner {
        padding: var(--space-8) var(--space-6);
    }

    .hero-title {
        font-size: var(--text-3xl) !important;
    }

    .enhanced-tabs > .tab-wrap {
        padding: var(--space-5) !important;
    }
}

@media (max-width: 768px) {
    .gradio-container {
        padding: var(--space-4) !important;
    }

    .hero-banner {
        padding: var(--space-6) var(--space-4);
        border-radius: var(--radius-xl);
        margin-bottom: var(--space-5);
    }

    .hero-title {
        font-size: var(--text-2xl) !important;
    }

    .hero-subtitle {
        font-size: var(--text-base) !important;
    }

    .hero-meta {
        gap: var(--space-2);
    }

    .status-badge {
        font-size: 11px !important;
        padding: var(--space-1) var(--space-3);
    }

    .features-grid {
        grid-template-columns: 1fr 1fr !important;
        gap: var(--space-3);
    }

    .feature-card {
        padding: var(--space-4);
    }

    .feature-icon {
        font-size: var(--icon-lg);
    }

    .enhanced-tabs > .tab-nav {
        padding: var(--space-2) var(--space-1) 0 var(--space-1) !important;
        gap: 2px !important;
        overflow-x: auto;
        flex-wrap: nowrap !important;
    }

    .enhanced-tabs > .tab-nav button {
        padding: var(--space-2) var(--space-3) !important;
        font-size: var(--text-xs) !important;
        white-space: nowrap;
        flex-shrink: 0;
    }

    .enhanced-tabs > .tab-wrap {
        padding: var(--space-4) !important;
    }

    .card {
        padding: var(--space-4);
    }

    .footer-grid {
        grid-template-columns: 1fr !important;
        gap: var(--space-5);
    }

    .enhanced-footer {
        padding: var(--space-5) var(--space-4);
        margin-top: var(--space-8);
    }

    .status-bar-container {
        flex-direction: column;
        gap: var(--space-2);
        align-items: flex-start;
    }
}

@media (max-width: 480px) {
    .gradio-container {
        padding: var(--space-3) !important;
    }

    .hero-banner {
        padding: var(--space-5) var(--space-3);
    }

    .hero-title {
        font-size: var(--text-xl) !important;
    }

    .features-grid {
        grid-template-columns: 1fr !important;
    }

    .enhanced-tabs > .tab-nav button {
        padding: var(--space-2) !important;
        font-size: 11px !important;
    }

    .enhanced-tabs > .tab-wrap {
        padding: var(--space-3) !important;
    }

    .card, .output-panel {
        padding: var(--space-3);
    }
}

/* --- 21. 加载动画（优化版） --- */
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.loading-spinner::before {
    content: '';
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid var(--border-medium);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-right: var(--space-2);
}

@keyframes skeleton-pulse {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 0.8; }
}

.skeleton {
    background: linear-gradient(90deg, var(--bg-tertiary) 25%, var(--bg-elevated) 50%, var(--bg-tertiary) 75%);
    background-size: 200% 100%;
    animation: skeleton-pulse 1.5s ease-in-out infinite;
    border-radius: var(--radius-md);
}

/* --- 22. 实用工具类（优化版） --- */
.animate-fade-in {
    animation: fade-in var(--duration-slow) var(--ease-decelerate);
}

@keyframes fade-in {
    from { opacity: 0; }
    to { opacity: 1; }
}

.animate-slide-up {
    animation: slide-up var(--duration-entrance) var(--ease-decelerate);
}

@keyframes slide-up {
    from {
        opacity: 0;
        transform: translateY(16px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.animate-slide-in-left {
    animation: slide-in-left var(--duration-entrance) var(--ease-decelerate);
}

@keyframes slide-in-left {
    from {
        opacity: 0;
        transform: translateX(-16px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

.animate-scale-in {
    animation: scale-in var(--duration-normal) var(--ease-decelerate);
}

@keyframes scale-in {
    from {
        opacity: 0;
        transform: scale(0.96);
    }
    to {
        opacity: 1;
        transform: scale(1);
    }
}

/* --- 23. 选择文本样式 --- */
::selection {
    background: var(--primary-ring);
    color: var(--text-primary);
}

/* --- 24. 链接样式 --- */
a {
    color: var(--primary);
    text-decoration: none;
    transition: color var(--duration-normal) var(--ease-standard);
}

a:hover {
    color: var(--primary-light);
    text-decoration: underline;
}

/* --- 25. Gradio 特定覆盖样式（优化版） --- */
.gradio-container .gap {
    gap: var(--space-4) !important;
}

.gradio-row {
    gap: var(--space-4) !important;
}

.gradio-column {
    gap: var(--space-4) !important;
}

.form-group {
    margin-bottom: var(--space-4);
}

input[type="radio"], input[type="checkbox"] {
    accent-color: var(--primary);
    cursor: pointer;
    width: 16px;
    height: 16px;
}

select {
    cursor: pointer;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394A3B8' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right var(--space-3) center;
    padding-right: var(--space-8) !important;
}

audio {
    border-radius: var(--radius-md);
    background: var(--bg-tertiary);
}

/* --- 26. 弹窗与抽屉动画 --- */
.gradio-container .modal,
.gradio-container [class*="modal"] {
    animation: modal-enter var(--duration-slow) var(--ease-decelerate);
}

@keyframes modal-enter {
    from {
        opacity: 0;
        transform: scale(0.95) translateY(8px);
    }
    to {
        opacity: 1;
        transform: scale(1) translateY(0);
    }
}

/* --- 27. 全局按钮统一样式覆盖 --- */
.gradio-container button:not([class*="btn"]):not(.tab-nav button) {
    border-radius: var(--radius-md) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
}

.gradio-container button:not([class*="btn"]):not(.tab-nav button):hover {
    transform: translateY(-1px);
}

.gradio-container button:not([class*="btn"]):not(.tab-nav button):active {
    transform: translateY(0) scale(0.98);
    transition-duration: 80ms !important;
}

/* --- 28. 微交互增强 --- */
.gradio-container .gradio-dropdown {
    transition: all var(--duration-normal) var(--ease-standard) !important;
}

.gradio-container .gradio-dropdown:focus-within {
    box-shadow: 0 0 0 3px var(--primary-ring) !important;
}

/* 图标尺寸规范 */
.icon-sm { font-size: var(--icon-sm) !important; width: var(--icon-sm); height: var(--icon-sm); }
.icon-md { font-size: var(--icon-md) !important; width: var(--icon-md); height: var(--icon-md); }
.icon-lg { font-size: var(--icon-lg) !important; width: var(--icon-lg); height: var(--icon-lg); }
.icon-xl { font-size: var(--icon-xl) !important; width: var(--icon-xl); height: var(--icon-xl); }

/* --- 29. 无障碍支持 (Accessibility) --- */

/* 焦点可见性增强 - 确保键盘导航用户能清晰看到焦点 */
*:focus-visible {
    outline: 3px solid var(--primary) !important;
    outline-offset: 2px !important;
}

/* 跳过导航链接 */
.skip-nav {
    position: absolute;
    top: -100%;
    left: 50%;
    transform: translateX(-50%);
    padding: var(--space-3) var(--space-5);
    background: var(--primary);
    color: #fff;
    border-radius: var(--radius-md);
    font-weight: 700;
    z-index: 9999;
    transition: top var(--duration-normal) var(--ease-standard);
}

.skip-nav:focus {
    top: var(--space-4);
}

/* 屏幕阅读器专用 */
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border-width: 0;
}

/* 减少动画偏好设置 - 尊重用户的系统设置 */
@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
    }

    .hero-banner::before,
    .hero-banner::after {
        animation: none !important;
    }

    .status-pulse {
        animation: none !important;
        opacity: 0.8;
    }

    .progress-shimmer {
        animation: none !important;
        background: var(--bg-tertiary);
    }

    .loading-spinner::before {
        animation: none !important;
        border-top-color: var(--text-muted);
    }

    .feature-card,
    .card,
    .output-panel {
        animation: none !important;
        opacity: 1;
    }

    .enhanced-tabs > .tab-item {
        animation: none !important;
    }

    .primary-btn,
    .secondary-btn,
    .stop-btn,
    .feature-card,
    .gradio-container button {
        transition: none !important;
    }

    .primary-btn:hover,
    .secondary-btn:hover,
    .stop-btn:hover,
    .feature-card:hover {
        transform: none !important;
    }

    .primary-btn:active,
    .secondary-btn:active,
    .stop-btn:active {
        transform: none !important;
    }
}

/* --- 30. 骨架屏加载动画 --- */
.skeleton-loader {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-4);
}

.skeleton-line {
    height: 16px;
    border-radius: var(--radius-sm);
    background: linear-gradient(
        90deg,
        var(--bg-tertiary) 0%,
        var(--bg-elevated) 40%,
        var(--bg-tertiary) 60%,
        var(--bg-tertiary) 100%
    );
    background-size: 200% 100%;
    animation: skeleton-loading 1.8s ease-in-out infinite;
}

.skeleton-line:nth-child(1) { width: 80%; }
.skeleton-line:nth-child(2) { width: 95%; }
.skeleton-line:nth-child(3) { width: 70%; }
.skeleton-line:nth-child(4) { width: 60%; }
.skeleton-line:nth-child(5) { width: 85%; }

.skeleton-line.short {
    height: 12px;
    width: 40% !important;
}

.skeleton-line.tall {
    height: 24px;
}

@keyframes skeleton-loading {
    0% {
        background-position: 200% 0;
    }
    100% {
        background-position: -200% 0;
    }
}

/* 骨架卡片 */
.skeleton-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: var(--space-6);
    animation: skeleton-pulse 2s ease-in-out infinite;
}

/* 骨架头像 */
.skeleton-avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: linear-gradient(
        90deg,
        var(--bg-tertiary) 0%,
        var(--bg-elevated) 50%,
        var(--bg-tertiary) 100%
    );
    background-size: 200% 100%;
    animation: skeleton-loading 1.8s ease-in-out infinite;
}

/* 骨架按钮 */
.skeleton-button {
    width: 100px;
    height: 36px;
    border-radius: var(--radius-md);
    background: linear-gradient(
        90deg,
        var(--bg-tertiary) 0%,
        var(--bg-elevated) 50%,
        var(--bg-tertiary) 100%
    );
    background-size: 200% 100%;
    animation: skeleton-loading 1.8s ease-in-out infinite;
}

/* 骨架图片 */
.skeleton-image {
    width: 100%;
    height: 200px;
    border-radius: var(--radius-lg);
    background: linear-gradient(
        90deg,
        var(--bg-tertiary) 0%,
        var(--bg-elevated) 50%,
        var(--bg-tertiary) 100%
    );
    background-size: 200% 100%;
    animation: skeleton-loading 1.8s ease-in-out infinite;
}

/* --- 31. Intersection Observer 滚动入场动画 --- */
.animate-on-scroll {
    opacity: 0;
    transform: translateY(20px);
    transition: opacity var(--duration-entrance) var(--ease-decelerate),
                transform var(--duration-entrance) var(--ease-decelerate);
}

.animate-on-scroll.is-visible {
    opacity: 1;
    transform: translateY(0);
}

/* 不同方向的入场动画 */
.animate-on-scroll.from-left {
    transform: translateX(-20px);
}

.animate-on-scroll.from-left.is-visible {
    transform: translateX(0);
}

.animate-on-scroll.from-right {
    transform: translateX(20px);
}

.animate-on-scroll.from-right.is-visible {
    transform: translateX(0);
}

.animate-on-scroll.scale-up {
    transform: scale(0.95);
}

.animate-on-scroll.scale-up.is-visible {
    transform: scale(1);
}

/* 延迟类 - 用于依次入场 */
.animate-on-scroll.delay-1 { transition-delay: 0.05s; }
.animate-on-scroll.delay-2 { transition-delay: 0.1s; }
.animate-on-scroll.delay-3 { transition-delay: 0.15s; }
.animate-on-scroll.delay-4 { transition-delay: 0.2s; }
.animate-on-scroll.delay-5 { transition-delay: 0.25s; }
.animate-on-scroll.delay-6 { transition-delay: 0.3s; }

/* 减少动画偏好下禁用滚动动画 */
@media (prefers-reduced-motion: reduce) {
    .animate-on-scroll {
        opacity: 1;
        transform: none;
        transition: none;
    }
}

/* --- 32. 表单提交状态反馈 --- */
.form-submitting {
    position: relative;
    pointer-events: none;
}

.form-submitting::after {
    content: '';
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.1);
    border-radius: inherit;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* 成功反馈动画 */
@keyframes success-pulse {
    0% {
        box-shadow: 0 0 0 0 var(--accent-success);
    }
    70% {
        box-shadow: 0 0 0 12px rgba(34, 197, 94, 0);
    }
    100% {
        box-shadow: 0 0 0 0 rgba(34, 197, 94, 0);
    }
}

.success-feedback {
    animation: success-pulse 0.8s ease-out;
}

/* 错误反馈动画 */
@keyframes error-shake {
    0%, 100% { transform: translateX(0); }
    10%, 30%, 50%, 70%, 90% { transform: translateX(-4px); }
    20%, 40%, 60%, 80% { transform: translateX(4px); }
}

.error-feedback {
    animation: error-shake 0.5s ease-in-out;
}

/* 表单验证状态 */
.input-valid {
    border-color: var(--accent-success) !important;
    box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.15) !important;
}

.input-invalid {
    border-color: var(--accent-error) !important;
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15) !important;
}

.input-warning {
    border-color: var(--accent-warning) !important;
    box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.15) !important;
}

/* 验证提示消息 */
.validation-message {
    font-size: var(--text-xs);
    margin-top: var(--space-1);
    padding-left: var(--space-2);
    display: flex;
    align-items: center;
    gap: var(--space-1);
}

.validation-message.error {
    color: var(--accent-error);
}

.validation-message.success {
    color: var(--accent-success);
}

.validation-message.warning {
    color: var(--accent-warning);
}

/* --- 33. 视差滚动效果 --- */
.parallax-container {
    overflow: hidden;
    position: relative;
}

.parallax-element {
    will-change: transform;
    transform: translateZ(0);
    transition: transform 0.1s linear;
}

/* --- 34. 锚点平滑滚动 --- */
html {
    scroll-behavior: smooth;
    scroll-padding-top: var(--space-8);
}

/* 锚点目标高亮 */
:target {
    animation: target-highlight 1s ease-out;
}

@keyframes target-highlight {
    0% {
        background-color: var(--primary-bg);
    }
    100% {
        background-color: transparent;
    }
}

/* --- 35. 触摸设备优化 --- */
@media (hover: none) and (pointer: coarse) {
    /* 增大触摸目标 */
    .primary-btn,
    .secondary-btn,
    .stop-btn,
    .feature-card,
    .tab-nav button,
    .inner-tabs > .tab-nav button {
        min-height: 44px;
        min-width: 44px;
        padding: var(--space-3) var(--space-4);
    }

    /* 移除hover效果 */
    .feature-card:hover {
        transform: none;
        box-shadow: var(--shadow-card);
    }

    .primary-btn:hover,
    .secondary-btn:hover,
    .stop-btn:hover {
        transform: none;
    }

    /* 优化滚动条 */
    ::-webkit-scrollbar {
        width: 0;
        height: 0;
    }

    /* 增大下拉箭头点击区域 */
    select {
        padding: var(--space-3) var(--space-10) var(--space-3) var(--space-4) !important;
    }
}

/* --- 36. 浏览器兼容性增强 --- */

/* Webkit 内核浏览器 */
@supports (-webkit-backdrop-filter: blur(10px)) {
    .card,
    .output-panel,
    .status-bar-container,
    .hero-banner {
        -webkit-backdrop-filter: blur(var(--blur-sm));
    }
}

/* Firefox 兼容性 */
@-moz-document url-prefix() {
    .card,
    .output-panel,
    .status-bar-container {
        background-color: var(--bg-secondary);
    }
}

/* Safari 特殊处理 */
@supports (font: -apple-system-body) {
    body {
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
    }
}

/* --- 37. 深色/浅色模式支持 --- */
/* 当前为深色模式默认，添加浅色模式切换支持 */
@media (prefers-color-scheme: light) {
    :root {
        --bg-primary: #F8FAFC;
        --bg-secondary: #FFFFFF;
        --bg-tertiary: #F1F5F9;
        --bg-elevated: #E2E8F0;
        --bg-input: #FFFFFF;
        --bg-input-focus: #F8FAFC;
        --bg-glass: rgba(255, 255, 255, 0.8);
        --bg-glass-light: rgba(248, 250, 252, 0.9);
        --text-primary: #0F172A;
        --text-secondary: #475569;
        --text-muted: #64748B;
        --text-disabled: #94A3B8;
        --border-subtle: rgba(0, 0, 0, 0.06);
        --border-medium: rgba(0, 0, 0, 0.12);
        --primary-glow: rgba(139, 92, 246, 0.2);
        --primary-glow-strong: rgba(139, 92, 246, 0.3);
        --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
        --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.08);
        --shadow-card: 0 4px 16px rgba(0, 0, 0, 0.08);
        --shadow-elevated: 0 8px 32px rgba(0, 0, 0, 0.1);
    }
}

/* ============================================
   新增UI增强模块
   ============================================ */

/* --- 39. 设置分组 --- */
.setting-group {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: var(--space-5);
    margin-bottom: var(--space-4);
    background: var(--bg-glass);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
}

.setting-group-title {
    font-size: var(--text-sm) !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    margin: 0 0 var(--space-3) 0 !important;
    display: flex;
    align-items: center;
    gap: var(--space-2);
}

.help-text {
    font-size: 12px;
    color: var(--text-muted) !important;
    line-height: 1.5;
    margin-top: var(--space-1);
}

/* --- 40. 键盘快捷键徽章 --- */
.kbd {
    display: inline-block;
    background: linear-gradient(180deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.04) 100%);
    border: 1px solid rgba(255,255,255,0.2);
    border-bottom-width: 2px;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    color: var(--text-secondary);
    font-family: var(--font-mono);
    margin-left: var(--space-2);
    vertical-align: middle;
    line-height: 1.6;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2);
}

/* --- 41. 按钮禁用状态增强 --- */
.gradio-container button:disabled {
    opacity: 0.5 !important;
    cursor: not-allowed !important;
    transform: none !important;
    filter: grayscale(50%) !important;
}

/* --- 42. 字数计数器 --- */
.char-counter {
    position: absolute;
    bottom: 8px;
    right: 12px;
    font-size: 12px;
    color: var(--text-muted);
    pointer-events: none;
    z-index: 10;
    background: var(--bg-tertiary);
    padding: 2px 8px;
    border-radius: var(--radius-sm);
    line-height: 1.4;
    white-space: nowrap;
}

.char-counter.warn {
    color: var(--accent-warning);
}

.char-counter.error {
    color: var(--accent-error);
}

/* 输入框底部留白 - 防止字数计数器与下方内容重叠 */
.gradio-container textarea {
    padding-bottom: 28px !important;
}

/* --- 43. 输入框抖动动画 --- */
@keyframes input-shake {
    0%, 100% { transform: translateX(0); }
    10%, 30%, 50%, 70%, 90% { transform: translateX(-4px); }
    20%, 40%, 60%, 80% { transform: translateX(4px); }
}

.input-shake {
    animation: input-shake 400ms ease-in-out;
    border-color: var(--accent-error) !important;
}

/* --- 44. 空状态页面 --- */
.empty-state {
    text-align: center;
    padding: 48px 24px;
    color: var(--text-muted);
}

.empty-state-icon {
    font-size: 48px;
    margin-bottom: 16px;
    display: block;
    opacity: 0.6;
}

.empty-state-text {
    font-size: 16px;
    margin-bottom: 12px;
    color: var(--text-secondary) !important;
}

.empty-state-action {
    margin-top: 16px;
}

.empty-state-action button {
    cursor: pointer;
}

/* --- 45. Toast 通知系统 --- */
.toast-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.toast {
    padding: 12px 20px;
    border-radius: 8px;
    color: #fff;
    font-size: 14px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    animation: toast-in 200ms ease-out;
    display: flex;
    align-items: center;
    gap: 8px;
    max-width: 400px;
    line-height: 1.5;
}

.toast-success {
    background: linear-gradient(135deg, #7C3AED, #8B5CF6);
}

.toast-error {
    background: linear-gradient(135deg, #DC2626, #EF4444);
}

.toast-info {
    background: linear-gradient(135deg, #2563EB, #3B82F6);
}

.toast-close {
    cursor: pointer;
    opacity: 0.7;
    margin-left: auto;
    font-size: 18px;
    line-height: 1;
}

.toast-close:hover {
    opacity: 1;
}

@keyframes toast-in {
    from { opacity: 0; transform: translateX(20px); }
    to { opacity: 1; transform: translateX(0); }
}

@keyframes toast-out {
    from { opacity: 1; transform: translateX(0); }
    to { opacity: 0; transform: translateX(20px); }
}

/* --- 45.1 紫色面板文字对比度修复 --- */
/* Target labels in purple audio panels to be white */
.purple-audio label,
.purple-audio span[style*="color"],
.gr-group[style*="background: rgb(139"] label,
.gr-group[style*="background:#8B5CF6"] label,
.gr-group[style*="background: #8B5CF6"] label {
    color: #FFFFFF !important;
    text-shadow: 0 1px 2px rgba(0,0,0,0.3) !important;
}

/* Audio player container fix - ensure player is always visible */
.purple-audio .gradio-audio,
.purple-audio audio,
.purple-audio .component,
.purple-audio .audio-player,
.purple-audio [data-testid="audio"],
.purple-audio .wrap {
    min-height: 60px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    background: transparent !important;
}

/* Ensure audio element is visible in Gradio 4.x */
.purple-audio audio {
    display: block !important;
    width: 100% !important;
    min-height: 50px !important;
    background: rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
}

/* Fix for Gradio 4.x audio player not showing controls */
.gradio-container .wrap.svelte-s1rpyyt,
.gradio-container .player.svelte-1b4m56,
.gradio-container audio,
.gradio-container .audio-player,
.gradio-container .component.audio {
    width: 100% !important;
    min-height: 50px !important;
}

/* Status textbox in purple panels */
.purple-audio ~ .status-textbox,
.purple-audio + div .status-textbox textarea,
.purple-audio + div textarea {
    color: #FFFFFF !important;
}

/* Char-counter text in purple panels */
.purple-audio ~ div .char-counter,
.gr-group[style*="background: rgb(139"] .char-counter,
.gr-group[style*="background:#8B5CF6"] .char-counter {
    color: #E0E0FF !important;
}

/* Audio label "每200字自动分段合成" counter */
.char-counter {
    color: var(--text-muted);
}
/* Override for purple context - will be handled by JS fixAudioPanel */

/* --- 45.2 引擎切换警告弱化 --- */
.engine-warning {
    font-size: 12px !important;
    color: rgba(245, 158, 11, 0.6) !important;
    margin-top: -4px !important;
    margin-bottom: 8px !important;
    padding-left: 4px !important;
    font-style: italic;
}

/* --- 45.3 声音描述预设标签 --- */
.voice-preset-tags {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 6px !important;
    margin-top: 4px !important;
    margin-bottom: 8px !important;
    padding: 4px 0 !important;
}

.preset-tag {
    display: inline-flex !important;
    align-items: center !important;
    padding: 3px 10px !important;
    border-radius: 20px !important;
    background: var(--primary-bg) !important;
    border: 1px solid rgba(139, 92, 246, 0.2) !important;
    color: var(--primary-light) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    user-select: none !important;
}

.preset-tag:hover {
    background: var(--primary) !important;
    color: #FFFFFF !important;
    border-color: var(--primary) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 2px 8px var(--primary-glow) !important;
}

.preset-tag:active {
    transform: translateY(0) scale(0.95) !important;
}

.preset-tag-active {
    background: var(--primary) !important;
    color: #fff !important;
    border-color: var(--primary) !important;
    transform: scale(0.95) !important;
}

.engine-btn-state {
    display: none !important;
    height: 0 !important;
    overflow: hidden !important;
}

/* --- 46. 音频播放增强 --- */
audio::-webkit-media-controls-panel {
    background: var(--bg-tertiary) !important;
    border-radius: var(--radius-md) !important;
}

.gradio-audio audio::-webkit-media-controls-current-time-display,
.gradio-audio audio::-webkit-media-controls-time-remaining-display {
    color: var(--text-primary) !important;
    font-size: 12px !important;
}

.audio-playlist {
    background: var(--bg-tertiary);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    overflow: hidden;
    margin-top: var(--space-3);
}

.playlist-item {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--border-subtle);
    transition: background var(--duration-fast) var(--ease-standard);
}

.playlist-item:last-child {
    border-bottom: none;
}

.playlist-item:hover {
    background: var(--primary-bg);
}

.playlist-item-name {
    flex: 1;
    font-size: var(--text-sm);
    color: var(--text-primary);
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.playlist-item-meta {
    font-size: var(--text-xs);
    color: var(--text-muted);
}

.playlist-item-delete {
    cursor: pointer;
    color: var(--accent-error);
    opacity: 0.6;
    transition: opacity var(--duration-fast) var(--ease-standard);
    background: none;
    border: none;
    padding: 4px 8px;
    font-size: 14px;
}

.playlist-item-delete:hover {
    opacity: 1;
}

/* --- 47. 进度指示器增强 --- */
.progress-segment-indicator {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-sm);
    color: var(--text-secondary);
}

.progress-segment-indicator .segment-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--primary);
    animation: pulse-dot 1.5s ease-in-out infinite;
}

.progress-segment-indicator .segment-dot.done {
    background: var(--accent-success);
    animation: none;
}

/* --- 48. 按钮组快捷键提示 --- */
.btn-with-shortcut {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-1);
}

/* --- 49. Gradio 间距一致性覆盖 --- */
.gradio-container .form {
    gap: var(--space-4) !important;
}

.gradio-container .gap {
    gap: var(--space-4) !important;
}

/* textarea 容器相对定位，用于放置计数器 */
.gradio-container .wrap[data-testid="textbox"] {
    position: relative !important;
}

/* --- 50. 打印样式 --- */
@media print {
    .hero-banner,
    .features-grid,
    .status-bar-container,
    .enhanced-footer,
    button,
    .tab-nav,
    .toast-container {
        display: none !important;
    }

    body {
        background: white !important;
        color: black !important;
        font-size: 12pt !important;
    }

    .card,
    .output-panel {
        box-shadow: none !important;
        border: 1px solid #ccc !important;
        break-inside: avoid;
    }
}

/* --- 51. 官方精品卡片网格 --- */
.speaker-card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 12px;
    padding: 8px 0;
}

.speaker-card {
    background: var(--bg-tertiary);
    border: 2px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 16px;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.speaker-card:hover {
    border-color: var(--primary);
    background: var(--primary-bg);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px var(--primary-glow);
}

.speaker-card.selected {
    border-color: var(--primary);
    background: linear-gradient(135deg, var(--primary-bg), rgba(139, 92, 246, 0.15));
    box-shadow: 0 0 0 2px var(--primary);
}

.speaker-card-name {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-primary);
    margin: 0;
}

.speaker-card-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}

.speaker-card-tag {
    display: inline-block;
    padding: 2px 8px;
    background: rgba(139, 92, 246, 0.12);
    border-radius: 12px;
    font-size: 11px;
    color: var(--primary-light);
    font-weight: 500;
}

.speaker-card-actions {
    display: flex;
    gap: 8px;
    margin-top: auto;
}

.speaker-card-btn {
    flex: 1;
    padding: 6px 12px;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
    background: var(--bg-secondary);
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
    text-align: center;
}

.speaker-card-btn:hover {
    background: var(--primary);
    color: #fff;
    border-color: var(--primary);
}

.speaker-card-btn.btn-use {
    background: var(--primary);
    color: #fff;
    border-color: var(--primary);
}

.speaker-card-btn.btn-use:hover {
    background: var(--primary-dark);
}

/* 音色筛选栏 */
.filter-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    padding: 12px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-lg);
    margin-bottom: 12px;
}

.filter-bar-label {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-muted);
    margin-right: 4px;
}

.filter-chip {
    padding: 4px 12px;
    border-radius: 20px;
    border: 1px solid var(--border-subtle);
    background: var(--bg-secondary);
    color: var(--text-secondary);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s ease;
}

.filter-chip:hover {
    border-color: var(--primary);
    color: var(--primary-light);
}

.filter-chip.active {
    background: var(--primary);
    color: #fff;
    border-color: var(--primary);
}

/* 音色详情面板 */
.speaker-detail-panel {
    background: linear-gradient(135deg, var(--bg-tertiary), var(--bg-secondary));
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 20px;
    margin-top: 12px;
}

.speaker-detail-panel h3 {
    margin: 0 0 12px 0;
    font-size: var(--text-xl);
    color: var(--text-primary);
}

.speaker-detail-panel .detail-row {
    display: flex;
    gap: 12px;
    margin-bottom: 8px;
    font-size: var(--text-sm);
}

.speaker-detail-panel .detail-label {
    color: var(--text-muted);
    font-weight: 600;
    min-width: 80px;
}

.speaker-detail-panel .detail-value {
    color: var(--text-primary);
}

/* --- 52. 剧本角色颜色编码 --- */
.role-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 12px;
    margin-right: 4px;
}

.role-tag[data-role="御姐"] { background: rgba(236, 72, 153, 0.2); color: #F472B6; border: 1px solid rgba(236, 72, 153, 0.3); }
.role-tag[data-role="旁白"] { background: rgba(107, 114, 128, 0.2); color: #9CA3AF; border: 1px solid rgba(107, 114, 128, 0.3); }
.role-tag[data-role="萝莉"] { background: rgba(244, 114, 182, 0.2); color: #F9A8D4; border: 1px solid rgba(244, 114, 182, 0.3); }
.role-tag[data-role="少年"] { background: rgba(59, 130, 246, 0.2); color: #60A5FA; border: 1px solid rgba(59, 130, 246, 0.3); }
.role-tag[data-role="大叔"] { background: rgba(139, 92, 246, 0.2); color: #A78BFA; border: 1px solid rgba(139, 92, 246, 0.3); }
.role-tag[data-role="正太"] { background: rgba(34, 197, 94, 0.2); color: #4ADE80; border: 1px solid rgba(34, 197, 94, 0.3); }
.role-tag[data-role="女王"] { background: rgba(239, 68, 68, 0.2); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.3); }
.role-tag[data-role="暖男"] { background: rgba(251, 146, 60, 0.2); color: #FB923C; border: 1px solid rgba(251, 146, 60, 0.3); }

.script-line {
    padding: 6px 12px;
    border-radius: var(--radius-md);
    margin: 2px 0;
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    border-left: 3px solid transparent;
}

.script-line[data-role-color="pink"] { background: rgba(236, 72, 153, 0.05); border-left-color: #EC4899; }
.script-line[data-role-color="gray"] { background: rgba(107, 114, 128, 0.05); border-left-color: #6B7280; }
.script-line[data-role-color="blue"] { background: rgba(59, 130, 246, 0.05); border-left-color: #3B82F6; }
.script-line[data-role-color="purple"] { background: rgba(139, 92, 246, 0.05); border-left-color: #8B5CF6; }
.script-line[data-role-color="green"] { background: rgba(34, 197, 94, 0.05); border-left-color: #22C55E; }
.script-line[data-role-color="red"] { background: rgba(239, 68, 68, 0.05); border-left-color: #EF4444; }
.script-line[data-role-color="orange"] { background: rgba(251, 146, 60, 0.05); border-left-color: #FB923C; }

/* --- 53. 音色库视图切换 --- */
.view-toggle {
    display: flex;
    gap: 4px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
    padding: 3px;
}

.view-toggle-btn {
    padding: 6px 12px;
    border-radius: var(--radius-sm);
    border: none;
    background: transparent;
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
}

.view-toggle-btn.active {
    background: var(--primary);
    color: #fff;
}

.view-toggle-btn:hover:not(.active) {
    color: var(--text-primary);
    background: var(--bg-secondary);
}

/* 音色库卡片视图 */
.voice-card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
    padding: 8px 0;
}

.voice-card {
    background: var(--bg-tertiary);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 16px;
    transition: all 0.2s ease;
}

.voice-card:hover {
    border-color: var(--primary);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px var(--primary-glow);
}

.voice-card-name {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-primary);
    margin: 0 0 8px 0;
}

.voice-card-meta {
    font-size: var(--text-xs);
    color: var(--text-muted);
    margin-bottom: 8px;
}

.voice-card-actions {
    display: flex;
    gap: 8px;
}

/* 音色数量统计 */
.stat-card {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 20px;
    background: linear-gradient(135deg, var(--primary-bg), rgba(139, 92, 246, 0.1));
    border-radius: var(--radius-lg);
    margin-bottom: 16px;
}

.stat-card-icon {
    font-size: 32px;
    line-height: 1;
}

.stat-card-value {
    font-size: 28px;
    font-weight: 800;
    color: var(--primary-light);
    line-height: 1;
}

.stat-card-label {
    font-size: var(--text-sm);
    color: var(--text-muted);
    font-weight: 500;
}

/* --- 54. 历史记录增强 --- */
.history-filters {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-bottom: 12px;
}

.time-filter-chip {
    padding: 4px 12px;
    border-radius: 20px;
    border: 1px solid var(--border-subtle);
    background: var(--bg-secondary);
    color: var(--text-secondary);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s ease;
}

.time-filter-chip:hover {
    border-color: var(--primary);
    color: var(--primary-light);
}

.time-filter-chip.active {
    background: var(--primary);
    color: #fff;
    border-color: var(--primary);
}

.history-record-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-subtle);
    transition: background 0.15s ease;
}

.history-record-row:hover {
    background: var(--primary-bg);
}

.history-record-row:nth-child(even) {
    background: rgba(0, 0, 0, 0.02);
}

.history-record-row:nth-child(even):hover {
    background: var(--primary-bg);
}

.history-duration {
    font-size: var(--text-xs);
    color: var(--text-muted);
    font-weight: 500;
    font-family: var(--font-mono);
}

.history-mini-play {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 1px solid var(--border-subtle);
    background: var(--bg-secondary);
    color: var(--text-muted);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 10px;
    transition: all 0.15s ease;
}

.history-mini-play:hover {
    background: var(--primary);
    color: #fff;
    border-color: var(--primary);
}

.history-batch-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
    margin-top: 8px;
}

.history-checkbox {
    width: 16px;
    height: 16px;
    cursor: pointer;
}

/* --- 55. VoxCPM2 引擎标识 --- */
.engine-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}

.engine-badge.qwen3tts {
    background: rgba(139, 92, 246, 0.15);
    color: var(--primary-light);
    border: 1px solid rgba(139, 92, 246, 0.3);
}

.engine-badge.voxcpm2 {
    background: rgba(16, 185, 129, 0.15);
    color: #34D399;
    border: 1px solid rgba(16, 185, 129, 0.3);
}

/* VoxCPM2 可视化控件 */
.voxcpm2-knob {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
}

.voxcpm2-knob-label {
    font-size: var(--text-xs);
    color: var(--text-muted);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.voxcpm2-knob-value {
    font-size: var(--text-lg);
    font-weight: 800;
    color: var(--primary-light);
    font-family: var(--font-mono);
}

/* VoxCPM2 参数面板 */
.voxcpm2-params-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 16px;
    padding: 12px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-lg);
}

/* --- 56. 统一子标签样式 --- */
.sub-tab-nav {
    display: flex;
    gap: 0;
    border-bottom: 2px solid var(--border-subtle);
    margin-bottom: 16px;
}

.sub-tab-btn {
    padding: 8px 16px;
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-muted);
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    cursor: pointer;
    transition: all 0.2s ease;
}

.sub-tab-btn:hover {
    color: var(--text-primary);
}

.sub-tab-btn.active {
    color: var(--primary-light);
    border-bottom-color: var(--primary);
}

/* 引擎选择器统一样式 */
.engine-selector-inline {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
    margin-bottom: 12px;
}

.engine-selector-inline .engine-label {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-muted);
}

.engine-selector-inline .engine-options {
    display: flex;
    gap: 4px;
}

.engine-option-btn {
    padding: 4px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: var(--bg-secondary);
    color: var(--text-secondary);
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
}

.engine-option-btn:hover {
    border-color: var(--primary);
    color: var(--primary-light);
}

.engine-option-btn.active {
    background: var(--primary);
    color: #fff;
    border-color: var(--primary);
}

/* ========================================== */
/* 页面布局全面优化 */
/* ========================================== */

/* --- 1. 顶部引擎选择区域优化 --- */
#engine-selector-row {
    margin-bottom: var(--space-5) !important;
    gap: var(--space-4) !important;
}

#engine-selector-row > div {
    gap: var(--space-3) !important;
}

#engine-selector-row .gradio-column:first-child {
    background: var(--bg-glass) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-lg) !important;
    padding: var(--space-5) !important;
    box-shadow: var(--shadow-sm) !important;
}

#engine-selector-row .gradio-column:last-child {
    background: var(--bg-glass) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-lg) !important;
    padding: var(--space-5) !important;
    box-shadow: var(--shadow-sm) !important;
}

#engine-radio {
    margin-bottom: var(--space-3) !important;
}

#engine-radio label {
    font-size: var(--text-sm) !important;
    font-weight: 600 !important;
    color: var(--text-secondary) !important;
    margin-bottom: var(--space-2) !important;
}

#engine-radio .wrap {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: var(--space-2) !important;
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
}

#engine-radio .wrap .radio {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-2) var(--space-4) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    flex: 1 !important;
    min-width: 120px !important;
    text-align: center !important;
}

#engine-radio .wrap .radio:hover {
    border-color: var(--primary) !important;
    background: var(--primary-bg) !important;
}

#engine-radio .wrap .radio:has(input:checked) {
    background: var(--primary-bg) !important;
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 2px var(--primary-ring) !important;
}

#engine-radio input[type="radio"] {
    display: none !important;
}

#engine-radio .wrap .radio label span {
    font-size: var(--text-sm) !important;
    font-weight: 500 !important;
    color: var(--text-primary) !important;
}

.engine-warning {
    background: var(--warning-bg) !important;
    border: 1px solid var(--warning-border) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-2) var(--space-3) !important;
    font-size: var(--text-xs) !important;
    color: var(--warning-text) !important;
    display: flex !important;
    align-items: center !important;
    gap: var(--space-2) !important;
}

.engine-warning::before {
    content: '⚠️' !important;
    font-size: 14px !important;
}

#engine-status-textbox {
    background: var(--bg-primary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-3) !important;
    text-align: center !important;
    font-size: var(--text-sm) !important;
    font-weight: 500 !important;
    color: var(--text-primary) !important;
}

#engine-status-textbox label {
    font-size: var(--text-xs) !important;
    color: var(--text-muted) !important;
    margin-bottom: var(--space-1) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}

#engine-status-textbox textarea {
    background: transparent !important;
    border: none !important;
    text-align: center !important;
    font-weight: 600 !important;
    color: var(--primary) !important;
}

/* --- 2. 标签页导航优化 --- */
.enhanced-tabs > .tab-nav {
    background: var(--bg-glass) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-lg) var(--radius-lg) 0 0 !important;
    padding: var(--space-3) var(--space-4) !important;
    margin-bottom: 0 !important;
    gap: var(--space-2) !important;
    overflow-x: auto !important;
    flex-wrap: nowrap !important;
    box-shadow: var(--shadow-sm) !important;
}

.enhanced-tabs > .tab-nav::-webkit-scrollbar {
    height: 4px !important;
}

.enhanced-tabs > .tab-nav::-webkit-scrollbar-track {
    background: transparent !important;
}

.enhanced-tabs > .tab-nav::-webkit-scrollbar-thumb {
    background: var(--border-medium) !important;
    border-radius: 2px !important;
}

.enhanced-tabs > .tab-nav button {
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-2) var(--space-4) !important;
    font-size: var(--text-sm) !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    white-space: nowrap !important;
    flex-shrink: 0 !important;
    position: relative !important;
}

.enhanced-tabs > .tab-nav button:hover {
    background: var(--primary-bg) !important;
    border-color: var(--primary-ring) !important;
    color: var(--primary) !important;
}

.enhanced-tabs > .tab-nav button.selected {
    background: var(--primary) !important;
    color: #ffffff !important;
    border-color: var(--primary) !important;
    box-shadow: 0 2px 8px var(--primary-glow) !important;
}

.enhanced-tabs > .tab-nav button.selected::after {
    display: none !important;
}

.enhanced-tabs > .tab-wrap {
    background: var(--bg-primary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 0 0 var(--radius-lg) var(--radius-lg) !important;
    border-top: none !important;
    padding: var(--space-5) !important;
    box-shadow: var(--shadow-sm) !important;
}

/* --- 3. 双栏布局优化 --- */
.enhanced-tabs > .tab-wrap > .tabitem > .gap {
    gap: var(--space-5) !important;
}

.enhanced-tabs > .tab-wrap > .tabitem > .gap > .row {
    gap: var(--space-5) !important;
}

.enhanced-tabs > .tab-wrap > .tabitem > .gap > .row > .column {
    gap: var(--space-4) !important;
}

/* --- 4. 卡片组件优化 --- */
.card {
    margin-bottom: var(--space-4) !important;
    position: relative !important;
    overflow: hidden !important;
}

.card::before {
    content: '' !important;
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    width: 100% !important;
    height: 3px !important;
    background: linear-gradient(90deg, var(--primary), var(--primary-light)) !important;
    opacity: 0 !important;
    transition: opacity var(--duration-normal) var(--ease-standard) !important;
}

.card:hover::before {
    opacity: 1 !important;
}

.card-header {
    margin-bottom: var(--space-4) !important;
    padding-bottom: var(--space-3) !important;
    border-bottom: 1px solid var(--border-subtle) !important;
    display: flex !important;
    align-items: center !important;
    gap: var(--space-2) !important;
}

.card-header-icon {
    font-size: var(--icon-md) !important;
    line-height: 1 !important;
}

.card-header-title {
    font-size: var(--text-lg) !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    margin: 0 !important;
    line-height: 1.2 !important;
}

/* --- 5. 音频播放器优化 --- */
.purple-audio {
    background: var(--bg-glass) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-lg) !important;
    padding: var(--space-4) !important;
    box-shadow: var(--shadow-sm) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    position: relative !important;
    overflow: visible !important;
}

.purple-audio:hover {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 1px var(--primary-ring), var(--shadow-md) !important;
}

.purple-audio audio {
    width: 100% !important;
    border-radius: var(--radius-md) !important;
    background: var(--bg-tertiary) !important;
    outline: none !important;
    display: block !important;
}

.purple-audio audio::-webkit-media-controls-panel {
    background: var(--bg-tertiary) !important;
    border-radius: var(--radius-md) !important;
    display: flex !important;
    align-items: center !important;
    padding: 4px !important;
}

.purple-audio audio::-webkit-media-controls-play-button,
.purple-audio audio::-webkit-media-controls-mute-button,
.purple-audio audio::-webkit-media-controls-volume-slider,
.purple-audio audio::-webkit-media-controls-volume-slider-container,
.purple-audio audio::-webkit-media-controls-timeline,
.purple-audio audio::-webkit-media-controls-current-time-display,
.purple-audio audio::-webkit-media-controls-time-remaining-display,
.purple-audio audio::-webkit-media-controls-playback-rate-button,
.purple-audio audio::-webkit-media-controls-seek-back-button,
.purple-audio audio::-webkit-media-controls-seek-forward-button {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
}

.purple-audio audio::-webkit-media-controls-current-time-display,
.purple-audio audio::-webkit-media-controls-time-remaining-display {
    color: var(--text-primary) !important;
    font-weight: 500 !important;
}

.purple-audio label {
    font-size: var(--text-sm) !important;
    font-weight: 600 !important;
    color: var(--text-secondary) !important;
    margin-bottom: var(--space-2) !important;
}

.purple-audio > div > div {
    overflow: visible !important;
}

/* --- 6. 输入表单优化 --- */
.card > .gradio-textbox,
.card > .gradio-dropdown,
.card > .gradio-radio,
.card > .gradio-tabs {
    margin-bottom: var(--space-4) !important;
}

.gradio-textbox label,
.gradio-dropdown label,
.gradio-radio label {
    font-size: var(--text-sm) !important;
    font-weight: 600 !important;
    color: var(--text-secondary) !important;
    margin-bottom: var(--space-2) !important;
    display: block !important;
}

.gradio-textbox textarea,
.gradio-textbox input,
.gradio-dropdown select {
    background: var(--bg-input) !important;
    border: 1px solid var(--border-medium) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-3) var(--space-4) !important;
    font-size: var(--text-base) !important;
    color: var(--text-primary) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    width: 100% !important;
}

.gradio-textbox textarea:hover,
.gradio-dropdown select:hover {
    border-color: var(--border-focus) !important;
    background: var(--bg-input-focus) !important;
}

.gradio-textbox textarea:focus,
.gradio-dropdown select:focus {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px var(--primary-ring) !important;
    outline: none !important;
}

/* --- 7. 内部标签页优化 --- */
.inner-tabs > .tab-nav {
    background: var(--bg-tertiary) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-1) !important;
    margin-bottom: var(--space-4) !important;
    gap: var(--space-1) !important;
    border: 1px solid var(--border-subtle) !important;
}

.inner-tabs > .tab-nav button {
    background: transparent !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    padding: var(--space-2) var(--space-3) !important;
    font-size: var(--text-sm) !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
}

.inner-tabs > .tab-nav button:hover {
    background: var(--bg-elevated) !important;
    color: var(--text-primary) !important;
}

.inner-tabs > .tab-nav button.selected {
    background: var(--bg-secondary) !important;
    color: var(--primary) !important;
    box-shadow: var(--shadow-sm) !important;
}

.inner-tabs > .tab-wrap {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    padding: var(--space-2) 0 !important;
    margin-top: 0 !important;
}

/* --- 8. 状态文本框优化 --- */
.status-textbox {
    background: var(--bg-glass) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-3) !important;
    margin-top: var(--space-3) !important;
}

.status-textbox label {
    font-size: var(--text-xs) !important;
    color: var(--text-muted) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    margin-bottom: var(--space-1) !important;
}

.status-textbox textarea {
    background: transparent !important;
    border: none !important;
    font-size: var(--text-sm) !important;
    color: var(--text-primary) !important;
    font-weight: 500 !important;
}

/* --- 9. 按钮优化 --- */
.primary-btn {
    position: relative !important;
    overflow: hidden !important;
}

.primary-btn::before {
    content: '' !important;
    position: absolute !important;
    top: 0 !important;
    left: -100% !important;
    width: 100% !important;
    height: 100% !important;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent) !important;
    transition: left 0.5s ease !important;
}

.primary-btn:hover::before {
    left: 100% !important;
}

.secondary-btn {
    position: relative !important;
    overflow: hidden !important;
}

.secondary-btn::before {
    content: '' !important;
    position: absolute !important;
    inset: 0 !important;
    background: var(--primary-bg) !important;
    opacity: 0 !important;
    transition: opacity var(--duration-normal) var(--ease-standard) !important;
    border-radius: inherit !important;
}

.secondary-btn:hover::before {
    opacity: 1 !important;
}

.secondary-btn span {
    position: relative !important;
    z-index: 1 !important;
}

/* --- 10. 分隔线优化 --- */
.divider {
    margin: var(--space-5) 0 !important;
    border: none !important;
    height: 1px !important;
    background: var(--border-subtle) !important;
    position: relative !important;
}

.divider::after {
    content: '' !important;
    position: absolute !important;
    left: 0 !important;
    top: 0 !important;
    width: 60px !important;
    height: 1px !important;
    background: linear-gradient(90deg, var(--primary), transparent) !important;
}

/* --- 11. 语音预设标签优化 --- */
.voice-preset-tags {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: var(--space-2) !important;
    margin: var(--space-3) 0 !important;
    padding: var(--space-2) !important;
    background: var(--bg-tertiary) !important;
    border-radius: var(--radius-md) !important;
    border: 1px solid var(--border-subtle) !important;
}

.preset-tag {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-sm) !important;
    padding: var(--space-1) var(--space-3) !important;
    font-size: var(--text-xs) !important;
    font-weight: 600 !important;
    color: var(--text-secondary) !important;
    cursor: pointer !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    white-space: nowrap !important;
}

.preset-tag:hover {
    background: var(--primary-bg) !important;
    border-color: var(--primary) !important;
    color: var(--primary) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 2px 4px rgba(139, 92, 246, 0.15) !important;
}

.preset-tag:active {
    transform: translateY(0) !important;
}

/* --- 12. 快捷键提示优化 --- */
.kbd {
    display: inline-block !important;
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-medium) !important;
    border-radius: var(--radius-sm) !important;
    padding: 2px 8px !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    font-family: monospace !important;
    letter-spacing: 0.05em !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important;
}

/* --- 13. 筛选栏优化 --- */
.filter-bar {
    display: flex !important;
    align-items: center !important;
    gap: var(--space-2) !important;
    padding: var(--space-2) var(--space-3) !important;
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    margin: var(--space-3) 0 !important;
    flex-wrap: wrap !important;
}

.filter-bar-label {
    font-size: var(--text-sm) !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    margin-right: var(--space-1) !important;
}

.filter-chip {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-sm) !important;
    padding: var(--space-1) var(--space-3) !important;
    font-size: var(--text-xs) !important;
    font-weight: 600 !important;
    color: var(--text-secondary) !important;
    cursor: pointer !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    white-space: nowrap !important;
}

.filter-chip:hover {
    background: var(--primary-bg) !important;
    border-color: var(--primary-ring) !important;
    color: var(--primary) !important;
}

.filter-chip.active {
    background: var(--primary) !important;
    border-color: var(--primary) !important;
    color: #ffffff !important;
    box-shadow: 0 1px 4px var(--primary-glow) !important;
}

/* --- 14. 音色详情面板优化 --- */
.speaker-detail-panel {
    background: var(--bg-glass) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-lg) !important;
    padding: var(--space-5) !important;
    margin: var(--space-4) 0 !important;
    box-shadow: var(--shadow-sm) !important;
}

.speaker-detail-panel h3 {
    font-size: var(--text-lg) !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    margin: 0 0 var(--space-4) 0 !important;
    padding-bottom: var(--space-3) !important;
    border-bottom: 1px solid var(--border-subtle) !important;
}

.detail-row {
    display: flex !important;
    padding: var(--space-2) 0 !important;
    border-bottom: 1px solid var(--border-subtle) !important;
}

.detail-row:last-child {
    border-bottom: none !important;
}

.detail-label {
    width: 100px !important;
    flex-shrink: 0 !important;
    font-size: var(--text-sm) !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
}

.detail-value {
    flex: 1 !important;
    font-size: var(--text-sm) !important;
    color: var(--text-primary) !important;
    line-height: 1.5 !important;
}

/* --- 15. 音频播放器优化 --- */

/* 修复音频播放器控制按钮重叠问题 */
[class*="audio"] .controls-wrap {
    display: flex !important;
    align-items: center !important;
    justify-content: space-around !important;
    gap: 8px !important;
    padding: 8px !important;
    flex-wrap: nowrap !important;
}

/* 音频播放器按钮尺寸优化 */
[class*="audio"] button {
    min-width: 36px !important;
    min-height: 36px !important;
    padding: 6px !important;
}

/* 音频播放器容器宽度 */
[class*="audio"] {
    width: 100% !important;
}

/* 关键修复：让 Row 的右侧列高度自适应内容，不跟随左侧拉伸 */
.enhanced-tabs > .tab-wrap > .tabitem > .gap > .row {
    align-items: flex-start !important;
}

/* 强制所有 gradio-row 内的 gradio-column 不拉伸 */
.gradio-row {
    align-items: flex-start !important;
}
.gradio-column {
    height: auto !important;
    min-height: 0 !important;
    flex-shrink: 0 !important;
    align-self: flex-start !important;
}

/* 输出面板高度自适应 */
.gradio-column > .gradio-group {
    height: auto !important;
    min-height: auto !important;
}

/* ===== 关键修复：右侧输出面板不拉伸 ===== */
/* 通过 elem_classes="right-output-panel" 精确定位 */
.right-output-panel,
#right-output-panel {
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    align-self: flex-start !important;
    flex-grow: 0 !important;
    flex-shrink: 0 !important;
    overflow: visible !important;
}
.right-output-panel > *,
#right-output-panel > * {
    height: auto !important;
    min-height: 0 !important;
}
/* 右侧面板内的 Audio 组件紧凑化 */
.right-output-panel .gradio-audio,
#right-output-panel .gradio-audio {
    min-height: auto !important;
    height: auto !important;
}
/* 右侧面板内的 Textbox 紧凑化 */
.right-output-panel .gradio-textbox,
#right-output-panel .gradio-textbox {
    min-height: auto !important;
    height: auto !important;
}

/* --- 26. 顶部导航区紧凑优化 --- */
/* 缩小引擎选择行间距 */
#engine-selector-row {
    margin-bottom: 12px !important;
    gap: 12px !important;
}

/* 缩小引擎选择区域的内边距 */
#engine-selector-row > div {
    gap: 8px !important;
}

/* 缩小警告提示的垂直间距 */
.engine-warning {
    margin-top: 4px !important;
    margin-bottom: 4px !important;
    padding: 4px 12px !important;
}

/* 缩小输出格式选择的间距 */
.gradio-container .form .gradio-radio:has(input[name=" 输出格式"]) {
    margin-bottom: 12px !important;
    padding: 8px 16px !important;
}

/* 缩小标签页导航的高度 */
.enhanced-tabs > .tab-nav {
    padding: 4px 8px 0 8px !important;
    margin-bottom: 0 !important;
}

.enhanced-tabs > .tab-nav button {
    padding: 8px 16px !important;
    font-size: 13px !important;
}

/* 缩小卡片之间的间距 */
.card {
    margin-bottom: 12px !important;
    padding: 16px !important;
}

.card-header {
    margin-bottom: 12px !important;
    padding-bottom: 8px !important;
}

/* 缩小输入表单元素的间距 */
.gradio-textbox label,
.gradio-dropdown label,
.gradio-radio label {
    margin-bottom: 6px !important;
}

.gradio-textbox textarea,
.gradio-textbox input,
.gradio-dropdown select {
    padding: 8px 12px !important;
}

/* 缩小内部标签页的间距 */
.inner-tabs > .tab-nav {
    margin-bottom: 12px !important;
    padding: 4px !important;
}

.inner-tabs > .tab-nav button {
    padding: 6px 12px !important;
}

/* 缩小按钮间距 */
.primary-btn,
.secondary-btn {
    margin-top: 8px !important;
    margin-bottom: 8px !important;
}

/* 缩小分隔线的间距 */
.divider {
    margin: 12px 0 !important;
}

/* 缩小语音预设标签的间距 */
.voice-preset-tags {
    margin: 8px 0 !important;
    padding: 8px !important;
    gap: 6px !important;
}

.preset-tag {
    padding: 4px 10px !important;
    font-size: 12px !important;
}

/* 缩小保存名称区域的间距 */
/* output-panel textbox styles removed - elem_id not defined in Python */

/* 优化行间距 */
.enhanced-tabs > .tab-wrap > .tabitem > .gap > .row {
    gap: 12px !important;
}

.enhanced-tabs > .tab-wrap > .tabitem > .gap {
    gap: 12px !important;
}

/* 缩小引擎状态文本框的间距 */
#engine-status-textbox {
    padding: 8px !important;
}

#engine-status-textbox textarea {
    font-size: 13px !important;
}

/* 缩小状态栏的间距 */
#status-bar {
    margin-bottom: 12px !important;
    padding: 8px 16px !important;
}

/* --- 16. 进度条容器优化 --- */
.progress-container {
    margin: var(--space-4) 0 !important;
    padding: var(--space-3) var(--space-4) !important;
    background: var(--bg-glass) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    box-shadow: var(--shadow-sm) !important;
}

/* --- 17. 系统状态栏优化 --- */
#status-bar {
    background: var(--bg-glass) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-3) var(--space-4) !important;
    margin-bottom: var(--space-4) !important;
    display: flex !important;
    align-items: center !important;
    gap: var(--space-2) !important;
    font-size: var(--text-sm) !important;
    color: var(--text-secondary) !important;
    box-shadow: var(--shadow-sm) !important;
}

.status-pulse {
    display: inline-block !important;
    width: 8px !important;
    height: 8px !important;
    background: var(--accent-success) !important;
    border-radius: 50% !important;
    animation: pulse 2s ease-in-out infinite !important;
}

@keyframes pulse {
    0%, 100% {
        opacity: 1 !important;
        transform: scale(1) !important;
    }
    50% {
        opacity: 0.5 !important;
        transform: scale(0.9) !important;
    }
}

/* --- 18. 输出格式选择优化 --- */
.gradio-container .form .gradio-radio:has(input[name="🎵 输出格式"]) {
    background: var(--bg-glass) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-3) var(--space-4) !important;
    margin-bottom: var(--space-4) !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: var(--space-3) !important;
}

/* --- 19. 模型规格Radio优化 --- */
.model-size-radio {
    margin-bottom: var(--space-4) !important;
}

.model-size-radio .wrap {
    display: flex !important;
    gap: var(--space-2) !important;
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-1) !important;
}

.model-size-radio .wrap .radio {
    background: transparent !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    padding: var(--space-2) var(--space-4) !important;
    transition: all var(--duration-normal) var(--ease-standard) !important;
    flex: 1 !important;
    text-align: center !important;
}

.model-size-radio .wrap .radio:hover {
    background: var(--bg-elevated) !important;
}

.model-size-radio .wrap .radio:has(input:checked) {
    background: var(--primary) !important;
    box-shadow: 0 2px 8px var(--primary-glow) !important;
}

.model-size-radio .wrap .radio:has(input:checked) label span {
    color: #ffffff !important;
    font-weight: 600 !important;
}

/* --- 20. 剧本工坊布局优化 --- */
/* 使用通用选择器替代中文 ID（Gradio tab id 不一定渲染为 DOM id） */
.gradio-tabitem[id*="Tab"] .gradio-column:first-child {
    flex: 2 !important;
}

.gradio-tabitem[id*="Tab"] .gradio-column:last-child {
    flex: 1 !important;
}

/* --- 21. 响应式设计优化 --- */
/* ===== 深色主题覆盖：消除灰色背景 ===== */
/* Gradio 组件默认使用 --background-fill-secondary（灰色），覆盖为深色 */
.gradio-container {
    --background-fill-primary: rgba(15, 15, 30, 0.6) !important;
    --background-fill-secondary: rgba(20, 20, 40, 0.5) !important;
    --background-fill-tertiary: rgba(25, 25, 50, 0.4) !important;
    --border-color-primary: rgba(80, 80, 140, 0.2) !important;
    --border-color-secondary: rgba(60, 60, 120, 0.15) !important;
    --body-background-fill: rgba(10, 10, 20, 1) !important;
    --block-background-fill: rgba(15, 15, 30, 0.6) !important;
    --block-border-color: rgba(80, 80, 140, 0.15) !important;
}
/* Group 组件背景 */
.gradio-group,
.gradio-panel,
.gradio-form,
.gradio-accesor,
.gradio-checkboxgroup,
.gradio-radio {
    background: transparent !important;
    border-color: rgba(80, 80, 140, 0.15) !important;
}
/* Audio 组件背景 */
.gradio-audio {
    background: rgba(20, 20, 40, 0.5) !important;
    border-color: rgba(80, 80, 140, 0.2) !important;
}
/* Dataframe/表格背景 */
.gradio-dataframe {
    background: rgba(15, 15, 30, 0.6) !important;
    border-color: rgba(80, 80, 140, 0.15) !important;
}
/* Dropdown 背景 */
.gradio-dropdown {
    background: rgba(20, 20, 40, 0.5) !important;
}
/* Textbox 背景 */
.gradio-textbox textarea,
.gradio-textbox input {
    background: rgba(15, 15, 30, 0.6) !important;
}
/* Tab 内容区域背景 */
.tabitem {
    background: transparent !important;
}

/* ===== 布局优化 ===== */
/* Row 内 Column 顶部对齐（仅剧本工坊等保留左右分栏的 Tab） */
.row {
    align-items: flex-start !important;
}
.row > .column:last-child {
    flex: 0 1 auto !important;
    align-self: flex-start !important;
}

/* ===== 左侧内容紧凑化 ===== */
/* 减少卡片内部间距 */
.card {
    padding: 10px !important;
    gap: 6px !important;
}
/* 减少文本框内边距 */
.card .gradio-textbox textarea,
.card .gradio-textbox input {
    padding: 6px 10px !important;
    min-height: unset !important;
}
/* 减少按钮上下间距 */
.card .primary-btn {
    margin-top: 2px !important;
    margin-bottom: 2px !important;
}
/* 减少分割线间距 */
.card .divider {
    margin: 6px 0 !important;
}
/* 减少下拉框间距 */
.card .gradio-dropdown {
    margin-bottom: 2px !important;
}
/* 减少标签页间距 */
.inner-tabs {
    margin-top: 4px !important;
}
/* 减少卡片标题间距 */
.card-header {
    margin-bottom: 4px !important;
}
.card-header h3 {
    margin: 0 !important;
    font-size: 14px !important;
}
/* 预设标签行紧凑化 */
.voice-preset-tags {
    margin-top: 4px !important;
    margin-bottom: 4px !important;
}
.voice-preset-tags .preset-tag {
    padding: 2px 10px !important;
    font-size: 12px !important;
    margin: 2px !important;
}

@media (max-width: 1440px) {
    .enhanced-tabs > .tab-wrap > .tabitem > .gap > .row {
        flex-direction: column !important;
    }

    .enhanced-tabs > .tab-wrap > .tabitem > .gap > .row > .column:first-child {
        flex: 1 1 0% !important;
        min-width: 0 !important;
    }
    .enhanced-tabs > .tab-wrap > .tabitem > .gap > .row > .column:last-child {
        flex: 0 1 auto !important;
        min-width: 0 !important;
        align-self: flex-start !important;
    }
    
    /* output-panel responsive styles removed - elem_id not defined in Python */
}

@media (max-width: 1024px) {
    #engine-selector-row {
        flex-direction: column !important;
    }
    
    #engine-selector-row > .column {
        width: 100% !important;
    }
    
    .enhanced-tabs > .tab-nav {
        padding: var(--space-2) var(--space-2) !important;
        gap: var(--space-1) !important;
    }
    
    .enhanced-tabs > .tab-nav button {
        padding: var(--space-2) var(--space-3) !important;
        font-size: var(--text-xs) !important;
    }
    
    .enhanced-tabs > .tab-wrap {
        padding: var(--space-4) !important;
    }
}

@media (max-width: 768px) {
    .simple-nav {
        flex-direction: column !important;
        gap: var(--space-2) !important;
        padding: var(--space-3) !important;
    }
    
    .nav-badges {
        flex-wrap: wrap !important;
        justify-content: center !important;
    }
    
    .enhanced-tabs > .tab-nav {
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
    }
    
    .enhanced-tabs > .tab-nav::-webkit-scrollbar {
        height: 2px !important;
    }
    
    .card {
        padding: var(--space-4) !important;
    }
    
    .card-header {
        flex-direction: column !important;
        align-items: flex-start !important;
        gap: var(--space-1) !important;
    }
    
    .voice-preset-tags {
        justify-content: center !important;
    }
    
    .filter-bar {
        justify-content: center !important;
    }
}

@media (max-width: 480px) {
    .gradio-container {
        padding: var(--space-2) !important;
    }
    
    .enhanced-tabs > .tab-wrap {
        padding: var(--space-3) !important;
    }
    
    .card {
        padding: var(--space-3) !important;
    }
    
    .card-header-title {
        font-size: var(--text-base) !important;
    }
    
    .primary-btn,
    .secondary-btn {
        width: 100% !important;
    }
}

/* --- 22. 滚动条美化 --- */
.gradio-container::-webkit-scrollbar {
    width: 8px !important;
    height: 8px !important;
}

.gradio-container::-webkit-scrollbar-track {
    background: var(--bg-tertiary) !important;
    border-radius: 4px !important;
}

.gradio-container::-webkit-scrollbar-thumb {
    background: var(--border-medium) !important;
    border-radius: 4px !important;
    transition: background var(--duration-normal) var(--ease-standard) !important;
}

.gradio-container::-webkit-scrollbar-thumb:hover {
    background: var(--primary) !important;
}

/* --- 23. 动画优化 --- */
@keyframes fadeInUp {
    from {
        opacity: 0 !important;
        transform: translateY(10px) !important;
    }
    to {
        opacity: 1 !important;
        transform: translateY(0) !important;
    }
}

.card,
.output-panel,
.purple-audio,
.status-textbox {
    animation: fadeInUp var(--duration-slow) var(--ease-decelerate) !important;
}

/* --- 24. 焦点环优化 --- */
:focus-visible {
    outline: 2px solid var(--primary) !important;
    outline-offset: 2px !important;
    border-radius: var(--radius-sm) !important;
}

/* --- 25. 音频组件下载按钮不被裁剪 --- */
.purple-audio > div,
.gradio-audio > div {
    overflow: visible !important;
}

/* 确保音频容器的padding给下载按钮留出空间 */
.purple-audio {
    padding-top: 20px !important;
    padding-bottom: 20px !important;
    padding-right: 20px !important;
    padding-left: 15px !important;
}
"""

_OFFICIAL_SPEAKERS_ORDERED = ["Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric", "Ryan", "Aiden", "Ono_Anna", "Sohee"]
_OFFICIAL_DISPLAY_NAMES = [f"{OFFICIAL_SPEAKER_INFO[s][0]} ({s})" for s in _OFFICIAL_SPEAKERS_ORDERED]
_LANGS = ["Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian", "Auto"]

# --- 【7. I18n 国际化】 ---
_I18N_TRANSLATIONS = {
    "en": {
        "app_title": "TTS MultiModel Voice Studio",
        "nav_brand": "🎙️ TTS MultiModel",
        "status_ready": "⚡ **Ready · Waiting for input**",
        "output_format": "🎵 Output Format",
        "engine_selector": "⚙️ Select Engine",
        "engine_status": "Engine Status",
        "tab_voice_design": "🎨 Voice Design",
        "tab_voice_clone": "👥 Voice Clone",
        "tab_official": "🌟 Official Voices",
        "tab_script": "🎬 Script Studio",
        "tab_voxcpm2": " VoxCPM2 Engine",
        "tab_history": "📜 History",
        "tab_persona": "🎵 Voice Library",
        "input_settings": "✏️ Input Settings",
        "synthesis_text": "Synthesis Text",
        "language": "Language",
        "voice_description": "Voice Description",
        "preset_create": "Description Create",
        "saved_voices": "Saved Voices",
        "select_persona": "Select Saved Voice (incl. Official)",
        "no_persona": "(No voices available)",
        "generate_btn": "✨ Generate Preview",
        "clone_btn": "🚀 Start Cloning",
        "official_btn": "🚀 Generate",
        "clone_settings": "🧬 Clone Settings",
        "model_size": "Model Size",
        "ref_audio": "Reference Audio",
        "ref_text": "Reference Text (optional)",
        "refresh_list": "🔄 Refresh List",
        "use_selected": "🎙️ Generate with Selected",
        "save_name": "Save Name",
        "save_persona": "📂 Save to Voice Library",
        "result_audio": "Result Audio",
        "clone_result": "Clone Result",
        "status": "Status",
        "official_voice": "⭐ Official Voice",
        "filter_all": "All",
        "filter_female": "Female",
        "filter_male": "Male",
        "filter_sweet": "Sweet",
        "filter_mature": "Mature",
        "filter_deep": "Deep",
        "script_editor": "📜 Script Editor",
        "script_content": "Script Content",
        "quick_insert": "🎭 Quick Insert Voice",
        "custom_voice": "Custom Voice",
        "official_voice_tab": "Official Voice",
        "history_title": "📁 Generation History",
        "search_file": "🔍 Search Filename",
        "clear_search": "🗑️ Clear",
        "time_today": "Today",
        "time_week": "This Week",
        "time_month": "This Month",
        "time_all": "All",
        "persona_title": "🎙️ Voice Library Details",
        "search_persona": "🔍 Search Voice Name",
        "view_list": "☰ List",
        "view_card": "⊞ Card",
        "current_persona": "Current Selected Voice",
        "preview": "Preview",
        "play_btn": "▶️ Play Voice",
        "delete_btn": "🗑️ Delete Voice",
        "voxcpm_design": "✏️ VoxCPM2 Voice Design",
        "voxcpm_clone": "🧬 Controllable Clone",
        "voxcpm_ultimate": "🔬 Ultimate Clone",
        "control_instruction": "Control Instruction (optional)",
        "synthesis_text_vox": "Synthesis Text",
        "advanced_settings": "⚙️ Advanced Settings",
        "cfg_value": "CFG Value",
        "locdit_steps": "LocDiT Steps",
        "denoise_strength": "Denoise Strength",
        "text_normalize": "Text Normalization",
        "randomness": "Randomness",
        "generate_ultimate": "✨ Ultimate Clone Generate",
        "official_text_area": "Text (supports [Speaker][Instruction]Text format)",
    },
    "zh-CN": {
        "app_title": "TTS MultiModel 语音工坊",
        "nav_brand": "🎙️ TTS MultiModel",
        "status_ready": "⚡ **引擎就绪 · 等待输入**",
        "output_format": "🎵 输出格式",
        "engine_selector": "⚙️ 选择引擎",
        "engine_status": "引擎状态",
        "tab_voice_design": "🎨 声音设计",
        "tab_voice_clone": "👥 语音克隆",
        "tab_official": "🌟 官方精品",
        "tab_script": "🎬 剧本工坊",
        "tab_voxcpm2": " VoxCPM2 引擎",
        "tab_history": "📜 历史记录",
        "tab_persona": "🎵 音色库",
        "input_settings": "✏️ 输入设置",
        "synthesis_text": "合成文本",
        "language": "语言",
        "voice_description": "声音描述",
        "preset_create": "描述创建",
        "saved_voices": "已保存音色",
        "select_persona": "选择已保存音色（含官方）",
        "no_persona": "(暂无音色)",
        "generate_btn": "✨ 生成试听",
        "clone_btn": "🚀 开始克隆",
        "official_btn": "🚀 生成",
        "clone_settings": "🧬 克隆设置",
        "model_size": "模型规格",
        "ref_audio": "参考原声",
        "ref_text": "原声文本（可选）",
        "refresh_list": "🔄 刷新列表",
        "use_selected": "🎙️ 使用选中音色生成",
        "save_name": "保存名称",
        "save_persona": "📂 固化到音色库",
        "result_audio": "结果音频",
        "clone_result": "克隆结果",
        "status": "状态",
        "official_voice": "⭐ 官方精品音色",
        "filter_all": "全部",
        "filter_female": "女声",
        "filter_male": "男声",
        "filter_sweet": "甜美",
        "filter_mature": "成熟",
        "filter_deep": "低沉",
        "script_editor": "📜 剧本编辑器",
        "script_content": "剧本内容",
        "quick_insert": "🎭 快速插入音色",
        "custom_voice": "自定义音色",
        "official_voice_tab": "官方音色",
        "history_title": "📁 生成历史",
        "search_file": "🔍 搜索文件名",
        "clear_search": "🗑️ 清空搜索",
        "time_today": "今天",
        "time_week": "本周",
        "time_month": "本月",
        "time_all": "全部",
        "persona_title": "🎙️ 音色库详情",
        "search_persona": "🔍 搜索音色名称",
        "view_list": "☰ 列表",
        "view_card": "⊞ 卡片",
        "current_persona": "当前选中音色",
        "preview": "试听",
        "play_btn": "▶️ 试听音色",
        "delete_btn": "🗑️ 删除音色",
        "voxcpm_design": "✏️ VoxCPM2 声音设计",
        "voxcpm_clone": "🧬 可控克隆",
        "voxcpm_ultimate": "🔬 极致克隆",
        "control_instruction": "控制指令（可选）",
        "synthesis_text_vox": "合成文本",
        "advanced_settings": "⚙️ 高级设置",
        "cfg_value": "CFG Value",
        "locdit_steps": "LocDiT Steps",
        "denoise_strength": "降噪强度",
        "text_normalize": "文本规范化",
        "randomness": "随机性",
        "generate_ultimate": "✨ 极致克隆生成",
        "official_text_area": "文本（支持 [角色][指令]文本 格式）",
    },
}
_I18N_TRANSLATIONS["zh-Hans"] = _I18N_TRANSLATIONS["zh-CN"]
_I18N_TRANSLATIONS["zh"] = _I18N_TRANSLATIONS["zh-CN"]

for _d in _I18N_TRANSLATIONS.values():
    if _d is not None:
        for _k, _v in _I18N_TRANSLATIONS["en"].items():
            _d.setdefault(_k, _v)

I18N = gr.I18n(**_I18N_TRANSLATIONS)

# --- 【8. UI 构建（增强版）】 ---
def run_integrated(ip, port):
    with gr.Blocks(
        title="TTS MultiModel 语音工坊",
        head="<style>" + ENHANCED_CSS + "</style>",
        js="""
        // ===== I18n 国际化支持 =====
        (function() {
            var translations = {
                en: {
                    nav_status: 'Dual Engines Ready · Waiting for Input',
                    nav_multi_engine: 'Multi-Engine Support',
                    history_empty_text: 'No generation records',
                    history_empty_hint: 'After synthesizing audio, history records will automatically appear here',
                    history_first_btn: '🎨 Start First Synthesis',
                    persona_empty_text: 'No custom voices',
                    persona_empty_hint: 'After saving a voice in "Voice Design" or "Voice Clone", it will be displayed here',
                    persona_first_btn: '🎨 Create First Voice',
                    filter_label: 'Filter:',
                    time_filter: 'Time:',
                    select_all: 'Select All',
                    batch_export: '📦 Batch Export',
                    batch_delete: '🗑️ Batch Delete',
                    all: 'All',
                    today: 'Today',
                    week: 'This Week',
                    month: 'This Month',
                    female: 'Female',
                    male: 'Male',
                    sweet: 'Sweet',
                    mature: 'Mature',
                    deep: 'Deep',
                    list: '☰ List',
                    card: '⊞ Card',
                    footer_brand: '🎙️ AI Voice Studio Pro',
                    footer_desc: 'Integrating Qwen3TTS and VoxCPM2 dual engines, providing professional-grade speech synthesis, voice design and multi-person script editing capabilities.',
                    footer_features: 'Core Features',
                    footer_tech: 'Technology Stack',
                    footer_links: 'Links',
                    footer_blog: 'Official Blog',
                    footer_bottom: 'Powered by <strong>Qwen3TTS</strong> · VoxCPM2 · CUDA Graph Accelerated Core'
                },
                zh: {
                    nav_status: '双引擎就绪 · 等待输入',
                    nav_multi_engine: '多引擎支持',
                    history_empty_text: '暂无生成记录',
                    history_empty_hint: '合成音频后，历史记录将自动显示在这里',
                    history_first_btn: '🎨 开始首次合成',
                    persona_empty_text: '暂无自定义音色',
                    persona_empty_hint: '在"声音设计"或"语音克隆"中保存音色后，将显示在这里',
                    persona_first_btn: '🎨 创建首个音色',
                    filter_label: '筛选:',
                    time_filter: '时间:',
                    select_all: '全选',
                    batch_export: '📦 批量导出',
                    batch_delete: '🗑️ 批量删除',
                    all: '全部',
                    today: '今天',
                    week: '本周',
                    month: '本月',
                    female: '女声',
                    male: '男声',
                    sweet: '甜美',
                    mature: '成熟',
                    deep: '低沉',
                    list: '☰ 列表',
                    card: '⊞ 卡片',
                    footer_brand: '🎙️ AI 语音工坊 Pro',
                    footer_desc: '集成 Qwen3TTS 与 VoxCPM2 双引擎，提供专业级语音合成、声音设计与多人剧本编辑能力。',
                    footer_features: '核心功能',
                    footer_tech: '技术栈',
                    footer_links: '链接',
                    footer_blog: '官方博客',
                    footer_bottom: 'Powered by <strong>Qwen3TTS</strong> · VoxCPM2 · CUDA Graph 加速内核'
                }
            };
            translations['zh-CN'] = translations.zh;
            translations['zh-Hans'] = translations.zh;
            
            var currentLang = 'zh';
            
            window.setUILanguage = function(lang) {
                currentLang = lang;
                var dict = translations[lang] || translations.zh;
                document.querySelectorAll('[data-i18n]').forEach(function(el) {
                    var key = el.getAttribute('data-i18n');
                    if (dict[key]) {
                        el.textContent = dict[key];
                    }
                });
            };
            
            setTimeout(function() { window.setUILanguage(currentLang); }, 100);
            setTimeout(function() { window.setUILanguage(currentLang); }, 500);
        })();
        
        // ===== 音频面板空状态提示 =====
        (function() {
            function addEmptyStates() {
                var groups = document.querySelectorAll('.gr-group');
                groups.forEach(function(group) {
                    var text = group.textContent || '';
                    if (text.includes('结果音频') || text.includes('合成音频') || text.includes('克隆结果')) {
                        var hasAudio = group.querySelector('audio') !== null;
                        if (!hasAudio && !group.querySelector('.output-empty-state')) {
                            var emptyDiv = document.createElement('div');
                            emptyDiv.className = 'output-empty-state';
                            emptyDiv.innerHTML = '<div style="text-align:center;">' +
                                '<div style="font-size:13px;color:rgba(255,255,255,0.9);line-height:1.6;">' +
                                '<div style="margin-bottom:6px;font-weight:600;">开始你的声音之旅：</div>' +
                                '<div style="display:flex;align-items:center;gap:6px;justify-content:center;margin-bottom:3px;">' +
                                '<span style="background:rgba(255,255,255,0.15);border-radius:50%;width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;">①</span>' +
                                '<span style="font-size:12px;">输入文本</span></div>' +
                                '<div style="display:flex;align-items:center;gap:6px;justify-content:center;margin-bottom:3px;">' +
                                '<span style="background:rgba(255,255,255,0.15);border-radius:50%;width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;">②</span>' +
                                '<span style="font-size:12px;">描述风格</span></div>' +
                                '<div style="display:flex;align-items:center;gap:6px;justify-content:center;">' +
                                '<span style="background:rgba(255,255,255,0.15);border-radius:50%;width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;">③</span>' +
                                '<span style="font-size:12px;">点击生成</span></div>' +
                                '</div></div>';
                            group.appendChild(emptyDiv);
                        }
                        if (hasAudio) {
                            var existing = group.querySelector('.output-empty-state');
                            if (existing) existing.remove();
                        }
                    }
                });
            }
            
            setTimeout(addEmptyStates, 300);
            setTimeout(addEmptyStates, 800);
        })();

        /* ===== Toast 通知系统 ===== */
        (function() {
            if (!document.querySelector('.toast-container')) {
                var container = document.createElement('div');
                container.className = 'toast-container';
                document.body.appendChild(container);
            }
        })();

        window.showToast = function(message, type, duration) {
            type = type || 'info';
            duration = duration || 3000;
            var container = document.querySelector('.toast-container');
            if (!container) return;
            var toast = document.createElement('div');
            toast.className = 'toast toast-' + type;
            var icon = type === 'success' ? '\u2705' : type === 'error' ? '\u274c' : '\u2139\uFE0F';
            toast.innerHTML = '<span>' + icon + '</span><span>' + message + '</span><span class="toast-close" onclick="this.parentElement.remove()">\u00D7</span>';
            container.appendChild(toast);
            if (duration > 0) {
                setTimeout(function() {
                    toast.style.animation = 'toast-out 200ms ease-in forwards';
                    setTimeout(function() { if (toast.parentElement) toast.remove(); }, 200);
                }, duration);
            }
        };

        /* ===== 网络状态监听 ===== */
        window.addEventListener('offline', function() {
            if (window.showToast) window.showToast('\u7F51\u7EDC\u8FDE\u63A5\u5DF2\u65AD\u5F00', 'error', 0);
        });
        window.addEventListener('online', function() {
            if (window.showToast) window.showToast('\u7F51\u7EDC\u8FDE\u63A5\u5DF2\u6062\u590D', 'success', 3000);
        });

        /* ===== 字数计数器 ===== */
        window.initCharCounters = function() {
            var textareas = document.querySelectorAll('.gradio-container textarea');
            textareas.forEach(function(ta) {
                if (ta.dataset.charCounterInit) return;
                ta.dataset.charCounterInit = '1';
                var counter = document.createElement('div');
                counter.className = 'char-counter';
                ta.parentElement.style.position = 'relative';
                ta.parentElement.appendChild(counter);
                var updateCounter = function() {
                    var len = ta.value.length;
                    var maxPerSeg = 200;
                    var segs = Math.ceil(Math.max(len, 1) / maxPerSeg);
                    if (len === 0) {
                        counter.textContent = '\u6BCF200\u5B57\u81EA\u52A8\u5206\u6BB5\u5408\u6210';
                        counter.className = 'char-counter';
                    } else if (len <= maxPerSeg) {
                        counter.textContent = len + ' \u5B57 | 1 \u6BB5\u5408\u6210';
                        counter.className = 'char-counter';
                    } else {
                        counter.textContent = '\u5DF2\u8F93\u5165 ' + len + ' \u5B57\uFF08\u5C06\u5206 ' + segs + ' \u6BB5\u5408\u6210\uFF09';
                        counter.className = 'char-counter' + (len > maxPerSeg * 5 ? ' error' : len > maxPerSeg * 3 ? ' warn' : '');
                    }
                };
                ta.addEventListener('input', updateCounter);
                updateCounter();
            });
        };
        setTimeout(window.initCharCounters, 500);
        setTimeout(window.initCharCounters, 2000);

        /* ===== 输入框抖动 - 空输入提示 ===== */
        window.shakeEmptyInputs = function() {
            var generateBtns = document.querySelectorAll('.primary-btn');
            generateBtns.forEach(function(btn) {
                if (btn.dataset.shakeInit) return;
                btn.dataset.shakeInit = '1';
                btn.addEventListener('click', function() {
                    var tab = btn.closest('.tab-item, [id*="Tab"]');
                    if (!tab) return;
                    var textareas = tab.querySelectorAll('textarea');
                    textareas.forEach(function(ta) {
                        if (!ta.value || ta.value.trim() === '') {
                            ta.classList.remove('input-shake');
                            void ta.offsetWidth;
                            ta.classList.add('input-shake');
                            setTimeout(function() { ta.classList.remove('input-shake'); }, 500);
                        }
                    });
                });
            });
        };
        setTimeout(window.shakeEmptyInputs, 1000);

        /* ===== 标签页未保存警告 ===== */
        (function() {
            var tabChanges = new Map();
            var trackedTextareas = new Set();

            function trackTextarea(ta) {
                if (trackedTextareas.has(ta)) return;
                trackedTextareas.add(ta);
                var tabId = 'default';
                var parent = ta.closest('.tab-item');
                if (parent) {
                    var btn = parent.querySelector('[role="tab"], button[aria-selected]');
                    if (btn) tabId = btn.textContent || btn.getAttribute('data-id') || 'unknown';
                }
                ta.addEventListener('input', function() {
                    tabChanges.set(tabId, true);
                });
                ta._tabId = tabId;
            }

            function watchTabs() {
                document.querySelectorAll('.gradio-container textarea').forEach(trackTextarea);
            }

            setTimeout(watchTabs, 1000);
            (function watchTabsLimited() {
        setTimeout(function() {
            watchTabs();
            if (document.querySelector('.enhanced-tabs')) watchTabsLimited();
        }, 5000);
    })();

            var tabNav = document.querySelector('.enhanced-tabs > .tab-nav');
            if (tabNav) {
                tabNav.addEventListener('click', function(e) {
                    var btn = e.target.closest('button');
                    if (!btn) return;
                    var currentActive = document.querySelector('.enhanced-tabs > .tab-nav button.selected');
                    if (currentActive) {
                        var prevTabId = currentActive.textContent || 'unknown';
                        if (tabChanges.get(prevTabId)) {
                            if (!confirm('\u5F53\u524D\u6807\u7B7E\u6709\u672A\u4FDD\u5B58\u7684\u5185\u5BB9\uFF0C\u786E\u5B9A\u8981\u5207\u6362\u5417\uFF1F')) {
                                e.preventDefault();
                                e.stopPropagation();
                            } else {
                                tabChanges.set(prevTabId, false);
                            }
                        }
                    }
                });
            }
        })();

        /* ===== Skeleton 骨架屏辅助 ===== */
        window.showSkeleton = function(container, count) {
            count = count || 3;
            var el = typeof container === 'string' ? document.querySelector(container) : container;
            if (!el) return;
            el.innerHTML = '';
            for (var i = 0; i < count; i++) {
                var line = document.createElement('div');
                line.className = 'skeleton-line' + (i % 3 === 2 ? ' short' : '');
                el.appendChild(line);
            }
        };

        /* ===== DOM就绪后初始化增强 ===== */
        document.addEventListener('DOMContentLoaded', function() {
            if (window.showToast) {
                window.showToast('\u7CFB\u7EDF\u5C31\u7EEA\uFF0C\u6B22\u8FCE\u4F7F\u7528 Qwen3-TTS Pro', 'success', 4000);
            }
        });

        /* ===== 声音描述预设标签点击插入 ===== */
        (function() {
            var initTags = function() {
                var container = document.getElementById('voice-preset-tags');
                if (!container) return;
                if (container.dataset.tagInit) return;
                container.dataset.tagInit = '1';
                
                var tags = container.querySelectorAll('.preset-tag');
                tags.forEach(function(tag) {
                    tag.addEventListener('click', function() {
                        // 预设标签选中态
                        document.querySelectorAll('.preset-tag').forEach(function(t) { t.classList.remove('preset-tag-active'); });
                        this.classList.add('preset-tag-active');
                        var value = this.getAttribute('data-value') || this.textContent;
                        // Find the voice description textarea (声音描述)
                        var descTextarea = document.querySelector('[aria-label*="声音描述"], [placeholder*="极度撒娇的萝莉音"]');
                        if (descTextarea) {
                            if (descTextarea.value && descTextarea.value.trim()) {
                                descTextarea.value = descTextarea.value.trim() + '，' + value;
                            } else {
                                descTextarea.value = value;
                            }
                            descTextarea.dispatchEvent(new Event('input', { bubbles: true }));
                            descTextarea.focus();
                        }
                    });
                });
            };
            
            setTimeout(initTags, 800);
            setTimeout(initTags, 2000);
            var _tagObserver = new MutationObserver(function() { setTimeout(initTags, 200); }); _tagObserver.observe(document.body, { childList: true, subtree: true });;
        })();
        
        // ===== 官方精品音色卡片交互 =====
        window.selectSpeakerCard = function(key) {
            // 更新选中状态
            document.querySelectorAll('.speaker-card').forEach(function(card) {
                card.classList.remove('selected');
            });
            var target = document.querySelector('.speaker-card[data-speaker="' + key + '"]');
            if (target) target.classList.add('selected');
            
            // 更新桥接 Textbox（触发 Python 端 change 事件）
            var bridgeInput = document.querySelector('#speaker-bridge-input textarea, #speaker-bridge-input input');
            if (bridgeInput) { bridgeInput.value = key; bridgeInput.dispatchEvent(new Event('input', {bubbles: true})); }
            
            // 更新详情面板
            var info = window.SPEAKER_INFO || {};
            var s = info[key] || ["", "", "", ""];
            var detailContainer = document.getElementById('speaker-detail-container');
            if (detailContainer) {
                detailContainer.innerHTML = '<div class="speaker-detail-panel">' +
                    '<h3>🎙️ ' + s[0] + ' (' + key + ')</h3>' +
                    '<div class="detail-row"><span class="detail-label">音色类型</span><span class="detail-value">' + s[2] + '</span></div>' +
                    '<div class="detail-row"><span class="detail-label">声音特点</span><span class="detail-value">' + s[3] + '</span></div>' +
                    '<div class="detail-row"><span class="detail-label">详细说明</span><span class="detail-value">' + s[1] + '</span></div>' +
                    '</div>';
            }
        };
        
        window.filterSpeaker = function(filter) {
            document.querySelectorAll('.filter-chip').forEach(function(chip) {
                chip.classList.remove('active');
            });
            document.querySelector('.filter-chip[data-filter="' + filter + '"]')?.classList.add('active');
            
            var cards = document.querySelectorAll('.speaker-card');
            cards.forEach(function(card) {
                if (filter === 'all') { card.style.display = ''; return; }
                var name = card.getAttribute('data-speaker') || '';
                var info = window.SPEAKER_INFO || {};
                var s = info[name] || [];
                var type = (s[2] || '').toLowerCase();
                var show = false;
                if (filter === 'female') show = (type.indexOf('女') >= 0 || type.indexOf('少女') >= 0 || type.indexOf('御姐') >= 0 || type.indexOf('甜') >= 0 || type.indexOf('日系') >= 0 || type.indexOf('韩系') >= 0);
                else if (filter === 'male') show = (type.indexOf('男') >= 0 || type.indexOf('低音') >= 0);
                else if (filter === 'sweet') show = (type.indexOf('甜') >= 0 || type.indexOf('少女') >= 0 || type.indexOf('日系') >= 0 || type.indexOf('韩系') >= 0);
                else if (filter === 'mature') show = (type.indexOf('御姐') >= 0 || type.indexOf('成熟') >= 0 || type.indexOf('中年') >= 0 || type.indexOf('青年') >= 0);
                else if (filter === 'deep') show = (type.indexOf('低音') >= 0 || type.indexOf('深沉') >= 0 || type.indexOf('磁性') >= 0);
                card.style.display = show ? '' : 'none';
            });
        };
        
        window.SPEAKER_INFO = {
             "Vivian": ["薇薇安", "甜美少女音，活泼热情，适合年轻女性角色配音。擅长日常对话和情感表达。", "少女音", "年轻活泼，语速轻快"],
             "Serena": ["塞雷娜", "优雅成熟女性声线，知性大方。适合专业播报、教学讲解和商务场景。", "御姐音", "沉稳知性，语速适中"],
             "Uncle_Fu": ["傅叔叔", "中年男性沉稳声线，温和可靠。适合长辈角色、纪录片旁白和故事讲述。", "中年男音", "沉稳厚重，语速较慢"],
             "Dylan": ["迪伦", "年轻男性活力声线，阳光开朗。适合青年角色、广告配音和娱乐内容。", "青年男音", "阳光活力，语速较快"],
             "Eric": ["埃里克", "磁性低沉男声，深沉有魅力。适合悬疑叙事、有声书和电影预告。", "低音炮", "深沉磁性，语速缓慢"],
             "Ryan": ["瑞恩", "清脆少年音，干净纯粹。适合动漫角色、儿童内容和轻快解说。", "少年音", "清脆明亮，语速轻快"],
             "Aiden": ["艾登", "温暖青年男声，亲切自然。适合播客、自媒体和日常交流场景。", "暖男音", "温和亲切，语速适中"],
             "Ono_Anna": ["小野安娜", "日式甜美女声，日系二次元风格。适合动漫角色、游戏配音和轻小说。", "日系甜音", "甜美可爱，语速轻快"],
             "Sohee": ["秀熙", "韩式清甜女声，韩流风格。适合韩剧风格内容、韩语学习辅助。", "韩系甜音", "清甜温柔，语速适中"]
         };
         
         // ===== 历史记录时间筛选 =====
         window.filterHistoryTime = function(filter) {
             document.querySelectorAll('.time-filter-chip').forEach(function(chip) {
                 chip.classList.remove('active');
             });
             document.querySelector('.time-filter-chip[data-time="' + filter + '"]')?.classList.add('active');
             // 通知后端刷新
             var rows = document.querySelectorAll('.enhanced-tabs .gr-dataframe tbody tr, .gradio-dataframe table tbody tr');
             if (rows.length === 0) return;
             // 这里通过刷新按钮触发实际筛选
             var refreshBtn = document.querySelector('[data-testid="🔄 刷新记录"]');
             if (refreshBtn) refreshBtn.click();
         };
         
         // ===== 历史记录批量操作 =====
         window.toggleAllHistory = function(checked) {
             document.querySelectorAll('.history-row-checkbox').forEach(function(cb) {
                 cb.checked = checked;
             });
         };
         
         window.batchExportHistory = function() {
             var selected = document.querySelectorAll('.history-row-checkbox:checked');
             if (selected.length === 0) { alert('请先选择要导出的记录'); return; }
             alert('批量导出功能：将导出 ' + selected.length + ' 个文件');
         };
         
         window.batchDeleteHistory = function() {
             var selected = document.querySelectorAll('.history-row-checkbox:checked');
             if (selected.length === 0) { alert('请先选择要删除的记录'); return; }
             if (confirm('确定要删除选中的 ' + selected.length + ' 条记录吗？此操作不可恢复。')) {
                 alert('批量删除功能已触发');
             }
         };
         
         // ===== 音色库视图切换 =====
         window.switchVoiceView = function(view) {
             document.querySelectorAll('.view-toggle-btn').forEach(function(btn) {
                 btn.classList.remove('active');
             });
             document.querySelector('.view-toggle-btn[data-view="' + view + '"]')?.classList.add('active');
             
             var listView = document.getElementById('persona-list-view');
             var cardView = document.getElementById('persona-card-view');
             if (view === 'card') {
                 if (listView) listView.style.display = 'none';
                 if (cardView) { cardView.style.display = ''; cardView.innerHTML = buildPersonaCardGrid(); }
             } else {
                 if (listView) listView.style.display = '';
                 if (cardView) cardView.style.display = 'none';
             }
         };
         
         window.buildPersonaCardGrid = function() {
             // 从表格数据构建卡片视图
             var df = document.querySelector('#persona-list-view table');
             if (!df) return '<p style="color:var(--text-muted)">暂无数据</p>';
             var rows = df.querySelectorAll('tbody tr');
             if (rows.length === 0 || (rows.length === 1 && rows[0].textContent.includes('暂无'))) {
                 return '<p style="color:var(--text-muted)">暂无音色</p>';
             }
             var html = '<div class="voice-card-grid">';
             rows.forEach(function(row) {
                 var cells = row.querySelectorAll('td');
                 if (cells.length >= 4) {
                     var name = cells[0].textContent.trim();
                     var status = cells[1].textContent.trim();
                     var size = cells[2].textContent.trim();
                     var time = cells[3].textContent.trim();
                     html += '<div class="voice-card" onclick="selectPersonaCard(' + JSON.stringify(name) + ')">' +
                         '<h4 class="voice-card-name">' + name + '</h4>' +
                         '<div class="voice-card-meta">状态: ' + status + ' | 大小: ' + size + '</div>' +
                         '<div class="voice-card-meta">创建: ' + time + '</div>' +
                         '<div class="voice-card-actions">' +
                         '<span class="speaker-card-btn" onclick="event.stopPropagation(); playPersonaByName(' + JSON.stringify(name) + ')">🔊 试听</span>' +
                         '</div></div>';
                 }
             });
             html += '</div>';
             return html;
         };
         
         window.selectPersonaCard = function(name) {
             var input = document.querySelector('[aria-label="当前选中音色"], #persona-list-view input');
             if (input) { input.value = name; input.dispatchEvent(new Event('input', {bubbles: true})); }
         };
         
         window.playPersonaByName = function(name) {
             var playBtn = document.querySelector('[data-testid="▶️ 试听音色"]');
             if (playBtn) playBtn.click();
         };
         
         // ===== 光标位置插入文本 =====
         window.insertAtCursor = function(textareaId, text) {
             var ta = document.querySelector(textareaId);
             if (!ta) return;
             var start = ta.selectionStart;
             var end = ta.selectionEnd;
             var value = ta.value;
             ta.value = value.substring(0, start) + text + value.substring(end);
             ta.selectionStart = ta.selectionEnd = start + text.length;
             ta.dispatchEvent(new Event('input', {bubbles: true}));
             ta.focus();
         };
         
         // ===== 键盘快捷键 =====
         document.addEventListener('keydown', function(e) {
             // Ctrl+Enter 触发当前标签页的生成按钮
             if (e.ctrlKey && e.key === 'Enter') {
                 var genBtn = document.querySelector('.generate-btn:not([disabled])');
                 if (genBtn) {
                     genBtn.click();
                     e.preventDefault();
                 }
             }
             // Esc 清空当前输入框
             if (e.key === 'Escape') {
                 var activeEl = document.activeElement;
                 if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA')) {
                     activeEl.value = '';
                     activeEl.dispatchEvent(new Event('input', {bubbles: true}));
                     e.preventDefault();
                 }
             }
         });
        """
    ) as demo:
        # 语言切换（通过 URL 参数控制）
        # lang_state 已移除（未使用）
        
        # 简洁导航栏
        gr.HTML('<div class="simple-nav">'
                '<div class="nav-brand">🎙️ TTS MultiModel</div>'
                '<div class="nav-badges">'
                '<span class="nav-badge"><span class="status-dot"></span> <span data-i18n="nav_status">双引擎就绪 · 等待输入</span></span>'
                '<span class="nav-badge"><span data-i18n="nav_multi_engine">多引擎支持</span></span>'
                '</div></div>')
        # 引擎切换区
        with gr.Row(elem_id="engine-selector-row", equal_height=True):
            with gr.Column(scale=3):
                engine_selector = gr.Radio(
                    choices=["Qwen3TTS 1.7B", "Qwen3TTS 0.6B", "VoxCPM2"],
                    value="Qwen3TTS 1.7B",
                    label=I18N("engine_selector"),
                    elem_id="engine-radio"
                )
                gr.HTML('<div class="engine-warning">切换需等待约20秒，请勿频繁操作</div>')
            with gr.Column(scale=1):
                engine_status_display = gr.Textbox(
                    label=I18N("engine_status"),
                    value="Qwen3TTS 1.7B | 就绪",
                    interactive=False,
                    elem_id="engine-status-textbox",
                    max_lines=1
                )
        # 系统状态栏
        status_bar = gr.Markdown(value='<span class="status-pulse"></span> **引擎就绪 · 等待输入** | ' + _gen_tracker.status_text(), elem_id="status-bar")
        output_format = gr.Radio(["wav", "mp3"], label=I18N("output_format"), value="wav", scale=0, min_width=160)
        with gr.Group(elem_classes=["progress-container"], visible=True):
            progress_bar = gr.Markdown(value="", elem_id="progress-bar")
        with gr.Tabs(elem_classes=["enhanced-tabs"]) as main_tabs:
            # Tab 1: 声音设计
            with gr.Tab(I18N("tab_voice_design"), id="声音设计"):
                with gr.Column():
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon">✏️</span><h3 class="card-header-title">输入设置</h3></div>')
                        txt = gr.Textbox(label=I18N("synthesis_text"), value="哥哥，你回来啦，人家等了你好久好久了，要抱抱！", lines=3, placeholder="请输入需要合成的文本...", elem_classes=["tts-input-textbox"])
                        lan = gr.Dropdown(_LANGS, label=I18N("language"), value="Auto", elem_classes=["tts-input-dropdown"])
                        with gr.Tabs(elem_classes=["inner-tabs"]):
                            with gr.Tab(I18N("preset_create")):
                                ins = gr.Textbox(label=I18N("voice_description"), placeholder="如：极度撒娇的萝莉音，带有明显的鼻音和撒娇语气", lines=1)
                                gr.HTML('<div id="voice-preset-tags" class="voice-preset-tags">'
                                        '<span class="preset-tag" data-value="萝莉音">萝莉音</span>'
                                        '<span class="preset-tag" data-value="御姐音">御姐音</span>'
                                        '<span class="preset-tag" data-value="磁性男声">磁性男声</span>'
                                        '<span class="preset-tag" data-value="低音炮">低音炮</span>'
                                        '<span class="preset-tag" data-value="少年音">少年音</span>'
                                        '<span class="preset-tag" data-value="日系甜音">日系甜音</span>'
                                        '</div>')
                                btn = gr.Button(I18N("generate_btn"), variant="primary", elem_classes=["primary-btn", "generate-btn"])
                                gr.HTML('<div style="text-align:center;margin-top:-8px;margin-bottom:8px;"><span class="kbd">Ctrl+Enter</span></div>')
                                gr.HTML('<hr class="divider">')
                                with gr.Row():
                                    p_n = gr.Textbox(label=I18N("save_name"), placeholder="输入音色名称用于固化", scale=3)
                                    s_b = gr.Button(I18N("save_persona"), elem_classes=["secondary-btn"], scale=1)
                                confirm_overwrite_b = gr.Button("确认覆盖", variant="stop", visible=False, elem_classes=["btn-danger"])
                            with gr.Tab(I18N("saved_voices")):
                                persona_d = gr.Dropdown(label=I18N("select_persona"), choices=get_persona_list(include_official=True), value=I18N("no_persona"), interactive=True)
                                desc_d = gr.Markdown(value="")
                                gr.HTML('<hr class="divider">')
                                with gr.Row():
                                    btn_ref_d = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"])
                                    btn_d = gr.Button(I18N("use_selected"), variant="primary", elem_classes=["primary-btn"])
                    gr.HTML('<hr class="divider">')
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon">🔊</span><h3 class="card-header-title">输出结果</h3></div>')
                        aud = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"])
                        msg = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                btn.click(fn_voice_design, [txt, lan, ins, output_format], [aud, msg])
                s_b.click(fn_save_persona, [p_n, aud, txt], [msg, confirm_overwrite_b])
                confirm_overwrite_b.click(fn=lambda n, a, t: fn_save_persona(n, a, t, overwrite=True), inputs=[p_n, aud, txt], outputs=[msg, confirm_overwrite_b])
                def update_desc_d(name):
                    if not name or name == "(暂无音色)": return ""
                    real = name
                    if name.startswith("[官方]"):
                        m = re.search(r'\((\w+)\)$', name); real = m.group(1) if m else name.replace("[官方] ", "").split(" (")[0]
                    return get_persona_desc(real)
                persona_d.change(update_desc_d, [persona_d], [desc_d])
                btn_ref_d.click(lambda: gr.update(choices=get_persona_list(include_official=True)), None, persona_d)
                btn_d.click(fn_voice_clone_with_persona, [txt, lan, persona_d, gr.State("1.7B")], [aud, msg])
            # Tab 2: 语音克隆
            with gr.Tab(I18N("tab_voice_clone"), id="语音克隆"):
                with gr.Column():
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon">🧬</span><h3 class="card-header-title">克隆设置</h3></div>')
                        size_c = gr.Radio(["1.7B", "0.6B"], label=I18N("model_size"), value="1.7B")
                        txt_c = gr.Textbox(label=I18N("synthesis_text"), value="你好，这是我的克隆声音。", lines=3, placeholder="请输入需要合成的文本...", elem_classes=["tts-input-textbox"])
                        lan_c = gr.Dropdown(_LANGS, label=I18N("language"), value="Auto", elem_classes=["tts-input-dropdown"])
                        with gr.Tabs(elem_classes=["inner-tabs"]):
                            with gr.Tab(I18N("saved_voices")):
                                persona_c = gr.Dropdown(label=I18N("select_persona"), choices=get_persona_list(include_official=True), value=I18N("no_persona"), interactive=True)
                                desc_c = gr.Markdown(value="")
                                gr.HTML('<hr class="divider">')
                                with gr.Row():
                                    btn_ref_p = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"])
                            with gr.Tab("上传新参考"):
                                ref_a = gr.Audio(label=I18N("ref_audio"), type="filepath")
                                ref_t = gr.Textbox(label=I18N("ref_text"), placeholder="请输入参考音频对应的文字内容...", lines=2)
                        gr.HTML('<hr class="divider">')
                        btn_c = gr.Button(I18N("clone_btn"), variant="primary", elem_classes=["primary-btn", "generate-btn"])
                        gr.HTML('<hr class="divider">')
                        with gr.Row():
                            p_nc = gr.Textbox(label=I18N("save_name"), placeholder="输入音色名称用于固化", scale=3)
                            s_bc = gr.Button(I18N("save_persona"), elem_classes=["secondary-btn"], scale=1)
                        confirm_overwrite_bc = gr.Button("确认覆盖", variant="stop", visible=False, elem_classes=["btn-danger"])
                    gr.HTML('<hr class="divider">')
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon">🔊</span><h3 class="card-header-title">输出结果</h3></div>')
                        aud_c = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"])
                        msg_c = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                def update_desc_c(name):
                    if not name or name == "(暂无音色)": return ""
                    real = name
                    if name.startswith("[官方]"):
                        m = re.search(r'\((\w+)\)$', name); real = m.group(1) if m else name.replace("[官方] ", "").split(" (")[0]
                    return get_persona_desc(real)
                persona_c.change(update_desc_c, [persona_c], [desc_c])
                btn_ref_p.click(lambda: gr.update(choices=get_persona_list(include_official=True)), None, persona_c)
                btn_c.click(fn_voice_clone_with_persona, [txt_c, lan_c, persona_c, size_c, output_format], [aud_c, msg_c])
                s_bc.click(fn_save_persona, [p_nc, ref_a, ref_t], [msg_c, confirm_overwrite_bc])
                confirm_overwrite_bc.click(fn=lambda n, a, t: fn_save_persona(n, a, t, overwrite=True), inputs=[p_nc, ref_a, ref_t], outputs=[msg_c, confirm_overwrite_bc])
            # Tab 3: 官方精品（卡片网格展示）
            with gr.Tab(I18N("tab_official"), id="官方精品"):
                with gr.Column():
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon">⭐</span><h3 class="card-header-title">官方精品音色</h3></div>')
                        size_v = gr.Radio(["1.7B", "0.6B"], label=I18N("model_size"), value="1.7B", elem_classes=["model-size-radio"])
                        txt_v = gr.TextArea(label=I18N("official_text_area"), lines=6, placeholder="普通文本直接使用上方音色选择，或使用 [角色名][情感指令]内容 格式生成对话...", elem_classes=["tts-input-textarea"])
                        lan_v = gr.Dropdown(_LANGS, label=I18N("language"), value="Auto", elem_classes=["tts-input-dropdown"])
                        # 音色筛选栏
                        gr.HTML('<div class="filter-bar">'
                            '<span class="filter-bar-label" data-i18n="filter_label">筛选:</span>'
                            '<span class="filter-chip active" data-filter="all" onclick="filterSpeaker(\'all\')" data-i18n="all">全部</span>'
                            '<span class="filter-chip" data-filter="female" onclick="filterSpeaker(\'female\')" data-i18n="female">女声</span>'
                            '<span class="filter-chip" data-filter="male" onclick="filterSpeaker(\'male\')" data-i18n="male">男声</span>'
                            '<span class="filter-chip" data-filter="sweet" onclick="filterSpeaker(\'sweet\')" data-i18n="sweet">甜美</span>'
                            '<span class="filter-chip" data-filter="mature" onclick="filterSpeaker(\'mature\')" data-i18n="mature">成熟</span>'
                            '<span class="filter-chip" data-filter="deep" onclick="filterSpeaker(\'deep\')" data-i18n="deep">低沉</span>'
                            '</div>')
                    # 音色卡片网格
                    speaker_grid_html = gr.HTML(value=generate_speaker_card_grid("Vivian"), elem_id="speaker-card-container")
                    # 隐藏的选中音色桥接组件（JS -> Python）
                    speaker_bridge = gr.Textbox(value="Vivian", elem_id="speaker-bridge-input", visible=False)
                    # 隐藏的选中音色值
                    selected_speaker_key = gr.State(value="Vivian")
                    # 音色详情面板
                    speaker_detail_html = gr.HTML(
                        value='<div class="speaker-detail-panel">'
                              '<h3>🎙️ 薇薇安 (Vivian)</h3>'
                              '<div class="detail-row"><span class="detail-label">音色类型</span><span class="detail-value">少女音</span></div>'
                              '<div class="detail-row"><span class="detail-label">声音特点</span><span class="detail-value">年轻活泼，语速轻快</span></div>'
                              '<div class="detail-row"><span class="detail-label">详细说明</span><span class="detail-value">甜美少女音，活泼热情，适合年轻女性角色配音。擅长日常对话和情感表达。</span></div>'
                              '</div>',
                        elem_id="speaker-detail-container"
                    )
                    with gr.Tabs(elem_classes=["inner-tabs"]):
                        with gr.Tab(I18N("saved_voices")):
                            persona_v = gr.Dropdown(label=I18N("select_persona"), choices=get_persona_list(), value=I18N("no_persona"), interactive=True)
                            desc_v = gr.Markdown(value="")
                            gr.HTML('<hr class="divider">')
                            with gr.Row():
                                btn_ref_v = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"])
                    gr.HTML('<hr class="divider">')
                    btn_v = gr.Button(I18N("official_btn"), variant="primary", elem_classes=["primary-btn", "generate-btn"])
                    gr.HTML('<div style="text-align:center;margin-top:-8px;margin-bottom:8px;"><span class="kbd">Ctrl+Enter</span></div>')
                    gr.HTML('<hr class="divider">')
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon">🔊</span><h3 class="card-header-title">输出结果</h3></div>')
                        aud_v = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"])
                        msg_v = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                # 官方精品事件绑定
                def update_speaker_detail(key):
                    """更新音色详情面板"""
                    info = OFFICIAL_SPEAKER_INFO.get(key, ("", "", "", ""))
                    return f'''<div class="speaker-detail-panel">
    <h3>🎙️ {info[0]} ({key})</h3>
    <div class="detail-row"><span class="detail-label">音色类型</span><span class="detail-value">{info[2]}</span></div>
    <div class="detail-row"><span class="detail-label">声音特点</span><span class="detail-value">{info[3]}</span></div>
    <div class="detail-row"><span class="detail-label">详细说明</span><span class="detail-value">{info[1]}</span></div>
</div>'''
                def update_speaker_info_v2(choice):
                    match = re.search(r'\((\w+)\)$', choice); key = match.group(1) if match else choice
                    info = OFFICIAL_SPEAKER_INFO.get(key, ("", "", "", ""))
                    return f"🎙️ **{info[0]} ({key})**\n\n**音色类型**：{info[2]}\n**声音特点**：{info[3]}\n\n**详细说明**：{info[1]}"
                def add_official_tag_v2(text, speaker):
                    match = re.search(r'\((\w+)\)$', speaker); s = match.group(1) if match else speaker
                    if not text.strip(): return text
                    return f"{text.rstrip()}\n[{s}] "
                def update_desc_v(name):
                    if not name or name == "(暂无音色)": return ""
                    return get_persona_desc(name)
                persona_v.change(update_desc_v, [persona_v], [desc_v])
                btn_ref_v.click(lambda: gr.update(choices=get_persona_list()), None, persona_v)
                # 卡片点击 -> 桥接 Textbox -> 同步 selected_speaker_key + 更新详情面板
                speaker_bridge.change(lambda x: (x, update_speaker_detail(x)), [speaker_bridge], [selected_speaker_key, speaker_detail_html])
                btn_v.click(fn_custom_voice_v2, [txt_v, lan_v, selected_speaker_key, gr.State(""), size_v, persona_v], [aud_v, msg_v])
            # Tab 4: 剧本工坊
            with gr.Tab(I18N("tab_script"), id="剧本工坊"):
                with gr.Row(equal_height=False):
                    with gr.Column(scale=2):
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon">📜</span><h3 class="card-header-title">剧本编辑器</h3></div>')
                                size_s = gr.Radio(["1.7B", "0.6B"], label=I18N("model_size"), value="1.7B")
                                script = gr.TextArea(label=I18N("script_content"), lines=12, value="[御姐] 欢迎！\n[旁白] 这里是多人剧本模式。", placeholder="格式: [音色名称] 台词内容\n每行一个角色，使用方括号标记说话人...", elem_classes=["tts-input-textarea"])
                                lan_s = gr.Dropdown(_LANGS, label=I18N("language"), value="Auto", elem_classes=["tts-input-dropdown"])
                                gr.HTML('<hr class="divider">')
                                btn_s = gr.Button("🎬 开始合成长剧本", variant="primary", elem_classes=["primary-btn", "generate-btn"])
                    with gr.Column(scale=1, min_width=280, elem_classes=["output-sidebar"]):
                        with gr.Group(elem_classes=["card"]):
                            gr.HTML('<div class="card-header"><span class="card-header-icon">🎭</span><h3 class="card-header-title">快速插入音色</h3></div>')
                            with gr.Tabs(elem_classes=["inner-tabs"]):
                                with gr.Tab(I18N("custom_voice")):
                                    p_list = gr.Dropdown(label=I18N("saved_voices"), choices=get_persona_list(), interactive=True)
                                with gr.Tab(I18N("official_voice_tab")):
                                    p_list_official = gr.Dropdown(label=I18N("official_voice_tab"), choices=_OFFICIAL_DISPLAY_NAMES, interactive=True)
                            btn_ref = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"])
                            gr.HTML('<hr class="divider">')
                            aud_s = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"])
                            msg_s = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                # 音色插入后自动聚焦剧本编辑器
                script_focus_html = gr.HTML(visible=False)
                def add_tag_and_focus(text, tag, is_speaker=True):
                    result = add_tag(text, tag, is_speaker)
                    # 注入 JS 将光标移到剧本编辑器末尾
                    focus_js = '<script>setTimeout(function(){var ta=document.querySelector("#剧本工坊 textarea.tts-input-textarea, [data-testid*=\"script\"] textarea");if(ta){ta.selectionStart=ta.selectionEnd=ta.value.length;ta.focus();}},300);</script>'
                    return result, focus_js
                p_list.input(lambda t, r: add_tag_and_focus(t, r, True), [script, p_list], [script, script_focus_html])
                p_list_official.input(lambda t, r: add_tag_and_focus(t, r, True), [script, p_list_official], [script, script_focus_html])
                btn_ref.click(lambda: gr.update(choices=get_persona_list()), None, p_list)
                btn_s.click(fn_script_studio, [script, lan_s, size_s], [aud_s, msg_s])
            # Tab 5: VoxCPM2 (contains 3 sub-tabs)
            with gr.Tab(I18N("tab_voxcpm2"), id="VoxCPM2"):
                with gr.Tabs(elem_classes=["inner-tabs"]):
                    # Sub-tab 5.1: VoxCPM2 声音设计
                    with gr.Tab(I18N("voxcpm_design")):
                        with gr.Column():
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon">✏️</span><h3 class="card-header-title">VoxCPM2 声音设计</h3></div>')
                                vox_design_txt = gr.Textbox(label=I18N("synthesis_text_vox"), value="你好，这是我用 VoxCPM2 生成的声音。", lines=3, placeholder="请输入需要合成的文本...")
                                vox_design_ins = gr.Textbox(label=I18N("control_instruction"), value="用温暖亲切的语气说话", lines=2, placeholder="如：用温暖亲切的语气说话、带有兴奋的情感、缓慢而沉稳的语速...")
                                vox_design_btn = gr.Button(I18N("generate_btn"), variant="primary", elem_classes=["primary-btn", "generate-btn"])
                            gr.HTML('<hr class="divider">')
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon">🔊</span><h3 class="card-header-title">输出结果</h3></div>')
                                vox_design_aud = gr.Audio(label=I18N("result_audio"))
                                vox_design_msg = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                        vox_design_btn.click(fn_voxcpm_design, [vox_design_txt, vox_design_ins], [vox_design_aud, vox_design_msg])
                    # Sub-tab 5.2: VoxCPM2 可控克隆
                    with gr.Tab(I18N("voxcpm_clone")):
                        with gr.Column():
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon">🧬</span><h3 class="card-header-title">可控克隆设置</h3></div>')
                                vox_clone_txt = gr.Textbox(label=I18N("synthesis_text_vox"), value="你好，这是我的克隆声音。", lines=3, placeholder="请输入需要合成的文本...")
                                vox_clone_ins = gr.Textbox(label=I18N("control_instruction"), value="用温暖亲切的语气说话", lines=2, placeholder="如：用温暖亲切的语气说话、带有兴奋的情感...")
                                with gr.Tabs(elem_classes=["inner-tabs"]):
                                    with gr.Tab(I18N("saved_voices")):
                                        vox_clone_persona = gr.Dropdown(label=I18N("select_persona"), choices=get_persona_list(include_official=True), value=I18N("no_persona"), interactive=True)
                                        vox_clone_persona_desc = gr.Markdown(value="")
                                        with gr.Row():
                                            vox_clone_persona_ref = gr.Button(I18N("save_name"), elem_classes=["secondary-btn"])
                                    with gr.Tab(I18N("ref_audio")):
                                        vox_clone_ref = gr.Audio(label=I18N("ref_audio"), type="filepath")
                                        vox_clone_ref_txt = gr.Textbox(label=I18N("ref_text"), placeholder="请输入参考音频对应的文字内容...", lines=2)
                                vox_clone_btn = gr.Button(I18N("generate_btn"), variant="primary", elem_classes=["primary-btn", "generate-btn"])
                            gr.HTML('<hr class="divider">')
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon">🔊</span><h3 class="card-header-title">输出结果</h3></div>')
                                vox_clone_aud = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"])
                                vox_clone_msg = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                        def update_vox_clone_persona(name):
                            if not name or name == "(暂无音色)": return ""
                            real = name.split(" (", 1)[0] if " (" in name else name
                            wav_path = os.path.join(PERSONA_DIR, f"{real}.wav")
                            txt_path = os.path.join(PERSONA_DIR, f"{real}.txt")
                            if os.path.exists(wav_path):
                                vox_clone_persona_ref.click(lambda: wav_path, None, vox_clone_ref)
                            if os.path.exists(txt_path):
                                try:
                                    with open(txt_path, "r", encoding="utf-8") as f: return f.read()
                                except: pass
                            return ""
                        vox_clone_persona.change(update_vox_clone_persona, [vox_clone_persona], [vox_clone_persona_desc])
                        vox_clone_btn.click(fn_voxcpm_clone, [vox_clone_txt, vox_clone_ins, vox_clone_ref], [vox_clone_aud, vox_clone_msg])
                    # Sub-tab 5.3: VoxCPM2 极致克隆
                    with gr.Tab(I18N("voxcpm_ultimate")):
                        with gr.Column():
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon">🔬</span><h3 class="card-header-title">极致克隆设置</h3></div>')
                                vox_ulti_txt = gr.Textbox(label=I18N("synthesis_text_vox"), value="你好，这是我的声音。", lines=3, placeholder="请输入需要合成的文本...")
                                vox_ulti_ins = gr.Textbox(label=I18N("control_instruction"), value="", lines=2, placeholder="如：用温暖亲切的语气说话...")
                                vox_ulti_ref = gr.Audio(label=I18N("ref_audio"), type="filepath")
                                gr.HTML('<hr class="divider">')
                                gr.Markdown("### 高级设置")
                                with gr.Accordion(I18N("advanced_settings"), open=False):
                                    with gr.Row():
                                        vox_ulti_cfg = gr.Slider(minimum=0.5, maximum=2.0, value=1.2, step=0.1, label=I18N("cfg_value"))
                                        vox_ulti_steps = gr.Slider(minimum=2, maximum=10, value=6, step=1, label=I18N("locdit_steps"))
                                    with gr.Row():
                                        vox_ulti_denoise = gr.Slider(minimum=0.0, maximum=1.0, value=1.0, step=0.1, label=I18N("denoise_strength"))
                                        vox_ulti_norm = gr.Checkbox(value=True, label=I18N("text_normalize"))
                                    vox_ulti_seed = gr.Slider(minimum=0, maximum=4294967295, value=0, step=1, label=I18N("randomness"), info="0为随机，其他值为固定种子")
                                vox_ulti_btn = gr.Button(I18N("generate_ultimate"), variant="primary", elem_classes=["primary-btn"])
                            gr.HTML('<hr class="divider">')
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon">🔊</span><h3 class="card-header-title">输出结果</h3></div>')
                                vox_ulti_aud = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"])
                                vox_ulti_msg = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                                vox_ulti_ref_text_display = gr.Markdown(value="")
                        vox_ulti_btn.click(fn_voxcpm_ultimate_clone,
                            [vox_ulti_txt, vox_ulti_ins, vox_ulti_ref, vox_ulti_cfg, vox_ulti_norm, vox_ulti_denoise, vox_ulti_steps, vox_ulti_seed],
                            [vox_ulti_aud, vox_ulti_ref_text_display])
            # Tab 6: 历史记录（增强筛选和试听）
            with gr.Tab(I18N("tab_history")):
                with gr.Group(elem_classes=["card"]):
                    gr.HTML('<div class="card-header"><span class="card-header-icon">📁</span><h3 class="card-header-title">生成历史</h3></div>')
                    total_count = get_total_history_count()
                    if total_count == 0:
                        gr.HTML('<div class="empty-state">'
                                '<span class="empty-state-icon">📭</span>'
                                '<p class="empty-state-text" data-i18n="history_empty_text">暂无生成记录</p>'
                                '<p style="font-size:13px;margin-bottom:16px;" data-i18n="history_empty_hint">合成音频后，历史记录将自动显示在这里</p>'
                                '<div class="empty-state-action">'
                                '<button class="secondary-btn" onclick="document.querySelector(\'[data-testid="🎨 声音设计"]\').click()" data-i18n="history_first_btn">🎨 开始首次合成</button>'
                                '</div></div>')
                    else:
                        # 改进的数量统计
                        gr.HTML(f'<div class="stat-card">'
                                '<span class="stat-card-icon">📜</span>'
                                '<div><div class="stat-card-value">{total_count}</div>'
                                '<div class="stat-card-label">条历史记录</div></div></div>')
                    # 搜索和筛选栏
                    gr.HTML('<div class="history-filters">'
                            '<span class="filter-bar-label" data-i18n="time_filter">时间:</span>'
                            '<span class="time-filter-chip active" data-time="all" onclick="filterHistoryTime(\'all\')" data-i18n="all">全部</span>'
                            '<span class="time-filter-chip" data-time="today" onclick="filterHistoryTime(\'today\')" data-i18n="today">今天</span>'
                            '<span class="time-filter-chip" data-time="week" onclick="filterHistoryTime(\'week\')" data-i18n="week">本周</span>'
                            '<span class="time-filter-chip" data-time="month" onclick="filterHistoryTime(\'month\')" data-i18n="month">本月</span>'
                            '</div>')
                    with gr.Row():
                        search_box = gr.Textbox(label=I18N("search_file"), placeholder="输入关键词进行模糊匹配...", lines=1, scale=4)
                        time_filter_hidden = gr.State(value="all")
                        with gr.Column(scale=1, min_width=200):
                            history_btn = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"])
                            clear_btn = gr.Button(I18N("clear_search"), elem_classes=["stop-btn"])
                    history_info = gr.Markdown(value="")
                    history_df = gr.Dataframe(
                        headers=["文件名", "生成时间", "时长", "大小"],
                        value=get_history_table_data(),
                        interactive=False
                    )
                    # 批量操作栏
                    gr.HTML('<div class="history-batch-bar">'
                            '<input type="checkbox" class="history-checkbox" id="select-all-history" onclick="toggleAllHistory(this.checked)">'
                            '<span style="font-size:12px;color:var(--text-muted);" data-i18n="select_all">全选</span>'
                            '<span style="flex:1"></span>'
                            '<button class="secondary-btn" style="font-size:11px;padding:4px 8px;" onclick="batchExportHistory()" data-i18n="batch_export">📦 批量导出</button>'
                            '<button class="stop-btn" style="font-size:11px;padding:4px 8px;" onclick="batchDeleteHistory()" data-i18n="batch_delete">🗑️ 批量删除</button>'
                            '</div>')
                    def search_history(keyword, time_filter):
                        results = get_history_table_data(keyword, time_filter)
                        count = len(results)
                        if results == [["暂无记录", "-", "-", "-"]]:
                            info = f"🔍 **无匹配结果** — 未找到包含 `{keyword}` 的文件" if keyword else ""
                        else:
                            info = f"🔍 找到 **{count}** 条匹配记录" if keyword else f"共 **{count}** 条记录"
                        return results, info
                    def clear_search():
                        return "", "all", get_history_table_data(), ""
                    search_box.input(lambda kw, tf: search_history(kw, tf), [search_box, time_filter_hidden], [history_df, history_info])
                    history_btn.click(lambda kw, tf: search_history(kw, tf), [search_box, time_filter_hidden], [history_df, history_info])
                    clear_btn.click(clear_search, None, [search_box, time_filter_hidden, history_df, history_info])
            # Tab 7: 音色库管理（增强试听和视图切换）
            with gr.Tab(I18N("tab_persona")):
                with gr.Group(elem_classes=["card"]):
                    gr.HTML('<div class="card-header"><span class="card-header-icon">🎙️</span><h3 class="card-header-title">音色库详情</h3></div>')
                    total_persona = get_total_persona_count()
                    if total_persona == 0:
                        gr.HTML('<div class="empty-state">'
                                '<span class="empty-state-icon">🎙️</span>'
                                '<p class="empty-state-text" data-i18n="persona_empty_text">暂无自定义音色</p>'
                                '<p style="font-size:13px;margin-bottom:16px;" data-i18n="persona_empty_hint">在"声音设计"或"语音克隆"中保存音色后，将显示在这里</p>'
                                '<div class="empty-state-action">'
                                '<button class="secondary-btn" onclick="document.querySelector(\'[data-testid="🎨 声音设计"]\').click()" data-i18n="persona_first_btn">🎨 创建首个音色</button>'
                                '</div></div>')
                    else:
                        # 改进的数量统计
                        gr.HTML(f'<div class="stat-card">'
                                '<span class="stat-card-icon">🎙️</span>'
                                '<div><div class="stat-card-value">{total_persona}</div>'
                                '<div class="stat-card-label">个自定义音色</div></div></div>')
                    # 搜索和视图切换
                    with gr.Row():
                        persona_search = gr.Textbox(label=I18N("search_persona"), placeholder="输入关键词进行模糊匹配...", lines=1, scale=4)
                        with gr.Column(scale=1, min_width=200):
                            gr.HTML('<div style="display:flex;align-items:center;gap:8px;">'
                                    '<div class="view-toggle">'
                                    '<span class="view-toggle-btn active" data-view="list" onclick="switchVoiceView(\'list\')" data-i18n="list">☰ 列表</span>'
                                    '<span class="view-toggle-btn" data-view="card" onclick="switchVoiceView(\'card\')" data-i18n="card">⊞ 卡片</span>'
                                    '</div></div>')
                    with gr.Row():
                        persona_search_btn = gr.Button("🔍 搜索", variant="primary", elem_classes=["primary-btn"], scale=1)
                        persona_clear_btn = gr.Button(I18N("clear_search"), elem_classes=["stop-btn"], scale=1)
                        btn_refresh_persona = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"], scale=1)
                    persona_search_info = gr.Markdown(value="")
                    # 列表视图
                    persona_df = gr.Dataframe(
                        headers=["音色名称", "固化状态", "音频大小", "创建时间", "参考文本"],
                        value=get_persona_detail_table(),
                        interactive=True,
                        elem_id="persona-list-view"
                    )
                    # 卡片视图（默认隐藏）
                    persona_card_grid = gr.HTML(value="", visible=False, elem_id="persona-card-view")
                    with gr.Row():
                        selected_persona = gr.Textbox(label=I18N("current_persona"), interactive=False)
                        preview_audio = gr.Audio(label=I18N("preview"), interactive=False)
                    with gr.Row():
                        btn_play = gr.Button(I18N("play_btn"), elem_classes=["secondary-btn"])
                        btn_delete = gr.Button(I18N("delete_btn"), elem_classes=["stop-btn"])
                    delete_status = gr.Markdown(value="")
                def on_persona_row_select(evt):
                    if evt and evt.value and len(evt.value) > 0:
                        return evt.value[0]
                    return ""
                def play_persona(name):
                    if not name or name == "暂无音色":
                        return None, "❌ 未选择有效音色"
                    wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
                    if not os.path.exists(wav_path):
                        return None, f"❌ 音频文件不存在: {name}"
                    try:
                        wav, sr = sf.read(wav_path)
                        return (sr, wav), f"🎵 正在播放: {name}"
                    except Exception as e:
                        return None, f"❌ 播放失败: {e}"
                def do_delete_persona(name):
                    if not name or name == "暂无音色":
                        return "❌ 未选择有效音色"
                    
                    # 输入验证
                    valid, err_msg = _validate_persona_name(name)
                    if not valid:
                        return f"❌ {err_msg}"
                    
                    try:
                        for ext in [".wav", ".txt", ".pt"]:
                            p = os.path.join(PERSONA_DIR, f"{name}{ext}")
                            p_real = os.path.realpath(p)
                            # 验证路径在 PERSONA_DIR 内
                            if not p_real.startswith(os.path.realpath(PERSONA_DIR)):
                                return "❌ 非法路径"
                            if os.path.exists(p):
                                os.remove(p)
                        if name in _persona_embedding_cache:
                            del _persona_embedding_cache[name]
                        return f"✅ 音色 [{name}] 已删除"
                    except Exception as e:
                        logger.error(f"删除音色失败: {e}")
                        return f"❌ 删除失败: {e}"
                persona_df.select(on_persona_row_select, None, selected_persona)
                btn_play.click(play_persona, [selected_persona], [preview_audio, delete_status])
                def delete_and_refresh(name):
                    status = do_delete_persona(name)
                    table = get_persona_detail_table()
                    return status, table
                btn_delete.click(delete_and_refresh, [selected_persona], [delete_status, persona_df])
                def search_persona(keyword):
                    results = get_persona_detail_table(keyword); count = len(results)
                    if results == [["暂无音色", "-", "-", "-", "-"]]:
                        info = f"🔍 **无匹配结果** — 未找到包含 `{keyword}` 的音色" if keyword else ""
                    else:
                        info = f"🔍 找到 **{count}** 个匹配音色" if keyword else f"共 **{count}** 个音色"
                    return results, info
                def clear_persona_search():
                    return "", get_persona_detail_table(), ""
                persona_search.input(search_persona, [persona_search], [persona_df, persona_search_info])
                persona_search_btn.click(search_persona, [persona_search], [persona_df, persona_search_info])
                persona_clear_btn.click(clear_persona_search, None, [persona_search, persona_df, persona_search_info])
        def on_tab_select(evt):
            tab_id = evt.value if evt.value else ""
            try:
                if tab_id == "剧本工坊": load_model("语音克隆")
                elif tab_id: load_model(tab_id)
            except Exception: pass
        main_tabs.select(on_tab_select)
        # 引擎切换状态标记（防止定时器覆盖错误状态）
        engine_switch_error = [False]  # 使用列表作为可变标记
        def refresh_status():
            # 如果引擎切换出错，不要覆盖错误信息
            if engine_switch_error[0]:
                return gr.update()  # 不更新 status_bar
            return '<span class="status-pulse"></span> **双引擎就绪 · 等待输入** | ' + _gen_tracker.status_text()
        try:
            timer = gr.Timer(value=2); timer.tick(refresh_status, None, status_bar)
        except (TypeError, AttributeError): pass
        # 进度条定时器刷新
        def refresh_progress():
            html = _progress_mgr.get_progress_html()
            return html
        try:
            progress_timer = gr.Timer(value=0.5)
            progress_timer.tick(refresh_progress, None, progress_bar)
        except (TypeError, AttributeError): pass
        # 引擎切换事件绑定
        def on_engine_change(engine_name):
            try:
                qwen_size = "1.7B" if "1.7B" in engine_name else "0.6B" if "0.6B" in engine_name else "1.7B"
                final_status = None

                # 重置错误标记
                engine_switch_error[0] = False

                # 切换期间禁用生成按钮（通过 JS 注入）
                disable_js = '<script>document.querySelectorAll(".primary-btn").forEach(function(b){b.disabled=true;b.style.opacity="0.5";});</script>'

                # 逐次消费生成器，取最后一次状态
                # 注意：生成器内部已包含完整异常处理，这里只负责消费状态
                try:
                    for step_result in switch_engine(engine_name, qwen_size):
                        # 生成器每次 yield (status_text, extra1, extra2, extra3)
                        if isinstance(step_result, tuple) and len(step_result) >= 1:
                            final_status = step_result[0]
                            logger.info(f"[UI回调] 步骤状态: {final_status}")
                        else:
                            final_status = str(step_result) if step_result is not None else "未知状态"
                            logger.info(f"[UI回调] 步骤状态: {final_status}")
                except GeneratorExit:
                    pass

                if final_status is None:
                    final_status = f"{engine_name} 加载完成"

                # 切换完成，启用生成按钮
                enable_js = '<script>document.querySelectorAll(".primary-btn").forEach(function(b){b.disabled=false;b.style.opacity="";});</script>'

                # 检查是否是错误状态
                is_error = any(kw in str(final_status) for kw in ['失败', '错误', '异常', '不足', '不存在'])
                engine_status_val = f"{engine_name} | {'就绪' if not is_error and '就绪' in str(final_status) else '错误'}"
                logger.info(f"[UI回调] 最终状态: {final_status}, 引擎显示: {engine_status_val}, 是否错误: {is_error}")

                # 如果是错误状态，设置错误标志防止定时器覆盖
                if is_error:
                    engine_switch_error[0] = True
                    # 返回错误信息，并在 status_bar 中显示完整错误
                    return f"❌ {final_status}", engine_status_val, enable_js
                else:
                    return final_status, engine_status_val, enable_js

            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                error_msg = f"引擎切换异常: {type(e).__name__}: {e}\n\n详细堆栈:\n{tb}"
                logger.error(f"[UI回调] 异常: {error_msg}")
                engine_status_val = f"{engine_name} | 错误"
                engine_switch_error[0] = True
                enable_js = '<script>document.querySelectorAll(".primary-btn").forEach(function(b){b.disabled=false;b.style.opacity="";});</script>'
                return f"❌ {error_msg}", engine_status_val, enable_js
        engine_btn_state = gr.HTML(value="", elem_classes=["engine-btn-state"], visible=True)
        engine_selector.change(on_engine_change, [engine_selector], [status_bar, engine_status_display, engine_btn_state])

        gr.HTML('<div class="enhanced-footer">'
                '<div class="footer-grid">'
                '<div><p class="footer-brand" data-i18n="footer_brand">🎙️ AI 语音工坊 Pro</p>'
                '<p style="color:var(--text-muted);font-size:13px;line-height:1.6;" data-i18n="footer_desc">集成 Qwen3TTS 与 VoxCPM2 双引擎，提供专业级语音合成、声音设计与多人剧本编辑能力。</p></div>'
                '<div><p class="footer-title" data-i18n="footer_features">核心功能</p>'
                '<span class="footer-link" data-i18n="tab_voice_design">🎨 声音设计</span><span class="footer-link" data-i18n="tab_voice_clone">👥 语音克隆</span><span class="footer-link" data-i18n="tab_official">🌟 官方精品</span><span class="footer-link" data-i18n="tab_script">🎬 剧本工坊</span></div>'
                '<div><p class="footer-title" data-i18n="footer_tech">技术栈</p>'
                '<span class="footer-link">Qwen3TTS 引擎</span><span class="footer-link">VoxCPM2 引擎</span><span class="footer-link">CUDA Graph 加速</span><span class="footer-link">Gradio UI</span></div>'
                '<div><p class="footer-title" data-i18n="footer_links">链接</p>'
                '<a class="footer-link" href="https://qwen.ai/blog?id=qwen3tts-0115" target="_blank" data-i18n="footer_blog">官方博客</a>'
                '<a class="footer-link" href="https://github.com/QwenLM" target="_blank">GitHub</a></div>'
                '</div>'
                '<div class="footer-bottom" data-i18n="footer_bottom">Powered by <strong>Qwen3TTS</strong> · VoxCPM2 · CUDA Graph 加速内核</div></div>')

    app, _, _ = demo.launch(
        server_name=ip, server_port=int(port),
        ssl_certfile="bin/cert.pem", ssl_keyfile="bin/key.pem", ssl_verify=False,
        prevent_thread_lock=True,
        i18n=I18N,
    )

    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(TTSError)
    async def tts_error_handler_api(request, exc):
        return JSONResponse({"status": "error", "error_code": exc.error_code, "message": str(exc)}, status_code=400)

    @app.post("/api/load_model")
    async def _api_load_model(request: Request):
        try:
            body = await request.json()
            m_type = body.get("m_type", "声音设计")
            size = body.get("size", "1.7B")
            resolved = MODEL_TYPE_ALIASES.get(m_type, m_type)
            m = load_model(resolved, size)
            if m is not None:
                return JSONResponse({"status": "ok", "message": f"Model loaded: {resolved} ({size})"})
            else:
                return JSONResponse({"status": "error", "message": "Model load returned None"})
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)})

    @app.post("/api/unload_model")
    async def _api_unload_model():
        try:
            unload_model()
            return JSONResponse({"status": "ok", "message": "Model unloaded, VRAM released"})
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)})

    @app.get("/api/model_status")
    async def _api_model_status():
        return JSONResponse({
            "loaded": current_model is not None,
            "type": current_type,
            "size": current_size,
        })

    @app.get("/api/persona_list")
    async def _api_persona_list():
        return JSONResponse({"personas": get_persona_list()})

    @app.delete("/api/persona/{name}")
    async def _api_delete_persona(name: str):
        if not re.match(r'^[a-zA-Z0-9_\-\u4e00-\u9fff]+$', name):
            return JSONResponse({"status": "error", "message": "Invalid persona name"})
        try:
            for ext in [".wav", ".txt", ".pt"]:
                p = os.path.join(PERSONA_DIR, f"{name}{ext}")
                real_path = os.path.realpath(p)
                if not real_path.startswith(os.path.realpath(PERSONA_DIR)):
                    return JSONResponse({"status": "error", "message": "Path traversal detected"})
                if os.path.exists(p): os.remove(p)
            if name in _persona_embedding_cache:
                del _persona_embedding_cache[name]
            return JSONResponse({"status": "ok", "message": f"音色 [{name}] 已删除"})
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)})

    @app.post("/api/generate")
    async def _api_generate(request: Request):
        try:
            body = await request.json()
            mode = body.get("mode", "voice_clone")
            text = body.get("text", "")
            lang = body.get("lang", "Auto")
            size = body.get("size", "1.7B")
            persona_name = body.get("persona_name", "(暂无音色)")
            speaker = body.get("speaker", "Vivian")
            instruct = body.get("instruct")
            ref_audio_path = body.get("ref_audio_path")
            output_format = body.get("format", "wav")

            if not text.strip():
                return JSONResponse({"status": "error", "message": "文本不能为空"}, status_code=400)

            _gen_tracker.start_generation()
            start_time = time.time()
            try:
                if mode in ("voice_clone", "clone"):
                    if persona_name and persona_name != "(暂无音色)":
                        audio_result, msg = fn_voice_clone_with_persona(text, lang, persona_name, size)
                    elif ref_audio_path and os.path.exists(ref_audio_path):
                        m = load_model("语音克隆", size)
                        al, sr = m.generate_voice_clone(text=text, language=lang, ref_audio=ref_audio_path, ref_text="")
                        save_audio(al[0], sr, f"api_clone_{size}", format=output_format)
                        audio_result = (sr, al[0])
                        msg = f"完成！({size}核心，上传音频)"
                    else:
                        return JSONResponse({"status": "error", "message": "需提供 persona_name 或 ref_audio_path"}, status_code=400)
                elif mode == "voice_design":
                    m = load_model("声音设计")
                    al, sr = m.generate_voice_design(text=text, language=lang, instruct=instruct)
                    save_audio(al[0], sr, "api_design", format=output_format)
                    audio_result = (sr, al[0])
                    msg = "生成成功！"
                elif mode in ("custom_voice", "official"):
                    m = load_model("官方精品", size)
                    al, sr = m.generate_custom_voice(text=text, language=lang, speaker=speaker.lower(), instruct=instruct)
                    save_audio(al[0], sr, f"api_custom_{speaker}", format=output_format)
                    audio_result = (sr, al[0])
                    msg = f"生成成功！({speaker})"
                else:
                    return JSONResponse({"status": "error", "message": f"未知模式: {mode}"}, status_code=400)

                elapsed = time.time() - start_time
                _gen_tracker.end_generation(elapsed)

                if audio_result is None:
                    return JSONResponse({"status": "error", "message": msg})

                sr_val, wav_val = audio_result
                audio_b64 = base64.b64encode(wav_val.tobytes()).decode() if wav_val is not None else None
                return JSONResponse({
                    "status": "ok",
                    "message": msg,
                    "elapsed": round(elapsed, 2),
                    "sample_rate": sr_val,
                    "audio_base64": audio_b64,
                    "format": output_format,
                })
            except TTSError as e:
                return JSONResponse({"status": "error", "error_code": e.error_code, "message": str(e)}, status_code=400)
            except Exception as e:
                return JSONResponse({"status": "error", "error_code": "UNKNOWN_ERROR", "message": str(e)}, status_code=500)
            finally:
                cleanup_temp_files()
        except Exception as e:
            return JSONResponse({"status": "error", "message": f"请求解析失败: {e}"}, status_code=400)

    @app.get("/api/persona_detail")
    async def _api_persona_detail(name: str):
        if not name:
            return JSONResponse({"personas": get_persona_list()}, status_code=400)
        desc = get_persona_desc(name)
        return JSONResponse({"name": name, "description": desc})

    cleanup_temp_files()

    while True:
        time.sleep(1)

if __name__ == "__main__":
    load_model("声音设计") 
    run_integrated("127.0.0.1", "7860")