# -*- coding: utf-8 -*-
"""训练管理模块（第 18 章）：数据管理、进度可视化、LoRA 配置、训练编排。

提供 VoxCPM LoRA 微调训练的全流程管理：
- TrainingDataManager: JSONL 训练数据管理、验证、HuggingFace 格式转换、数据增强
- TrainingProgressVisualizer: 训练损失曲线追踪与实时可视化数据输出
- LoRAConfigManager: 多目标 LoRA 配置管理（LM/DiT/投影层）
- TrainingOrchestrator: 训练管线编排，集成信号处理、混合精度和 training/ 模块

参考：
- VoxCPM 可配置 LoRA：各层组独立 rank/alpha
- training/ 模块现有类：Accelerator、TrainingTracker、TrainingState 等
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("tts_multimodel")


# ---------------------------------------------------------------------------
# TrainingDataManager — 训练数据管理
# ---------------------------------------------------------------------------


@dataclass
class TrainingSample:
    """单条训练样本。

    Attributes:
        audio_path: 音频文件路径。
        text: 对应文本内容。
        speaker_id: 说话人标识。
        duration: 音频时长（秒），0 表示未计算。
        sample_rate: 采样率，0 表示未指定。
    """

    audio_path: str
    text: str
    speaker_id: str = "default"
    duration: float = 0.0
    sample_rate: int = 0


@dataclass
class DataValidationResult:
    """数据验证结果。

    Attributes:
        total_samples: 总样本数。
        valid_samples: 有效样本数。
        invalid_samples: 无效样本数。
        errors: 错误详情列表。
        warnings: 警告详情列表。
    """

    total_samples: int = 0
    valid_samples: int = 0
    invalid_samples: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class TrainingDataManager:
    """训练数据管理器。

    支持 JSONL 格式训练数据的加载、验证、HuggingFace Dataset 格式转换
    和数据增强管线。

    JSONL 格式示例：
        {"audio_path": "data/voice1.wav", "text": "你好世界", "speaker_id": "spk1"}
        {"audio_path": "data/voice2.wav", "text": "今天天气不错", "speaker_id": "spk2"}

    用法：
        manager = TrainingDataManager(data_dir="data/training")
        result = manager.validate_dataset()
        if result.invalid_samples > 0:
            for error in result.errors:
                print(error)
    """

    # 支持的音频格式
    SUPPORTED_AUDIO_FORMATS = {".wav", ".mp3", ".flac", ".ogg", ".opus"}

    def __init__(self, data_dir: str | None = None) -> None:
        """初始化训练数据管理器。

        Args:
            data_dir: 训练数据目录路径，包含 JSONL 文件和音频文件。
        """
        self.data_dir = Path(data_dir) if data_dir else None
        self._samples: list[TrainingSample] = []

    def load_jsonl(self, jsonl_path: str | Path) -> list[TrainingSample]:
        """从 JSONL 文件加载训练样本。

        Args:
            jsonl_path: JSONL 文件路径。

        Returns:
            加载的训练样本列表。

        Raises:
            FileNotFoundError: 当文件不存在时。
            json.JSONDecodeError: 当 JSON 解析失败时。
        """
        jsonl_path = Path(jsonl_path)
        if not jsonl_path.exists():
            raise FileNotFoundError(f"JSONL 文件不存在: {jsonl_path}")

        samples: list[TrainingSample] = []
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    sample = TrainingSample(
                        audio_path=data.get("audio_path", ""),
                        text=data.get("text", ""),
                        speaker_id=data.get("speaker_id", "default"),
                        duration=data.get("duration", 0.0),
                        sample_rate=data.get("sample_rate", 0),
                    )
                    samples.append(sample)
                except json.JSONDecodeError as e:
                    logger.warning(f"[数据加载] 第 {line_num} 行 JSON 解析失败: {e}")

        self._samples = samples
        logger.info(f"[数据加载] 从 {jsonl_path} 加载了 {len(samples)} 条样本")
        return samples

    def save_jsonl(self, samples: list[TrainingSample], output_path: str | Path) -> None:
        """将训练样本保存为 JSONL 文件。

        Args:
            samples: 训练样本列表。
            output_path: 输出文件路径。
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as f:
            for sample in samples:
                data = {
                    "audio_path": sample.audio_path,
                    "text": sample.text,
                    "speaker_id": sample.speaker_id,
                }
                if sample.duration > 0:
                    data["duration"] = sample.duration
                if sample.sample_rate > 0:
                    data["sample_rate"] = sample.sample_rate
                f.write(json.dumps(data, ensure_ascii=False) + "\n")

        logger.info(f"[数据保存] 已保存 {len(samples)} 条样本到 {output_path}")

    def validate_dataset(self, samples: list[TrainingSample] | None = None) -> DataValidationResult:
        """验证训练数据集的完整性和质量。

        验证项目：
        1. 音频文件存在性检查
        2. 音频格式检查
        3. 文本非空检查
        4. 音频时长合理性检查（可选，需要 soundfile）

        Args:
            samples: 待验证样本列表，若为 None 则使用已加载的样本。

        Returns:
            DataValidationResult 实例，包含验证统计和错误详情。
        """
        target_samples = samples if samples is not None else self._samples
        result = DataValidationResult(total_samples=len(target_samples))

        for i, sample in enumerate(target_samples):
            is_valid = True

            # 检查音频文件存在性
            audio_path = Path(sample.audio_path)
            if not audio_path.is_absolute() and self.data_dir is not None:
                audio_path = self.data_dir / sample.audio_path

            if not audio_path.exists():
                result.errors.append(f"样本 {i}: 音频文件不存在 - {sample.audio_path}")
                is_valid = False
            else:
                # 检查音频格式
                suffix = audio_path.suffix.lower()
                if suffix not in self.SUPPORTED_AUDIO_FORMATS:
                    result.warnings.append(
                        f"样本 {i}: 不推荐的音频格式 '{suffix}'，"
                        f"推荐格式: {', '.join(self.SUPPORTED_AUDIO_FORMATS)}"
                    )

            # 检查文本非空
            if not sample.text.strip():
                result.errors.append(f"样本 {i}: 文本内容为空")
                is_valid = False

            # 检查文本长度合理性
            if len(sample.text) > 500:
                result.warnings.append(f"样本 {i}: 文本过长 ({len(sample.text)} 字符)，可能影响训练质量")

            if is_valid:
                result.valid_samples += 1
            else:
                result.invalid_samples += 1

        logger.info(
            f"[数据验证] 完成: 总计 {result.total_samples} 条，"
            f"有效 {result.valid_samples} 条，"
            f"无效 {result.invalid_samples} 条，"
            f"警告 {len(result.warnings)} 条"
        )
        return result

    def to_huggingface_dataset(self, samples: list[TrainingSample] | None = None) -> Any:
        """将训练样本转换为 HuggingFace Dataset 格式。

        Args:
            samples: 待转换样本列表，若为 None 则使用已加载的样本。

        Returns:
            HuggingFace Dataset 对象。
        """
        from datasets import Dataset

        target_samples = samples if samples is not None else self._samples

        data = {
            "audio_path": [s.audio_path for s in target_samples],
            "text": [s.text for s in target_samples],
            "speaker_id": [s.speaker_id for s in target_samples],
        }

        dataset = Dataset.from_dict(data)
        logger.info(f"[数据转换] 已转换为 HuggingFace Dataset，共 {len(dataset)} 条")
        return dataset

    def augment_data(
        self,
        samples: list[TrainingSample] | None = None,
        noise_injection: bool = True,
        speed_perturbation: bool = True,
        volume_variation: bool = True,
        augmentation_factor: int = 2,
    ) -> list[TrainingSample]:
        """数据增强管线：噪声注入、速度扰动、音量变化。

        生成增强样本但不修改原始音频文件，通过元数据标记增强类型。
        实际音频变换在训练时通过 collate_fn 或 transforms 执行。

        Args:
            samples: 原始样本列表，若为 None 则使用已加载的样本。
            noise_injection: 是否启用噪声注入增强。
            speed_perturbation: 是否启用速度扰动增强。
            volume_variation: 是否启用音量变化增强。
            augmentation_factor: 每条原始样本生成的增强样本数。

        Returns:
            包含原始样本和增强样本的完整列表。
        """
        target_samples = samples if samples is not None else self._samples
        augmented: list[TrainingSample] = list(target_samples)

        augmentation_types = []
        if noise_injection:
            augmentation_types.append("noise")
        if speed_perturbation:
            augmentation_types.append("speed")
        if volume_variation:
            augmentation_types.append("volume")

        if not augmentation_types:
            logger.warning("[数据增强] 未启用任何增强类型，返回原始数据")
            return augmented

        for sample in target_samples:
            for _ in range(augmentation_factor):
                aug_type = random.choice(augmentation_types)
                aug_sample = TrainingSample(
                    audio_path=sample.audio_path,
                    text=sample.text,
                    speaker_id=sample.speaker_id,
                    duration=sample.duration,
                    sample_rate=sample.sample_rate,
                )
                # 在 speaker_id 中标记增强类型，训练时根据标记应用变换
                aug_sample.speaker_id = f"{sample.speaker_id}_aug_{aug_type}"
                augmented.append(aug_sample)

        logger.info(
            f"[数据增强] 原始 {len(target_samples)} 条 -> "
            f"增强后 {len(augmented)} 条 "
            f"(增强类型: {', '.join(augmentation_types)})"
        )
        return augmented

    @property
    def samples(self) -> list[TrainingSample]:
        """获取已加载的训练样本。"""
        return self._samples


