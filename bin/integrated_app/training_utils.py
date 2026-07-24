# -*- coding: utf-8 -*-
"""训练工具集模块（第 8 章）：梯度累积、学习率调度器、训练配置构建、DPO 存根。

提供 VoxCPM LoRA 微调训练所需的核心工具类：
- GradientAccumulator: 梯度累积，默认 8 步（对齐 VoxCPM 参考实现）
- CosineSchedulerFactory: 余弦退火调度器 + 线性预热
- TrainingConfigBuilder: BF16 + 梯度累积 + AdamW + 余弦调度器的完整训练配置
- DPOTrainerStub: DPO（Direct Preference Optimization）训练存根

参考：
- VoxCPM 训练配置：BF16 精度、8 步梯度累积、AdamW 优化器、余弦学习率调度
- GPT-SoVITS：正/负样本对比学习（DPO 参考）
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("tts_multimodel")


# ---------------------------------------------------------------------------
# GradientAccumulator — 梯度累积
# ---------------------------------------------------------------------------


class GradientAccumulator:
    """梯度累积控制器。

    在显存有限时，通过累积多个小批次的梯度来模拟大批次训练。
    默认累积步数为 8，对齐 VoxCPM 参考实现。

    用法：
        accumulator = GradientAccumulator(accumulation_steps=8)
        for batch_idx, batch in enumerate(dataloader):
            loss = model(batch) / accumulator.accumulation_steps
            loss.backward()
            if accumulator.should_step(batch_idx):
                optimizer.step()
                optimizer.zero_grad()
                accumulator.reset()

    Attributes:
        accumulation_steps: 梯度累积步数。
        _current_step: 当前已累积的步数。
    """

    def __init__(self, accumulation_steps: int = 8) -> None:
        if accumulation_steps < 1:
            raise ValueError(f"accumulation_steps 必须 >= 1，收到 {accumulation_steps}")
        self.accumulation_steps = accumulation_steps
        self._current_step: int = 0

    def should_step(self, batch_idx: int) -> bool:
        """判断当前批次是否应执行优化器步进。

        Args:
            batch_idx: 当前批次索引（从 0 开始）。

        Returns:
            True 表示已累积足够梯度，应执行优化器步进。
        """
        self._current_step += 1
        do_step = self._current_step >= self.accumulation_steps
        if do_step:
            logger.debug(
                f"[梯度累积] 执行步进：batch_idx={batch_idx}, "
                f"accumulated={self._current_step}/{self.accumulation_steps}"
            )
        return do_step

    def reset(self) -> None:
        """重置累积计数器（在每个优化器步进后调用）。"""
        self._current_step = 0

    @property
    def current_step(self) -> int:
        """当前已累积的步数。"""
        return self._current_step

    def wrap_optimizer(
        self,
        optimizer: Any,
        accumulation_steps: int | None = None,
    ) -> "_GradientAccumulationOptimizer":
        """将优化器包装为支持梯度累积的优化器。

        Args:
            optimizer: 原始优化器实例。
            accumulation_steps: 可选覆盖累积步数。

        Returns:
            包装后的梯度累积优化器。
        """
        steps = accumulation_steps if accumulation_steps is not None else self.accumulation_steps
        return _GradientAccumulationOptimizer(optimizer, steps, self)


class _GradientAccumulationOptimizer:
    """梯度累积优化器包装，透明代理原始优化器接口。"""

    def __init__(
        self,
        optimizer: Any,
        accumulation_steps: int,
        accumulator: GradientAccumulator,
    ) -> None:
        self.optimizer = optimizer
        self.accumulation_steps = accumulation_steps
        self.accumulator = accumulator
        self._step_count: int = 0

    def step(self, closure: Any = None) -> None:
        """条件性执行优化器步进。"""
        self._step_count += 1
        if self._step_count >= self.accumulation_steps:
            self.optimizer.step(closure=closure)
            self.optimizer.zero_grad()
            self.accumulator.reset()
            self._step_count = 0
            logger.debug("[梯度累积] 已执行 optimizer.step() 并清零梯度")

    def zero_grad(self, *args: Any, **kwargs: Any) -> None:
        self.optimizer.zero_grad(*args, **kwargs)

    @property
    def param_groups(self) -> list[dict]:
        return self.optimizer.param_groups

    @param_groups.setter
    def param_groups(self, value: list[dict]) -> None:
        self.optimizer.param_groups = value

    @property
    def state(self) -> dict:
        return self.optimizer.state

    def state_dict(self) -> dict:
        return self.optimizer.state_dict()

    def load_state_dict(self, state_dict: dict) -> None:
        self.optimizer.load_state_dict(state_dict)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.optimizer, name)


# ---------------------------------------------------------------------------
# CosineSchedulerFactory — 余弦退火调度器 + 线性预热
# ---------------------------------------------------------------------------


class CosineSchedulerFactory:
    """余弦退火学习率调度器工厂，支持线性预热。

    创建 PyTorch LambdaLR 调度器，先线性预热到初始学习率，
    再按余弦函数衰减到 min_lr。

    参考实现：VoxCPM 训练使用余弦退火 + 线性预热的经典组合，
    预热期通常为总步数的 5-10%。
    """

    @staticmethod
    def _cosine_schedule_with_warmup(
        current_step: int,
        *,
        num_warmup_steps: int,
        num_training_steps: int,
        min_lr_ratio: float,
    ) -> float:
        """计算余弦退火 + 线性预热的学习率乘数。"""
        if current_step < num_warmup_steps:
            return float(current_step) / float(max(1, num_warmup_steps))
        progress = float(current_step - num_warmup_steps) / float(
            max(1, num_training_steps - num_warmup_steps)
        )
        cosine_decay = 0.5 * (1.0 + math.cos(math.pi * progress))
        return max(min_lr_ratio, cosine_decay * (1.0 - min_lr_ratio) + min_lr_ratio)

    def create(
        self,
        optimizer: Any,
        total_steps: int,
        warmup_steps: int = 0,
        min_lr: float = 1e-6,
        base_lr: float | None = None,
    ) -> Any:
        """创建余弦退火 + 线性预热的学习率调度器。

        Args:
            optimizer: PyTorch 优化器实例。
            total_steps: 总训练步数。
            warmup_steps: 线性预热步数，默认 0。
            min_lr: 最低学习率，默认 1e-6。
            base_lr: 基础学习率，若为 None 则从优化器读取。

        Returns:
            torch.optim.lr_scheduler.LambdaLR 实例。

        Raises:
            ValueError: 当 total_steps <= 0 或 warmup_steps > total_steps 时。
        """
        import torch

        if total_steps <= 0:
            raise ValueError(f"total_steps 必须 > 0，收到 {total_steps}")
        if warmup_steps > total_steps:
            raise ValueError(
                f"warmup_steps ({warmup_steps}) 不能大于 total_steps ({total_steps})"
            )

        if base_lr is None:
            base_lr = optimizer.param_groups[0]["lr"]

        min_lr_ratio = min_lr / base_lr if base_lr > 0 else 0.0

        scheduler = torch.optim.lr_scheduler.LambdaLR(
            optimizer,
            lr_lambda=lambda step: self._cosine_schedule_with_warmup(
                step,
                num_warmup_steps=warmup_steps,
                num_training_steps=total_steps,
                min_lr_ratio=min_lr_ratio,
            ),
        )

        logger.info(
            f"[调度器] 创建余弦退火调度器: "
            f"total_steps={total_steps}, warmup_steps={warmup_steps}, "
            f"base_lr={base_lr}, min_lr={min_lr}, "
            f"min_lr_ratio={min_lr_ratio:.6f}"
        )
        return scheduler


# ---------------------------------------------------------------------------
# TrainingConfigBuilder — 训练配置构建器
# ---------------------------------------------------------------------------


@dataclass
class TrainingConfig:
    """VoxCPM LoRA 微调训练配置。

    参考 VoxCPM 训练配置：
    - BF16 混合精度训练
    - 8 步梯度累积
    - AdamW 优化器
    - 余弦学习率调度 + 线性预热

    Attributes:
        batch_size: 每设备批次大小。
        gradient_accumulation_steps: 梯度累积步数。
        learning_rate: 峰值学习率。
        weight_decay: 权重衰减系数。
        warmup_steps: 线性预热步数。
        total_steps: 总训练步数。
        min_lr: 最低学习率。
        use_bf16: 是否使用 BF16 混合精度。
        max_grad_norm: 梯度裁剪范数阈值。
        seed: 随机种子。
        log_interval: 日志记录间隔步数。
        save_interval: 检查点保存间隔步数。
        eval_interval: 验证间隔步数。
        output_dir: 输出目录路径。
        lora_rank: LoRA 秩。
        lora_alpha: LoRA 缩放因子。
        lora_dropout: LoRA Dropout 比率。
        target_modules: LoRA 目标模块列表。
    """

    batch_size: int = 4
    gradient_accumulation_steps: int = 8
    learning_rate: float = 1e-4
    weight_decay: float = 0.01
    warmup_steps: int = 500
    total_steps: int = 10000
    min_lr: float = 1e-6
    use_bf16: bool = True
    max_grad_norm: float = 1.0
    seed: int = 42
    log_interval: int = 10
    save_interval: int = 1000
    eval_interval: int = 500
    output_dir: str = "outputs/lora_checkpoints"
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: list[str] = field(
        default_factory=lambda: ["q_proj", "v_proj", "k_proj", "o_proj"]
    )

    @property
    def effective_batch_size(self) -> int:
        """有效批次大小 = batch_size * gradient_accumulation_steps。"""
        return self.batch_size * self.gradient_accumulation_steps


class TrainingConfigBuilder:
    """VoxCPM LoRA 微调训练配置构建器。

    支持链式调用构建完整的训练配置，默认值对齐 VoxCPM 参考实现。
    构建完成后可生成 optimizer、scheduler 和 gradient accumulator。

    用法：
        config = (
            TrainingConfigBuilder()
            .set_batch_size(4)
            .set_learning_rate(1e-4)
            .set_gradient_accumulation(8)
            .set_bf16(True)
            .set_lora(rank=16, alpha=32)
            .build()
        )
    """

    def __init__(self) -> None:
        self._config = TrainingConfig()

    def set_batch_size(self, batch_size: int) -> "TrainingConfigBuilder":
        """设置每设备批次大小。"""
        self._config.batch_size = batch_size
        return self

    def set_learning_rate(self, lr: float) -> "TrainingConfigBuilder":
        """设置峰值学习率。"""
        self._config.learning_rate = lr
        return self

    def set_gradient_accumulation(self, steps: int) -> "TrainingConfigBuilder":
        """设置梯度累积步数。"""
        self._config.gradient_accumulation_steps = steps
        return self

    def set_warmup_steps(self, steps: int) -> "TrainingConfigBuilder":
        """设置线性预热步数。"""
        self._config.warmup_steps = steps
        return self

    def set_total_steps(self, steps: int) -> "TrainingConfigBuilder":
        """设置总训练步数。"""
        self._config.total_steps = steps
        return self

    def set_bf16(self, enabled: bool = True) -> "TrainingConfigBuilder":
        """启用或禁用 BF16 混合精度训练。"""
        self._config.use_bf16 = enabled
        return self

    def set_lora(
        self,
        rank: int = 16,
        alpha: int = 32,
        dropout: float = 0.05,
        target_modules: list[str] | None = None,
    ) -> "TrainingConfigBuilder":
        """设置 LoRA 参数。"""
        self._config.lora_rank = rank
        self._config.lora_alpha = alpha
        self._config.lora_dropout = dropout
        if target_modules is not None:
            self._config.target_modules = target_modules
        return self

    def set_output_dir(self, output_dir: str) -> "TrainingConfigBuilder":
        """设置输出目录。"""
        self._config.output_dir = output_dir
        return self

    def set_intervals(
        self,
        log_interval: int = 10,
        save_interval: int = 1000,
        eval_interval: int = 500,
    ) -> "TrainingConfigBuilder":
        """设置日志/保存/验证间隔。"""
        self._config.log_interval = log_interval
        self._config.save_interval = save_interval
        self._config.eval_interval = eval_interval
        return self

    def build(self) -> TrainingConfig:
        """构建并返回训练配置。"""
        logger.info(
            f"[训练配置] 构建完成: "
            f"batch_size={self._config.batch_size}, "
            f"accumulation={self._config.gradient_accumulation_steps}, "
            f"effective_batch={self._config.effective_batch_size}, "
            f"lr={self._config.learning_rate}, "
            f"bf16={self._config.use_bf16}, "
            f"lora_rank={self._config.lora_rank}, "
            f"lora_alpha={self._config.lora_alpha}"
        )
        return self._config

    def build_optimizer(self, model_params: Any, config: TrainingConfig | None = None) -> Any:
        """构建 AdamW 优化器。

        对权重参数应用 weight_decay，对偏置和 LayerNorm 参数不应用。

        Args:
            model_params: 模型参数（model.named_parameters() 的返回值）。
            config: 可选配置，若为 None 则使用构建器内部配置。

        Returns:
            torch.optim.AdamW 实例。
        """
        import torch

        cfg = config or self._config

        decay_params = []
        no_decay_params = []
        for name, param in model_params:
            if not param.requires_grad:
                continue
            if param.dim() < 2 or "bias" in name or "norm" in name or "ln" in name:
                no_decay_params.append(param)
            else:
                decay_params.append(param)

        optimizer_groups = [
            {"params": decay_params, "weight_decay": cfg.weight_decay},
            {"params": no_decay_params, "weight_decay": 0.0},
        ]

        optimizer = torch.optim.AdamW(
            optimizer_groups,
            lr=cfg.learning_rate,
            betas=(0.9, 0.999),
            eps=1e-8,
        )

        logger.info(
            f"[训练配置] AdamW 优化器已创建: "
            f"decay_params={len(decay_params)}, "
            f"no_decay_params={len(no_decay_params)}, "
            f"lr={cfg.learning_rate}, weight_decay={cfg.weight_decay}"
        )
        return optimizer

    def build_scheduler(self, optimizer: Any, config: TrainingConfig | None = None) -> Any:
        """构建余弦退火学习率调度器。"""
        cfg = config or self._config
        factory = CosineSchedulerFactory()
        return factory.create(
            optimizer=optimizer,
            total_steps=cfg.total_steps,
            warmup_steps=cfg.warmup_steps,
            min_lr=cfg.min_lr,
            base_lr=cfg.learning_rate,
        )

    def build_gradient_accumulator(self, config: TrainingConfig | None = None) -> GradientAccumulator:
        """构建梯度累积器。"""
        cfg = config or self._config
        return GradientAccumulator(accumulation_steps=cfg.gradient_accumulation_steps)


# ---------------------------------------------------------------------------
# DPOTrainerStub — DPO 训练存根
# ---------------------------------------------------------------------------


class DPOTrainerStub:
    """DPO（Direct Preference Optimization）训练存根。

    DPO 是一种基于偏好对比的训练方法，通过正/负样本对比学习
    使模型生成更符合人类偏好的语音。

    参考 GPT-SoVITS 的正/负样本对比学习策略：
    - 正样本：高质量目标语音
    - 负样本：低质量或不匹配的语音
    - 模型学习区分并偏好正样本的生成模式

    当前为存根实现，完整实现需要以下步骤：
    1. 准备配对偏好数据集（正/负样本对）
    2. 实现 DPO 损失函数（参考 RLHF/DPO 论文）
    3. 添加参考模型（reference model）管理
    4. 实现 Beta 超参数控制偏好强度
    5. 集成到 training_manager.py 的训练管线中

    Attributes:
        beta: DPO 偏好强度超参数（越大则越倾向正样本）。
        reference_model: 参考模型（冻结，用于计算 KL 散度）。
    """

    _IMPLEMENTATION_GUIDE = (
        "\nDPO 训练完整实现步骤：\n"
        "1. 数据准备：构建配对数据集 (prompt, chosen, rejected)\n"
        "2. 模型架构：训练模型 + 冻结参考模型\n"
        "3. 损失函数：L_DPO = -E[log sigma(beta * (log pi_theta(y_w|x) / pi_ref(y_w|x)"
        " - log pi_theta(y_l|x) / pi_ref(y_l|x)))]\n"
        "4. 训练循环：前向传播 -> DPO 损失 -> 反向传播 -> 仅更新 policy model\n"
        "5. 参考：Rafailov et al. 'Direct Preference Optimization' (NeurIPS 2023)"
    )

    def __init__(self, beta: float = 0.1, reference_model: Any = None) -> None:
        self.beta = beta
        self.reference_model = reference_model

    def train(self, model: Any, dataloader: Any, optimizer: Any, num_epochs: int = 1, **kwargs: Any) -> dict[str, Any]:
        """执行 DPO 训练（未实现）。

        Raises:
            NotImplementedError: 当前为存根实现。
        """
        raise NotImplementedError(f"DPO 训练尚未实现。{self._IMPLEMENTATION_GUIDE}")

    def compute_dpo_loss(
        self,
        policy_chosen_logps: Any,
        policy_rejected_logps: Any,
        reference_chosen_logps: Any,
        reference_rejected_logps: Any,
    ) -> Any:
        """计算 DPO 损失（未实现）。

        Raises:
            NotImplementedError: 当前为存根实现。
        """
        raise NotImplementedError(f"DPO 损失计算尚未实现。{self._IMPLEMENTATION_GUIDE}")

    def prepare_reference_model(self, model: Any) -> Any:
        """准备冻结的参考模型（未实现）。

        Raises:
            NotImplementedError: 当前为存根实现。
        """
        raise NotImplementedError(f"DPO 参考模型准备尚未实现。{self._IMPLEMENTATION_GUIDE}")

    @classmethod
    def get_implementation_guide(cls) -> str:
        """获取 DPO 实现指南。"""
        return cls._IMPLEMENTATION_GUIDE
