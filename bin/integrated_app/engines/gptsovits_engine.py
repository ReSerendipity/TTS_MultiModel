"""GPT-SoVITS 引擎适配器模块。

**功能定位**：
    本模块实现 GPT-SoVITS 语音合成引擎的进程内适配器，是 TTS_MultiModel
    项目中支持**少样本 / 零样本语音克隆**的引擎之一。GPT-SoVITS 由 RVC-Boss
    团队开发，特点是：
    - 仅需 3~10 秒参考音频即可实现高质量零样本音色克隆
    - 支持中/英/日/韩/粤等多语种与跨语种合成
    - 通过 ``TTS_infer_pack`` 提供进程内推理管线（GPT s1 + SoVITS s2 双模型）

**架构角色**：
    :class:`GPTSoVITSEngine` 是 :class:`..engine_interface.TTSEngine` Protocol
    的具体实现类，遵循"构造轻量、``load()`` 重量加载"的声明式引擎契约，
    由 :func:`model_manager._load_generic_engine` 统一调度加载。

**进程内集成方式**：
    GPT-SoVITS 未发布为标准 pip 包，其推理代码位于项目
    ``reference_repos/GPT-SoVITS/`` 目录。本适配器在 :meth:`load` 时把该目录
    加入 ``sys.path`` 后懒导入 ``GPT_SoVITS.TTS_infer_pack.TTS``，
    权重从 ``pretrained_models/GPT-SoVITS/`` 读取。

**离线优先约束**：
    依赖缺失或权重缺失时，:meth:`load` 抛出带有清晰指引的 :class:`EngineLoadError`，
    引导用户运行 ``python scripts/download_gptsovits.py`` 下载权重，
    **绝不**在推理过程中自动联网下载。

**支持功能**：
    - ``generate_voice_clone``：零样本 / 少样本语音克隆（核心能力）
    - ``generate_streaming``：长文本分段流式合成
    - ``generate_voice_design`` / ``generate_script``：不支持，抛 NotImplementedError
"""

import logging
import os
import sys
import time
from typing import Any

from ..config import GPTSOVITS_MODEL_PATH, ROOT_DIR, SAVE_DIR
from ..engine_interface import TTSEngine
from ..exceptions import EngineLoadError, EngineNotLoadedError, GenerationError, ValidationError

logger = logging.getLogger("tts_multimodel")

#: GPT-SoVITS 推理代码所在目录（项目内 reference_repos 副本）。
_GPTSOVITS_REPO_DIR: str = os.path.join(ROOT_DIR, "reference_repos", "GPT-SoVITS")

#: GPT-SoVITS 支持的语言标签（TTS_infer_pack 的 text_lang / prompt_lang 取值）。
_LANG_MAP: dict[str, str] = {
    "zh": "all_zh",
    "en": "en",
    "ja": "all_ja",
    "ko": "all_ko",
    "yue": "all_yue",
    "auto": "auto",
}