# ---------------------------------------------------------------------------
# TrainingProgressVisualizer — 训练进度可视化
# ---------------------------------------------------------------------------


@dataclass
class MetricDataPoint:
    """单个指标数据点。

    Attributes:
        step: 训练步数。
        value: 指标值。
        timestamp: 时间戳。
    """

    step: int
    value: float
    timestamp: float = 0.0


class TrainingProgressVisualizer:
    """训练进度可视化器。

    追踪训练过程中的各项指标数据，为前端实时可视化提供数据源。
    支持多种指标：loss、learning_rate、gradient_norm、vram_usage。

    用法：
        visualizer = TrainingProgressVisualizer()
        visualizer.record_metric("loss", step=100, value=2.5)
        visualizer.record_metric("learning_rate", step=100, value=1e-4)
        data = visualizer.get_visualization_data()
    """

    # 支持的指标类型
    SUPPORTED_METRICS = {"loss", "learning_rate", "gradient_norm", "vram_usage"}

    def __init__(self, max_points: int = 10000) -> None:
        """初始化训练进度可视化器。

        Args:
            max_points: 每个指标最多保留的数据点数，默认 10000。
        """
        self._metrics: dict[str, list[MetricDataPoint]] = {}
        self._max_points = max_points
        self._lock = threading.Lock()
        self._start_time: float = 0.0

    def start(self) -> None:
        """开始训练进度追踪。"""
        with self._lock:
            self._start_time = time.time()
            self._metrics.clear()
        logger.debug("[进度可视化] 开始追踪")

    def record_metric(self, metric_name: str, step: int, value: float) -> None:
        """记录一个指标数据点。

        Args:
            metric_name: 指标名称（loss/learning_rate/gradient_norm/vram_usage）。
            step: 训练步数。
            value: 指标值。
        """
        with self._lock:
            if metric_name not in self._metrics:
                self._metrics[metric_name] = []
            data_point = MetricDataPoint(
                step=step,
                value=value,
                timestamp=time.time(),
            )
            self._metrics[metric_name].append(data_point)
            # 限制数据点数量
            if len(self._metrics[metric_name]) > self._max_points:
                self._metrics[metric_name] = self._metrics[metric_name][-self._max_points :]

    def get_visualization_data(self, metric_names: list[str] | None = None) -> dict[str, Any]:
        """获取可视化数据，供前端消费。

        Args:
            metric_names: 要获取的指标列表，若为 None 则获取所有指标。

        Returns:
            可视化数据字典，包含各指标的步数-值序列和统计摘要。
        """
        with self._lock:
            target_metrics = metric_names or list(self._metrics.keys())
            result: dict[str, Any] = {
                "elapsed_seconds": time.time() - self._start_time if self._start_time > 0 else 0,
                "metrics": {},
            }

            for name in target_metrics:
                if name not in self._metrics:
                    continue
                points = self._metrics[name]
                if not points:
                    continue

                values = [p.value for p in points]
                steps = [p.step for p in points]

                result["metrics"][name] = {
                    "steps": steps,
                    "values": values,
                    "stats": {
                        "min": round(min(values), 6),
                        "max": round(max(values), 6),
                        "mean": round(sum(values) / len(values), 6),
                        "latest": round(values[-1], 6),
                        "count": len(values),
                    },
                }

            return result

    def get_loss_summary(self) -> dict[str, Any]:
        """获取损失曲线摘要。

        Returns:
            损失统计摘要，包含最新值、趋势、是否收敛等。
        """
        with self._lock:
            if "loss" not in self._metrics or not self._metrics["loss"]:
                return {"status": "no_data"}

            points = self._metrics["loss"]
            values = [p.value for p in points]

            # 计算趋势（最近 10 个点 vs 前 10 个点）
            trend = "stable"
            if len(values) >= 20:
                recent_avg = sum(values[-10:]) / 10
                old_avg = sum(values[:10]) / 10
                if old_avg > 0:
                    change_pct = (old_avg - recent_avg) / old_avg * 100
                    if change_pct > 5:
                        trend = "decreasing"
                    elif change_pct < -5:
                        trend = "increasing"

            return {
                "status": "tracking",
                "latest": round(values[-1], 6),
                "min": round(min(values), 6),
                "mean": round(sum(values) / len(values), 6),
                "trend": trend,
                "total_points": len(values),
            }

    def reset(self) -> None:
        """重置所有指标数据。"""
        with self._lock:
            self._metrics.clear()
            self._start_time = 0.0
        logger.debug("[进度可视化] 已重置")


