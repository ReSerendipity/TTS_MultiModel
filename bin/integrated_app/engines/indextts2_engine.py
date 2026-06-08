# -*- coding: utf-8 -*-
"""IndexTTS 2.0 Engine Adapter for TTS MultiModel.

Provides a unified interface for IndexTTS 2.0 inference, supporting:
- Zero-shot voice cloning
- Emotion control (audio prompt, vector, text)
- Duration control
- Multi-backend GPU support (CUDA/ROCM/XPU/MPS/CPU)
"""

import os
import gc
import time
import logging
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger("tts_multimodel")


class IndexTTS2Engine:
    """IndexTTS 2.0 引擎适配器

    封装 IndexTTS 2.0 推理接口，提供统一的 API 供 TTS MultiModel 使用。
    支持零样本语音克隆、情感控制和时长控制。

    系统要求:
        - 最低配置: 6GB 显存 + 16GB 内存 (GPU 模式)
        - 推荐配置: 8GB+ 显存 + 16GB+ 内存
        - CPU 模式: 较慢，但可用
    """

    # 情感维度定义 (8维情感向量)
    EMOTION_DIMENSIONS = [
        "happy",       # 开心
        "angry",       # 愤怒
        "sad",         # 悲伤
        "afraid",      # 害怕
        "disgusted",   # 厌恶
        "melancholic", # 忧郁
        "surprised",   # 惊讶
        "calm",        # 平静
    ]

    def __init__(
        self,
        model_dir: Optional[str] = None,
        use_fp16: bool = True,
        device: Optional[str] = None,
        use_deepspeed: bool = False,
    ):
        """初始化 IndexTTS 2.0 引擎

        Args:
            model_dir: 模型文件目录路径
            use_fp16: 是否使用 FP16 精度（降低显存占用约50%）
            device: 指定运行设备 ("cuda", "xpu", "mps", "cpu")，None 则自动检测
            use_deepspeed: 是否启用 DeepSpeed 加速（需额外安装 DeepSpeed）
        """
        from ..gpu_backend import GPUBackendManager, GPUBackend

        # 确定模型路径
        if model_dir is None:
            project_root = Path(__file__).parent.parent.parent
            model_dir = str(project_root / "pretrained_models" / "IndexTTS2")

        self.model_dir = model_dir
        self.use_deepspeed = use_deepspeed

        # 自动检测设备
        self.backend = GPUBackendManager.detect_backend()
        if device:
            self.device = device
        else:
            if self.backend == GPUBackend.CUDA or self.backend == GPUBackend.ROCM:
                self.device = "cuda"
                # MPS 不支持 FP16，CPU 不需要 FP16
                self.use_fp16 = use_fp16 and self.backend != GPUBackend.CPU
            elif self.backend == GPUBackend.XPU:
                self.device = "xpu"
                self.use_fp16 = use_fp16
            elif self.backend == GPUBackend.MPS:
                self.device = "mps"
                self.use_fp16 = False  # MPS 不支持 FP16
            else:
                self.device = "cpu"
                self.use_fp16 = False

        logger.info(
            f"[IndexTTS2] 初始化引擎: model_dir={self.model_dir}, "
            f"device={self.device}, fp16={self.use_fp16}, "
            f"backend={self.backend.value}, deepspeed={self.use_deepspeed}"
        )

        # 验证模型文件
        self._validate_model_files()

        # 加载模型
        self._load_model()

    def _validate_model_files(self):
        """验证必需的模型文件是否存在"""
        required_files = [
            "gpt.pth",
            "s2mel.pth",
            "bpe.model",
            "config.yaml",
            "feat1.pt",
            "feat2.pt",
            "wav2vec2bert_stats.pt",
            "configuration.json",
        ]

        missing_files = []
        for filename in required_files:
            filepath = os.path.join(self.model_dir, filename)
            if not os.path.exists(filepath):
                missing_files.append(filename)

        if missing_files:
            raise FileNotFoundError(
                f"IndexTTS 2.0 模型文件缺失: {missing_files}\n"
                f"请运行: python scripts/download_indextts2.py 下载模型"
            )

        logger.info(f"[IndexTTS2] 模型文件验证通过: {self.model_dir}")

    def _load_model(self):
        """加载 IndexTTS 2.0 模型"""
        try:
            from indextts.infer_v2 import IndexTTS2
        except ImportError:
            raise ImportError(
                "indextts 未安装，请运行: pip install indextts\n"
                "或参考: https://github.com/index-tts/index-tts"
            )

        config_path = os.path.join(self.model_dir, "config.yaml")

        logger.info("[IndexTTS2] 开始加载模型...")
        start_time = time.time()

        try:
            self.tts = IndexTTS2(
                cfg_path=config_path,
                model_dir=self.model_dir,
                use_fp16=self.use_fp16,
                use_cuda_kernel=False,  # 默认关闭，可手动开启
                use_deepspeed=self.use_deepspeed,
            )
        except Exception as e:
            logger.error(f"[IndexTTS2] 模型加载失败: {e}")
            raise

        load_time = time.time() - start_time
        logger.info(f"[IndexTTS2] 模型加载完成，耗时: {load_time:.1f}秒")

        # 移动模型到指定设备
        self._move_to_device()

        # 打印显存信息
        if self.backend.value != "cpu":
            self._log_memory_info()

    def _move_to_device(self):
        """将模型组件移动到指定设备"""
        device_str = self.device

        components_moved = []
        for attr in ['gpt', 's2mel', 'vocoder', 'codec']:
            sub = getattr(self.tts, attr, None)
            if sub is not None and hasattr(sub, 'to'):
                try:
                    sub.to(device_str)
                    components_moved.append(attr)
                    logger.debug(f"[IndexTTS2] {attr} -> {device_str}")
                except Exception as e:
                    logger.warning(f"[IndexTTS2] 移动 {attr} 到 {device_str} 失败: {e}")

        if components_moved:
            logger.info(f"[IndexTTS2] 已移动组件到 {device_str}: {', '.join(components_moved)}")

    def _log_memory_info(self):
        """记录显存使用情况"""
        try:
            from ..gpu_backend import GPUBackendManager

            mem_info = GPUBackendManager.get_memory_info()
            total_gb = mem_info[0] / (1024 ** 3)
            allocated_gb = mem_info[1] / (1024 ** 3)
            free_gb = mem_info[3] / (1024 ** 3)

            logger.info(
                f"[IndexTTS2] 显存状态: 总计 {total_gb:.2f}GB, "
                f"已分配 {allocated_gb:.2f}GB, 可用 {free_gb:.2f}GB"
            )
        except Exception as e:
            logger.debug(f"[IndexTTS2] 获取显存信息失败: {e}")

    def infer(
        self,
        text: str,
        spk_audio_prompt: str,
        output_path: Optional[str] = None,
        emo_audio_prompt: Optional[str] = None,
        emo_alpha: float = 0.8,
        emo_vector: Optional[List[float]] = None,
        emo_text: Optional[str] = None,
        use_emo_text: bool = False,
        target_duration: Optional[float] = None,
        seed: Optional[int] = None,
        **kwargs
    ) -> str:
        """执行语音合成

        Args:
            text: 要合成的文本内容
            spk_audio_prompt: 说话人参考音频文件路径（用于语音克隆）
            output_path: 输出音频文件路径（可选，默认创建临时文件）
            emo_audio_prompt: 情感参考音频文件路径（可选）
            emo_alpha: 情感强度，范围 0.0-1.0，默认 0.8
            emo_vector: 8维情感向量 [happy, angry, sad, afraid, disgusted, melancholic, surprised, calm]
            emo_text: 情感描述文本（如 "非常开心的语气"）
            use_emo_text: 是否使用文本情感描述模式
            target_duration: 目标时长（秒），IndexTTS 2.0 支持精确时长控制
            seed: 随机种子（可选，用于复现结果）
            **kwargs: 其他传递给 IndexTTS 的参数

        Returns:
            输出音频文件路径

        Raises:
            RuntimeError: 推理过程中发生错误
        """
        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".wav", prefix="indextts2_")
            os.close(fd)

        logger.info(
            f"[IndexTTS2] 开始合成: text='{text[:50]}...', "
            f"output={output_path}, "
            f"emo_alpha={emo_alpha}, "
            f"target_duration={target_duration}"
        )

        try:
            # 构建推理参数
            infer_kwargs = {
                "spk_audio_prompt": spk_audio_prompt,
                "text": text,
                "output_path": output_path,
                "verbose": False,
            }

            # 情感控制参数
            if emo_audio_prompt and os.path.exists(emo_audio_prompt):
                infer_kwargs["emo_audio_prompt"] = emo_audio_prompt
            if emo_vector:
                if len(emo_vector) != 8:
                    logger.warning(
                        f"[IndexTTS2] emo_vector 应为 8 维，当前为 {len(emo_vector)} 维"
                    )
                else:
                    infer_kwargs["emo_vector"] = emo_vector
            if emo_text:
                infer_kwargs["emo_text"] = emo_text
            if use_emo_text:
                infer_kwargs["use_emo_text"] = True

            infer_kwargs["emo_alpha"] = emo_alpha

            # 时长控制
            if target_duration and target_duration > 0:
                infer_kwargs["target_duration"] = target_duration

            # 随机种子
            if seed is not None:
                infer_kwargs["seed"] = seed

            # 调用 IndexTTS 2.0 推理
            self.tts.infer(**infer_kwargs)

            # 验证输出文件
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                logger.info(f"[IndexTTS2] 合成完成: {output_path} ({file_size / 1024:.1f} KB)")
            else:
                logger.error(f"[IndexTTS2] 输出文件未生成: {output_path}")

            return output_path

        except Exception as e:
            logger.error(f"[IndexTTS2] 合成失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise RuntimeError(f"IndexTTS 2.0 合成失败: {e}") from e

    def get_memory_info(self) -> Dict[str, float]:
        """获取显存使用情况

        Returns:
            包含显存信息的字典 (单位: GB)
        """
        from ..gpu_backend import GPUBackendManager, GPUBackend

        if self.backend == GPUBackend.CPU:
            return {
                "total_gb": 0,
                "allocated_gb": 0,
                "reserved_gb": 0,
                "free_gb": 0,
                "device": "cpu",
            }

        mem_info = GPUBackendManager.get_memory_info()
        return {
            "total_gb": mem_info[0] / (1024 ** 3),
            "allocated_gb": mem_info[1] / (1024 ** 3),
            "reserved_gb": mem_info[2] / (1024 ** 3),
            "free_gb": mem_info[3] / (1024 ** 3),
            "device": self.device,
        }

    def is_ready(self) -> bool:
        return hasattr(self, 'tts') and self.tts is not None

    def load(self) -> None:
        self._load_model()

    def unload(self):
        """卸载模型释放显存/内存"""
        logger.info("[IndexTTS2] 开始卸载模型...")

        if hasattr(self, 'tts'):
            # 删除所有模型组件引用
            for attr in ['gpt', 's2mel', 'vocoder', 'codec']:
                sub = getattr(self.tts, attr, None)
                if sub is not None:
                    del sub
            del self.tts
            self.tts = None

        gc.collect()

        # 清理 GPU 缓存
        from ..gpu_backend import GPUBackendManager, GPUBackend
        if self.backend != GPUBackend.CPU:
            GPUBackendManager.synchronize()
            GPUBackendManager.empty_cache()
            GPUBackendManager.ipc_collect()

        logger.info("[IndexTTS2] 模型卸载完成")

    @staticmethod
    def build_emotion_vector(
        happy: float = 0.0,
        angry: float = 0.0,
        sad: float = 0.0,
        afraid: float = 0.0,
        disgusted: float = 0.0,
        melancholic: float = 0.0,
        surprised: float = 0.0,
        calm: float = 0.0,
    ) -> List[float]:
        """构建 8 维情感向量

        Args:
            各情感维度的强度值 (0.0-1.0)

        Returns:
            8维情感向量列表
        """
        return [
            max(0.0, min(1.0, happy)),
            max(0.0, min(1.0, angry)),
            max(0.0, min(1.0, sad)),
            max(0.0, min(1.0, afraid)),
            max(0.0, min(1.0, disgusted)),
            max(0.0, min(1.0, melancholic)),
            max(0.0, min(1.0, surprised)),
            max(0.0, min(1.0, calm)),
        ]

    @staticmethod
    def get_preset_emotions() -> Dict[str, List[float]]:
        """获取预设情感模板

        Returns:
            情感名称到情感向量的映射字典
        """
        return {
            "neutral": IndexTTS2Engine.build_emotion_vector(calm=0.5),
            "happy": IndexTTS2Engine.build_emotion_vector(happy=0.8),
            "angry": IndexTTS2Engine.build_emotion_vector(angry=0.8),
            "sad": IndexTTS2Engine.build_emotion_vector(sad=0.8),
            "surprised": IndexTTS2Engine.build_emotion_vector(surprised=0.8),
            "calm": IndexTTS2Engine.build_emotion_vector(calm=0.8),
            "melancholic": IndexTTS2Engine.build_emotion_vector(melancholic=0.8),
            "excited": IndexTTS2Engine.build_emotion_vector(happy=0.6, surprised=0.4),
            "gentle": IndexTTS2Engine.build_emotion_vector(calm=0.6, happy=0.3),
            "whisper": IndexTTS2Engine.build_emotion_vector(calm=0.9),
        }

    @property
    def version(self) -> str:
        """返回引擎版本信息"""
        return "IndexTTS 2.0"

    @property
    def min_vram_gb(self) -> float:
        """返回最低显存需求 (GB)"""
        return 6.0

    @property
    def min_ram_gb(self) -> float:
        """返回最低内存需求 (GB)"""
        return 16.0

    def generate_voice_design(
        self,
        text: str,
        instruction: str = "",
        normalize: bool = True,
    ):
        raise NotImplementedError(
            "Voice design is not supported by IndexTTS2 engine. "
            "Please switch to VoxCPM2 engine for voice design features."
        )

    def generate_voice_clone(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        instruction: str = "",
        normalize: bool = True,
        **kwargs,
    ):
        raise NotImplementedError(
            "Voice clone is not supported by IndexTTS2 engine. "
            "Please switch to VoxCPM2 engine for voice clone features."
        )

    def generate_script(
        self,
        text: str,
        speaker_map: dict,
        persona_map: dict = None,
        **kwargs,
    ):
        raise NotImplementedError(
            "Script generation is not supported by IndexTTS2 engine. "
            "Please switch to VoxCPM2 engine for script generation features."
        )

    def generate_streaming(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        **kwargs,
    ):
        raise NotImplementedError(
            "Streaming generation is not supported by IndexTTS2 engine. "
            "Please switch to VoxCPM2 engine for streaming features."
        )