class GPTSoVITSEngine(TTSEngine):
    """GPT-SoVITS 引擎适配器（进程内推理）。

    遵循 TTSEngine 协议的"无参构造 + 显式 ``load()``"契约：构造函数仅解析
    路径与设备，真正的权重加载在 :meth:`load` 中完成，便于调度层统一管理
    与测试 mock。

    Attributes:
        model_dir (str): GPT-SoVITS 权重根目录（``pretrained_models/GPT-SoVITS``）。
        device (str): 运行设备字符串（``"cuda"`` / ``"mps"`` / ``"cpu"``）。
        is_half (bool): 是否 FP16 半精度（仅 CUDA 下启用）。
        _pipeline (Any): 底层 ``GPT_SoVITS.TTS_infer_pack.TTS.TTS`` 实例，
            未加载时为 ``None``。
    """

    def __init__(self, model_dir: str | None = None) -> None:
        """初始化引擎（仅解析路径与设备，不加载权重）。

        Args:
            model_dir: 权重根目录；``None`` 时回退到 config 的 ``GPTSOVITS_MODEL_PATH``。
        """
        from ..gpu_backend import GPUBackend, GPUBackendManager

        self.model_dir: str = model_dir or GPTSOVITS_MODEL_PATH
        backend: GPUBackend = GPUBackendManager.detect_backend()
        if backend == GPUBackend.CUDA:
            self.device: str = "cuda"
            self.is_half: bool = True
        elif backend == GPUBackend.MPS:
            self.device = "mps"
            self.is_half = False
        else:
            self.device = "cpu"
            self.is_half = False
        self._pipeline: Any = None
        logger.info(
            f"[GPT-SoVITS] 初始化引擎: model_dir={self.model_dir}, "
            f"device={self.device}, is_half={self.is_half}"
        )

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        """检查引擎是否已加载就绪。

        Returns:
            bool: ``_pipeline`` 已初始化时返回 True。
        """
        return getattr(self, "_pipeline", None) is not None

    def _resolve_weights(self) -> dict[str, str]:
        """解析并校验 GPT-SoVITS 所需的权重文件路径。

        GPT-SoVITS 推理需要 4 类权重：
            - GPT（s1）自回归模型：``*.ckpt``（t2s_weights_path）
            - SoVITS（s2）声学模型：``*.pth``（vits_weights_path）
            - 中文 HuBERT：``chinese-hubert-base/``（cnhubert_base_path）
            - 中文 RoBERTa：``chinese-roberta-wwm-ext-large/``（bert_base_path）

        Returns:
            dict[str, str]: TTS_Config 所需的路径字典。

        Raises:
            EngineLoadError: 目录或任一必需权重缺失。
        """
        if not os.path.isdir(self.model_dir):
            raise EngineLoadError(
                f"GPT-SoVITS 模型目录不存在: {self.model_dir}\n"
                "请运行: python scripts/download_gptsovits.py 下载模型权重。",
                engine="gptsovits",
            )

        def _find(suffix: str) -> str:
            for root, _dirs, files in os.walk(self.model_dir):
                for fn in sorted(files):
                    if fn.endswith(suffix):
                        return os.path.join(root, fn)
            return ""

        gpt_path: str = _find(".ckpt")
        sovits_path: str = _find(".pth")
        cnhubert_dir: str = os.path.join(self.model_dir, "chinese-hubert-base")
        bert_dir: str = os.path.join(self.model_dir, "chinese-roberta-wwm-ext-large")

        missing: list[str] = []
        if not gpt_path:
            missing.append("GPT 权重 (*.ckpt)")
        if not sovits_path:
            missing.append("SoVITS 权重 (*.pth)")
        if not os.path.isdir(cnhubert_dir):
            missing.append("chinese-hubert-base/")
        if not os.path.isdir(bert_dir):
            missing.append("chinese-roberta-wwm-ext-large/")
        if missing:
            raise EngineLoadError(
                f"GPT-SoVITS 权重不完整，缺失: {missing}\n"
                "请运行: python scripts/download_gptsovits.py 下载模型权重。",
                engine="gptsovits",
            )

        return {
            "device": self.device,
            "is_half": self.is_half,
            "version": "v2",
            "t2s_weights_path": gpt_path,
            "vits_weights_path": sovits_path,
            "cnhuhbert_base_path": cnhubert_dir,
            "bert_base_path": bert_dir,
        }

    def load(self) -> None:
        """加载 GPT-SoVITS 推理管线（进程内）。

        流程：
            1. 校验权重完整性（:meth:`_resolve_weights`）。
            2. 将 reference_repos/GPT-SoVITS 加入 sys.path 并懒导入 TTS_infer_pack。
            3. 用权重路径构造 ``TTS_Config`` 与 ``TTS`` 管线。

        Raises:
            EngineLoadError: 权重缺失、推理代码缺失或管线初始化失败。
        """
        if self.is_ready():
            return

        weights: dict[str, str] = self._resolve_weights()

        if not os.path.isdir(_GPTSOVITS_REPO_DIR):
            raise EngineLoadError(
                f"未找到 GPT-SoVITS 推理代码目录: {_GPTSOVITS_REPO_DIR}",
                engine="gptsovits",
            )
        if _GPTSOVITS_REPO_DIR not in sys.path:
            sys.path.insert(0, _GPTSOVITS_REPO_DIR)

        try:
            from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config
        except ImportError as e:
            raise EngineLoadError(
                "GPT-SoVITS 依赖未安装或推理代码不可导入。\n"
                "请安装其依赖: pip install -r reference_repos/GPT-SoVITS/requirements.txt\n"
                f"原始错误: {e}",
                engine="gptsovits",
            ) from e

        logger.info("[GPT-SoVITS] 开始加载推理管线...")
        start: float = time.time()
        try:
            tts_config: Any = TTS_Config({"custom": weights})
            self._pipeline = TTS(tts_config)
        except Exception as e:
            self._pipeline = None
            raise EngineLoadError(
                f"GPT-SoVITS 管线初始化失败: {type(e).__name__}: {e}",
                engine="gptsovits",
            ) from e
        logger.info(f"[GPT-SoVITS] 推理管线加载完成，耗时 {time.time() - start:.1f}s")

    def unload(self) -> None:
        """卸载模型并释放显存（幂等）。"""
        logger.info("[GPT-SoVITS] 开始卸载模型...")
        try:
            if getattr(self, "_pipeline", None) is not None:
                del self._pipeline
            self._pipeline = None
            import gc

            gc.collect()
            from ..gpu_backend import GPUBackend, GPUBackendManager

            if GPUBackendManager.detect_backend() != GPUBackend.CPU:
                GPUBackendManager.empty_cache()
        except Exception as e:
            logger.exception(f"[GPT-SoVITS] 卸载异常（已忽略）: {e}")
        logger.info("[GPT-SoVITS] 模型卸载完成")

    # ------------------------------------------------------------------
    # 推理
    # ------------------------------------------------------------------

    def _run(self, req: dict[str, Any]) -> tuple[int, Any]:
        """执行一次推理，返回 (采样率, 波形 ndarray)。

        Args:
            req: TTS_infer_pack.run 所需的请求字典。

        Returns:
            tuple[int, Any]: (sample_rate, audio_ndarray)。

        Raises:
            GenerationError: 推理管线未产出音频或运行异常。
        """
        try:
            generator: Any = self._pipeline.run(req)
            sr, audio = next(generator)
            return sr, audio
        except StopIteration as e:
            raise GenerationError("GPT-SoVITS 推理未产出音频") from e
        except Exception as e:
            raise GenerationError(
                f"GPT-SoVITS 推理失败: {type(e).__name__}: {e}"
            ) from e

    def generate_voice_clone(
        self,
        text: str,
        reference_audio_path: str | None = None,
        instruction: str = "",
        normalize: bool = True,
        **kwargs: Any,
    ) -> tuple[Any, str]:
        """零样本 / 少样本语音克隆（TTSEngine 协议实现）。

        Args:
            text: 待合成文本。
            reference_audio_path: 说话人参考音频路径（必需）。
            instruction: 参考音频对应转写文本（prompt_text）。留空则走纯音色克隆。
            normalize: 兼容参数（GPT-SoVITS 内部处理，此处占位）。
            **kwargs: 额外参数：``text_lang`` / ``prompt_lang``（默认 zh）、
                ``text_split_method``（默认 cut5）、``top_k`` / ``top_p`` /
                ``temperature`` / ``speed_factor`` 等，透传给推理管线。

        Returns:
            tuple[Any, str]: ``(输出音频路径, 结果消息)``。

        Raises:
            EngineNotLoadedError: 引擎未就绪。
            ValueError: 未提供参考音频。
            GenerationError: 推理失败。
        """
        if not self.is_ready():
            raise EngineNotLoadedError("GPT-SoVITS 引擎未加载", engine="gptsovits")
        if not reference_audio_path:
            raise ValueError("GPT-SoVITS generate_voice_clone 需要 reference_audio_path")

        text_lang_raw: str = kwargs.pop("text_lang", "zh")
        prompt_lang_raw: str = kwargs.pop("prompt_lang", "zh")
        # pyopenjtalk 在 Python 3.12 + Windows MSVC 下无法编译，日语 tokenization 不可用。
        # 短期降级：检测到 ja 时返回友好错误，避免静默走中文 tokenization 导致发音错误。
        if text_lang_raw == "ja" or prompt_lang_raw == "ja":
            raise ValidationError(
                "日语 TTS 暂不可用：pyopenjtalk 在当前 Python 3.12 + Windows 环境下无法编译。"
                "请使用中/英/韩/粤等其他语言，或等待上游 pyopenjtalk 修复 Python 3.12 兼容性。",
                field="text_lang",
            )
        text_lang: str = _LANG_MAP.get(text_lang_raw, "auto")
        prompt_lang: str = _LANG_MAP.get(prompt_lang_raw, "auto")
        req: dict[str, Any] = {
            "text": text,
            "text_lang": text_lang,
            "ref_audio_path": reference_audio_path,
            "prompt_text": instruction or "",
            "prompt_lang": prompt_lang,
            "text_split_method": kwargs.pop("text_split_method", "cut5"),
            "return_fragment": False,
            "streaming_mode": False,
        }
        req.update(kwargs)

        sr, audio = self._run(req)
        output_path: str = self._save_wav(audio, sr, prefix="gptsovits_clone")
        return output_path, f"GPT-SoVITS 克隆完成: {output_path}"

    def generate_streaming(
        self,
        text: str,
        reference_audio_path: str | None = None,
        **kwargs: Any,
    ):
        """长文本分段流式合成。

        Args:
            text: 待合成长文本。
            reference_audio_path: 参考音频路径（必需）。
            **kwargs: 同 :meth:`generate_voice_clone`，另加 ``prompt_text``。

        Yields:
            tuple[Any, str]: 每段 ``(音频路径, 状态消息)``。

        Raises:
            EngineNotLoadedError: 引擎未就绪。
            ValueError: 未提供参考音频。
        """
        if not self.is_ready():
            raise EngineNotLoadedError("GPT-SoVITS 引擎未加载", engine="gptsovits")
        if not reference_audio_path:
            raise ValueError("GPT-SoVITS generate_streaming 需要 reference_audio_path")

        text_lang_raw: str = kwargs.pop("text_lang", "zh")
        prompt_lang_raw: str = kwargs.pop("prompt_lang", "zh")
        if text_lang_raw == "ja" or prompt_lang_raw == "ja":
            raise ValidationError(
                "日语 TTS 暂不可用：pyopenjtalk 在当前 Python 3.12 + Windows 环境下无法编译。"
                "请使用中/英/韩/粤等其他语言。",
                field="text_lang",
            )
        text_lang: str = _LANG_MAP.get(text_lang_raw, "auto")
        prompt_lang: str = _LANG_MAP.get(prompt_lang_raw, "auto")
        prompt_text: str = kwargs.pop("prompt_text", "")
        req: dict[str, Any] = {
            "text": text,
            "text_lang": text_lang,
            "ref_audio_path": reference_audio_path,
            "prompt_text": prompt_text,
            "prompt_lang": prompt_lang,
            "text_split_method": kwargs.pop("text_split_method", "cut5"),
            "return_fragment": True,
            "streaming_mode": True,
        }
        req.update(kwargs)

        idx: int = 0
        try:
            for sr, chunk in self._pipeline.run(req):
                idx += 1
                path: str = self._save_wav(chunk, sr, prefix=f"gptsovits_stream_{idx}")
                yield path, f"已生成第 {idx} 段"
        except Exception as e:
            raise GenerationError(
                f"GPT-SoVITS 流式推理失败: {type(e).__name__}: {e}"
            ) from e

    def generate_voice_design(
        self, text: str, instruction: str = "", normalize: bool = True, **kwargs: Any
    ) -> tuple[Any, str]:
        """语音设计（GPT-SoVITS 不支持）。

        Raises:
            NotImplementedError: 始终抛出，提示切换到 VoxCPM2。
        """
        raise NotImplementedError(
            "GPT-SoVITS 不支持语音设计，请切换到 VoxCPM2 引擎。"
        )

    def generate_script(
        self,
        text: str,
        speaker_map: dict[str, Any] | None = None,
        persona_map: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[Any, str]:
        """剧本工坊（GPT-SoVITS 不支持）。

        Raises:
            NotImplementedError: 始终抛出。
        """
        raise NotImplementedError(
            "GPT-SoVITS 不支持剧本工坊，请切换到 VoxCPM2 引擎。"
        )

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _save_wav(audio: Any, sample_rate: int, prefix: str = "gptsovits") -> str:
        """将波形数据写入 SAVE_DIR 下的时间戳 WAV 文件。

        Args:
            audio: 波形数据（numpy ndarray，int16 或 float）。
            sample_rate: 采样率 (Hz)。
            prefix: 输出文件名前缀。

        Returns:
            str: 保存的 WAV 文件绝对路径。
        """
        import soundfile as sf

        os.makedirs(SAVE_DIR, exist_ok=True)
        output_path: str = os.path.join(SAVE_DIR, f"{prefix}_{int(time.time() * 1000)}.wav")
        sf.write(output_path, audio, sample_rate)
        return output_path

    @property
    def version(self) -> str:
        """引擎版本标识。"""
        return "GPT-SoVITS v2"