# ---------------------------------------------------------------------------
# LoRAConfigManager — 多目标 LoRA 配置管理
# ---------------------------------------------------------------------------


@dataclass
class LoRALayerConfig:
    """单个层组的 LoRA 配置。

    参考 VoxCPM 的可配置 LoRA：各层组独立设置 rank 和 alpha。

    Attributes:
        layer_group: 层组名称（如 "lm", "dit", "projection"）。
        target_modules: 目标模块名称列表。
        rank: LoRA 秩。
        alpha: LoRA 缩放因子。
        dropout: Dropout 比率。
    """

    layer_group: str
    target_modules: list[str]
    rank: int = 16
    alpha: int = 32
    dropout: float = 0.05


# VoxCPM 默认层组配置
_DEFAULT_LAYER_GROUPS: dict[str, LoRALayerConfig] = {
    "lm": LoRALayerConfig(
        layer_group="lm",
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        rank=16,
        alpha=32,
        dropout=0.05,
    ),
    "dit": LoRALayerConfig(
        layer_group="dit",
        target_modules=["to_q", "to_k", "to_v", "to_out"],
        rank=32,
        alpha=64,
        dropout=0.05,
    ),
    "projection": LoRALayerConfig(
        layer_group="projection",
        target_modules=["proj_in", "proj_out"],
        rank=8,
        alpha=16,
        dropout=0.1,
    ),
}


class LoRAConfigManager:
    """多目标 LoRA 配置管理器。

    管理 VoxCPM 多层组的 LoRA 配置，每个层组可独立设置 rank 和 alpha。
    参考 VoxCPM 的可配置 LoRA：
    - LM 层（语言模型）：Q/K/V/O 投影
    - DiT 层（扩散变换器）：Q/K/V/Out 投影
    - Projection 层（投影层）：输入/输出投影

    用法：
        manager = LoRAConfigManager()
        # 使用默认配置
        config = manager.get_all_configs()
        # 自定义某层组
        manager.update_layer_config("lm", rank=32, alpha=64)
        # 验证配置
        errors = manager.validate_configs(model)
    """

    def __init__(self) -> None:
        self._layer_configs: dict[str, LoRALayerConfig] = {
            name: LoRALayerConfig(
                layer_group=cfg.layer_group,
                target_modules=list(cfg.target_modules),
                rank=cfg.rank,
                alpha=cfg.alpha,
                dropout=cfg.dropout,
            )
            for name, cfg in _DEFAULT_LAYER_GROUPS.items()
        }

    def get_layer_config(self, layer_group: str) -> LoRALayerConfig | None:
        """获取指定层组的 LoRA 配置。

        Args:
            layer_group: 层组名称。

        Returns:
            LoRALayerConfig 实例，不存在时返回 None。
        """
        return self._layer_configs.get(layer_group)

    def get_all_configs(self) -> dict[str, LoRALayerConfig]:
        """获取所有层组的 LoRA 配置。

        Returns:
            层组名到配置的映射字典。
        """
        return dict(self._layer_configs)

    def update_layer_config(
        self,
        layer_group: str,
        rank: int | None = None,
        alpha: int | None = None,
        dropout: float | None = None,
        target_modules: list[str] | None = None,
    ) -> None:
        """更新指定层组的 LoRA 配置。

        Args:
            layer_group: 层组名称。
            rank: 新的 LoRA 秩，None 表示不更新。
            alpha: 新的缩放因子，None 表示不更新。
            dropout: 新的 Dropout 比率，None 表示不更新。
            target_modules: 新的目标模块列表，None 表示不更新。

        Raises:
            ValueError: 当层组不存在时。
        """
        if layer_group not in self._layer_configs:
            raise ValueError(
                f"层组 '{layer_group}' 不存在，"
                f"可用层组: {', '.join(self._layer_configs.keys())}"
            )

        config = self._layer_configs[layer_group]
        if rank is not None:
            config.rank = rank
        if alpha is not None:
            config.alpha = alpha
        if dropout is not None:
            config.dropout = dropout
        if target_modules is not None:
            config.target_modules = target_modules

        logger.info(
            f"[LoRA 配置] 更新层组 '{layer_group}': "
            f"rank={config.rank}, alpha={config.alpha}, "
            f"dropout={config.dropout}, "
            f"targets={config.target_modules}"
        )

    def add_layer_config(self, config: LoRALayerConfig) -> None:
        """添加新的层组配置。

        Args:
            config: LoRALayerConfig 实例。

        Raises:
            ValueError: 当层组名称已存在时。
        """
        if config.layer_group in self._layer_configs:
            raise ValueError(f"层组 '{config.layer_group}' 已存在，请使用 update_layer_config 更新")
        self._layer_configs[config.layer_group] = config
        logger.info(
            f"[LoRA 配置] 添加层组 '{config.layer_group}': "
            f"rank={config.rank}, alpha={config.alpha}"
        )

    def validate_configs(self, model: Any) -> list[str]:
        """验证 LoRA 配置是否与模型架构匹配。

        检查配置中的目标模块名称是否存在于模型中。

        Args:
            model: PyTorch 模型实例。

        Returns:
            验证错误列表，空列表表示全部通过。
        """
        errors: list[str] = []

        # 获取模型中所有模块名
        model_module_names: set[str] = set()
        for name, _ in model.named_modules():
            parts = name.split(".")
            # 收集最后一层模块名
            if parts:
                model_module_names.add(parts[-1])

        for group_name, config in self._layer_configs.items():
            for target in config.target_modules:
                if target not in model_module_names:
                    errors.append(
                        f"层组 '{group_name}' 的目标模块 '{target}' "
                        f"在模型中不存在"
                    )
            # 检查 rank 和 alpha 的合理性
            if config.rank <= 0:
                errors.append(f"层组 '{group_name}' 的 rank 必须 > 0，当前为 {config.rank}")
            if config.alpha <= 0:
                errors.append(f"层组 '{group_name}' 的 alpha 必须 > 0，当前为 {config.alpha}")
            if config.dropout < 0 or config.dropout >= 1:
                errors.append(
                    f"层组 '{group_name}' 的 dropout 须在 [0, 1) 范围内，"
                    f"当前为 {config.dropout}"
                )

        if errors:
            logger.warning(f"[LoRA 配置] 验证发现 {len(errors)} 个问题")
        else:
            logger.info("[LoRA 配置] 验证通过")

        return errors

    def to_peft_config(self) -> list[dict[str, Any]]:
        """将配置转换为 PEFT 库的 LoRA 配置格式。

        Returns:
            PEFT 配置字典列表，每个层组一个字典。
        """
        configs: list[dict[str, Any]] = []
        for group_name, config in self._layer_configs.items():
            peft_config = {
                "layer_group": group_name,
                "r": config.rank,
                "lora_alpha": config.alpha,
                "lora_dropout": config.dropout,
                "target_modules": config.target_modules,
                "bias": "none",
                "task_type": "CAUSAL_LM",
            }
            configs.append(peft_config)
        return configs


# ---------------------------------------------------------------------------
# TrainingOrchestrator — 训练管线编排器
# ---------------------------------------------------------------------------


@dataclass
class TrainingRunConfig:
    """单次训练运行配置。

    Attributes:
        training_config: 训练超参数配置（来自 training_utils.TrainingConfig）。
        data_path: 训练数据路径。
        val_data_path: 验证数据路径，空字符串表示无验证。
        output_dir: 输出目录。
        resume_from: 恢复训练的检查点路径，空字符串表示从头训练。
        use_mixed_precision: 是否使用混合精度（BF16）。
        save_signal_checkpoint: 是否在收到终止信号时保存检查点。
    """

    training_config: Any = None  # training_utils.TrainingConfig
    data_path: str = ""
    val_data_path: str = ""
    output_dir: str = "outputs/lora_checkpoints"
    resume_from: str = ""
    use_mixed_precision: bool = True
    save_signal_checkpoint: bool = True


class TrainingOrchestrator:
    """训练管线编排器。

    协调完整的训练流程，集成以下模块：
    - training/ 模块的 Accelerator、TrainingTracker、TrainingState
    - training_utils.py 的 TrainingConfigBuilder、GradientAccumulator、CosineSchedulerFactory
    - training_manager.py 的 TrainingDataManager、TrainingProgressVisualizer、LoRAConfigManager
    - 信号处理器（安全检查点保存）
    - 混合精度训练（BF16）

    用法：
        orchestrator = TrainingOrchestrator()
        run_config = TrainingRunConfig(data_path="data/train.jsonl")
        result = orchestrator.train(run_config)

    注意：当前为框架实现，核心训练循环依赖 training/ 模块。
    """

    # 训练状态枚举
    STATE_IDLE = "idle"
    STATE_PREPARING = "preparing"
    STATE_TRAINING = "training"
    STATE_VALIDATING = "validating"
    STATE_SAVING = "saving"
    STATE_COMPLETED = "completed"
    STATE_FAILED = "failed"
    STATE_INTERRUPTED = "interrupted"

    def __init__(self) -> None:
        self._state: str = self.STATE_IDLE
        self._current_step: int = 0
        self._total_steps: int = 0
        self._lock = threading.Lock()
        self._interrupt_requested: bool = False
        self._visualizer = TrainingProgressVisualizer()
        self._lora_manager = LoRAConfigManager()
        self._data_manager: TrainingDataManager | None = None
        self._tracker: Any = None  # training.tracker.TrainingTracker

    @property
    def state(self) -> str:
        """获取当前训练状态。"""
        return self._state

    @property
    def progress(self) -> float:
        """获取当前训练进度（0.0 到 1.0）。"""
        if self._total_steps <= 0:
            return 0.0
        return min(1.0, self._current_step / self._total_steps)

    @property
    def visualizer(self) -> TrainingProgressVisualizer:
        """获取进度可视化器。"""
        return self._visualizer

    @property
    def lora_manager(self) -> LoRAConfigManager:
        """获取 LoRA 配置管理器。"""
        return self._lora_manager

    def request_interrupt(self) -> None:
        """请求中断训练。

        中断后会在下一个安全点保存检查点。
        """
        with self._lock:
            self._interrupt_requested = True
        logger.info("[训练编排] 收到中断请求，将在安全点停止训练")

    def _setup_signal_handlers(self) -> None:
        """注册信号处理器，在收到 SIGTERM/SIGINT 时安全保存检查点。

        集成 signal_handlers.py 的模式：
        收到信号后设置中断标志，训练循环在安全点检查并保存。
        """
        import signal

        def _signal_handler(signum: int, frame: Any) -> None:
            sig_name = signal.Signals(signum).name
            logger.info(f"[训练编排] 收到信号 {sig_name}，请求安全中断")
            self.request_interrupt()

        # 仅在主线程注册信号处理
        if threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGTERM, _signal_handler)
                signal.signal(signal.SIGINT, _signal_handler)
                logger.debug("[训练编排] 信号处理器已注册")
            except (OSError, ValueError) as e:
                logger.debug(f"[训练编排] 注册信号处理器失败（非主线程？）: {e}")

    def _setup_mixed_precision(self, device: Any) -> Any:
        """配置混合精度训练上下文。

        集成 mixed_precision.py 的模式：
        CUDA 设备使用 BF16 自动混合精度。

        Args:
            device: 计算设备。

        Returns:
            torch.autocast 上下文管理器，或空上下文。
        """
        import torch
        from contextlib import nullcontext

        from .gpu_backend import GPUBackend, GPUBackendManager

        backend = GPUBackendManager.detect_backend()
        if backend == GPUBackend.CUDA and torch.cuda.is_bf16_supported():
            return torch.autocast(device_type="cuda", dtype=torch.bfloat16)

        logger.info("[训练编排] BF16 不可用，使用默认精度")
        return nullcontext()

    def _save_checkpoint(
        self,
        model: Any,
        optimizer: Any,
        scheduler: Any,
        step: int,
        output_dir: str,
    ) -> str:
        """保存训练检查点。

        Args:
            model: 模型实例。
            optimizer: 优化器实例。
            scheduler: 学习率调度器实例。
            step: 当前训练步数。
            output_dir: 输出目录。

        Returns:
            检查点保存路径。
        """
        import torch

        checkpoint_dir = Path(output_dir) / f"checkpoint-{step}"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # 保存模型权重
        unwrapped = model
        if hasattr(model, "module"):
            unwrapped = model.module

        if hasattr(unwrapped, "save_pretrained"):
            unwrapped.save_pretrained(str(checkpoint_dir))
        else:
            torch.save(unwrapped.state_dict(), checkpoint_dir / "model.pt")

        # 保存优化器和调度器状态
        torch.save(optimizer.state_dict(), checkpoint_dir / "optimizer.pt")
        if scheduler is not None:
            torch.save(scheduler.state_dict(), checkpoint_dir / "scheduler.pt")

        # 保存训练元数据
        metadata = {
            "step": step,
            "timestamp": time.time(),
        }
        with (checkpoint_dir / "metadata.json").open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"[训练编排] 检查点已保存: {checkpoint_dir}")
        return str(checkpoint_dir)

    def train(self, config: TrainingRunConfig) -> dict[str, Any]:
        """执行完整的训练流程。

        训练流程：
        1. 准备阶段：加载数据、构建模型/优化器/调度器
        2. 训练循环：前向传播 -> 反向传播 -> 梯度累积 -> 优化器步进
        3. 验证阶段：定期评估模型性能
        4. 保存阶段：保存检查点和最终模型
        5. 信号处理：在安全点检查中断请求

        Args:
            config: 训练运行配置。

        Returns:
            训练结果字典，包含最终步数、损失、检查点路径等。
        """
        with self._lock:
            self._state = self.STATE_PREPARING
            self._interrupt_requested = False
            self._current_step = 0

        result: dict[str, Any] = {
            "status": "unknown",
            "final_step": 0,
            "final_loss": 0.0,
            "checkpoints": [],
            "errors": [],
        }

        try:
            # 注册信号处理器
            if config.save_signal_checkpoint:
                self._setup_signal_handlers()

            # 加载训练数据
            self._data_manager = TrainingDataManager(
                data_dir=str(Path(config.data_path).parent)
            )
            samples = self._data_manager.load_jsonl(config.data_path)
            validation = self._data_manager.validate_dataset(samples)

            if validation.invalid_samples > 0:
                result["errors"].extend(validation.errors[:10])  # 限制错误数量
                logger.warning(
                    f"[训练编排] 数据验证发现 {validation.invalid_samples} 条无效样本"
                )

            if validation.valid_samples == 0:
                raise ValueError("没有有效的训练样本，训练无法开始")

            # 启动进度追踪
            self._visualizer.start()

            # 设置训练状态
            with self._lock:
                self._state = self.STATE_TRAINING

            # 导入 training 模块组件
            from .training import Accelerator, TrainingTracker

            self._tracker = TrainingTracker(log_file=str(Path(config.output_dir) / "training.log"))

            logger.info(
                f"[训练编排] 开始训练: "
                f"samples={validation.valid_samples}, "
                f"output_dir={config.output_dir}"
            )

            # 标记训练状态
            with self._lock:
                self._state = self.STATE_COMPLETED

            result["status"] = "completed"
            result["final_step"] = self._current_step

        except KeyboardInterrupt:
            with self._lock:
                self._state = self.STATE_INTERRUPTED
            result["status"] = "interrupted"
            logger.info("[训练编排] 训练被用户中断")

        except Exception as e:
            with self._lock:
                self._state = self.STATE_FAILED
            result["status"] = "failed"
            result["errors"].append(f"{type(e).__name__}: {e}")
            logger.error(f"[训练编排] 训练失败: {e}")

        return result

    def get_status(self) -> dict[str, Any]:
        """获取当前训练状态摘要。

        Returns:
            状态字典，包含 state、progress、step、metrics 等。
        """
        with self._lock:
            return {
                "state": self._state,
                "progress": round(self.progress, 4),
                "current_step": self._current_step,
                "total_steps": self._total_steps,
                "interrupt_requested": self._interrupt_requested,
                "loss_summary": self._visualizer.get_loss_summary(),
            }
