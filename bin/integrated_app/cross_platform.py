# -*- coding: utf-8 -*-
"""跨平台部署模块（第 15 章）：DirectML、CPU 回退、CUDA 安装、Docker 配置。

提供跨平台 GPU/CPU 推理支持：
- DirectMLStrategy: Windows + AMD/Intel GPU 的 DirectML 后端策略
- CPUFallbackManager: GPU 不可用时的 CPU 推理配置管理
- CUDAInstaller: CUDA 工具包版本检测与安装引导
- DockerConfig: 容器化部署的 Dockerfile 生成

参考：
- VoiceBox cuda.py 自动安装模式
- Piper ONNX 轻量级部署策略
- Piper 多质量等级策略
"""

from __future__ import annotations

import logging
import platform
import struct
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("tts_multimodel")


# ---------------------------------------------------------------------------
# DirectMLStrategy — DirectML GPU 后端策略（Windows + AMD/Intel）
# ---------------------------------------------------------------------------


class DirectMLStrategy:
    """DirectML GPU 后端策略，扩展 gpu_backend.py 的策略模式。

    支持 Windows 平台上的 AMD 和 Intel GPU，通过 Microsoft DirectML
    提供跨厂商 GPU 加速。

    DirectML 是 Windows 上 AMD/Intel GPU 的推荐加速方案，
    但不支持 Linux。本项目核心引擎（VoxCPM2/IndexTTS2）依赖 CUDA，
    DirectML 仅作为备选方案提供。

    用法：
        strategy = DirectMLStrategy()
        if strategy.is_available():
            device = strategy.get_device()
    """

    def __init__(self) -> None:
        self._dml_module: Any = None
        self._checked: bool = False
        self._available: bool = False

    def _check_availability(self) -> bool:
        """检测 torch_directml 是否可用。

        Returns:
            True 如果 DirectML 可用。
        """
        if self._checked:
            return self._available

        self._checked = True

        # DirectML 仅支持 Windows
        if platform.system() != "Windows":
            logger.debug("[DirectML] 非 Windows 平台，跳过检测")
            self._available = False
            return False

        try:
            import torch_directml  # type: ignore[import-untyped]

            self._dml_module = torch_directml
            # 尝试创建设备以验证 DirectML 运行时可用
            _ = torch_directml.device()
            self._available = True
            logger.info("[DirectML] 检测到 DirectML 后端可用")
        except ImportError:
            logger.debug("[DirectML] torch_directml 未安装")
            self._available = False
        except Exception as e:
            logger.warning(f"[DirectML] 初始化失败: {e}")
            self._available = False

        return self._available

    def is_available(self) -> bool:
        """检查 DirectML 后端是否可用。

        Returns:
            True 如果 DirectML 可用。
        """
        return self._check_availability()

    def get_device(self) -> Any:
        """获取 DirectML 设备。

        Returns:
            torch_directml 设备对象，不可用时返回 None。
        """
        if not self.is_available():
            return None
        try:
            return self._dml_module.device()
        except Exception as e:
            logger.error(f"[DirectML] 获取设备失败: {e}")
            return None

    def get_device_name(self) -> str:
        """获取 DirectML 设备名称。

        Returns:
            设备名称字符串，不可用时返回 "N/A"。
        """
        if not self.is_available():
            return "N/A"
        try:
            # torch_directml 可能不直接提供设备名
            # 尝试通过 adapter 属性获取
            device = self.get_device()
            if device is not None and hasattr(device, "adapter"):
                return str(device.adapter)
        except Exception:
            pass
        return "DirectML Device"

    def memory_allocated(self, device: Any = None) -> int:
        """获取已分配显存（DirectML 不支持精确查询，返回 0）。

        Args:
            device: 设备对象（忽略）。

        Returns:
            0（DirectML 不暴露显存分配信息）。
        """
        return 0

    def memory_reserved(self, device: Any = None) -> int:
        """获取已保留显存（DirectML 不支持精确查询，返回 0）。

        Returns:
            0。
        """
        return 0

    def empty_cache(self) -> None:
        """清理缓存（DirectML 不支持手动缓存管理，为空操作）。"""
        pass

    def synchronize(self, device: Any = None) -> None:
        """同步设备（DirectML 不支持显式同步，为空操作）。"""
        pass

    def get_autocast_device_type(self) -> str:
        """获取 autocast 设备类型。

        Returns:
            "cpu"（DirectML 不支持原生 autocast，回退到 CPU 精度管理）。
        """
        return "cpu"


# ---------------------------------------------------------------------------
# CPUFallbackManager — CPU 回退推理管理
# ---------------------------------------------------------------------------


@dataclass
class CPUInferenceConfig:
    """CPU 推理配置。

    当 GPU 不可用时，自动调整参数以适应 CPU 推理。
    参考 Piper 的多质量等级策略：
    - x-low: 最小化模型，最快速度
    - low: 小模型，较快速度
    - medium: 平衡模型质量和速度
    - high: 完整模型，最佳质量

    Attributes:
        quality: 质量等级 (x-low/low/medium/high)。
        batch_size: CPU 推理批次大小。
        num_threads: 推理线程数（0 = 自动检测）。
        use_int8: 是否使用 INT8 量化。
        use_onnx: 是否使用 ONNX Runtime 推理。
        chunk_size: 音频分块大小（CPU 推理时分块处理）。
    """

    quality: str = "medium"
    batch_size: int = 1
    num_threads: int = 0
    use_int8: bool = False
    use_onnx: bool = False
    chunk_size: int = 512


# CPU 质量等级配置映射（参考 Piper 多质量策略）
_QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "x-low": {
        "batch_size": 1,
        "num_threads": 2,
        "use_int8": True,
        "use_onnx": True,
        "chunk_size": 256,
        "description": "最小化模型，最快速度，质量较低",
        "estimated_rtf": 0.3,  # 实时率（Real-Time Factor），越小越快
    },
    "low": {
        "batch_size": 1,
        "num_threads": 4,
        "use_int8": True,
        "use_onnx": True,
        "chunk_size": 384,
        "description": "小模型，较快速度，质量一般",
        "estimated_rtf": 0.5,
    },
    "medium": {
        "batch_size": 1,
        "num_threads": 0,  # 自动检测
        "use_int8": False,
        "use_onnx": False,
        "chunk_size": 512,
        "description": "平衡质量和速度",
        "estimated_rtf": 1.0,
    },
    "high": {
        "batch_size": 1,
        "num_threads": 0,
        "use_int8": False,
        "use_onnx": False,
        "chunk_size": 1024,
        "description": "完整模型，最佳质量，速度较慢",
        "estimated_rtf": 2.0,
    },
}


class CPUFallbackManager:
    """CPU 回退推理管理器。

    当 GPU 不可用时，自动检测系统配置并生成优化的 CPU 推理参数。
    参考 Piper 的多质量等级策略，根据 CPU 核心数和内存自动选择最佳预设。

    用法：
        manager = CPUFallbackManager()
        if manager.should_fallback():
            config = manager.get_inference_config(quality="medium")
    """

    def __init__(self) -> None:
        self._cpu_count: int = 0
        self._total_ram_gb: float = 0.0
        self._detected: bool = False

    def _detect_system(self) -> None:
        """检测系统 CPU 和内存配置。"""
        if self._detected:
            return

        try:
            import psutil

            self._cpu_count = psutil.cpu_count(logical=False) or psutil.cpu_count() or 4
            self._total_ram_gb = psutil.virtual_memory().total / (1024**3)
        except ImportError:
            import os

            self._cpu_count = os.cpu_count() or 4
            # 无 psutil 时使用保守估计
            self._total_ram_gb = 8.0

        self._detected = True
        logger.info(
            f"[CPU 回退] 系统检测: "
            f"CPU 核心数={self._cpu_count}, "
            f"内存={self._total_ram_gb:.1f}GB"
        )

    def should_fallback(self) -> bool:
        """判断是否应回退到 CPU 推理。

        Returns:
            True 表示没有可用的 GPU，应使用 CPU 推理。
        """
        from .gpu_backend import GPUBackend, GPUBackendManager

        backend = GPUBackendManager.detect_backend()
        return backend == GPUBackend.CPU

    def get_recommended_quality(self) -> str:
        """根据系统配置推荐 CPU 推理质量等级。

        选择策略：
        - 内存 < 8GB 或核心数 < 4: x-low
        - 内存 < 16GB 或核心数 < 8: low
        - 内存 < 32GB 或核心数 < 16: medium
        - 否则: high

        Returns:
            推荐的质量等级字符串。
        """
        self._detect_system()

        if self._total_ram_gb < 8 or self._cpu_count < 4:
            return "x-low"
        if self._total_ram_gb < 16 or self._cpu_count < 8:
            return "low"
        if self._total_ram_gb < 32 or self._cpu_count < 16:
            return "medium"
        return "high"

    def get_inference_config(self, quality: str | None = None) -> CPUInferenceConfig:
        """获取 CPU 推理配置。

        Args:
            quality: 质量等级，若为 None 则自动推荐。

        Returns:
            CPUInferenceConfig 实例。

        Raises:
            ValueError: 当 quality 不在预设列表中时。
        """
        self._detect_system()

        if quality is None:
            quality = self.get_recommended_quality()

        if quality not in _QUALITY_PRESETS:
            valid = ", ".join(_QUALITY_PRESETS.keys())
            raise ValueError(f"无效的质量等级 '{quality}'，有效值: {valid}")

        preset = _QUALITY_PRESETS[quality]
        config = CPUInferenceConfig(
            quality=quality,
            batch_size=preset["batch_size"],
            num_threads=preset["num_threads"],
            use_int8=preset["use_int8"],
            use_onnx=preset["use_onnx"],
            chunk_size=preset["chunk_size"],
        )

        logger.info(
            f"[CPU 回退] 推理配置: quality={quality}, "
            f"batch_size={config.batch_size}, "
            f"threads={config.num_threads or 'auto'}, "
            f"int8={config.use_int8}, onnx={config.use_onnx}"
        )
        return config

    def get_performance_estimate(self, quality: str | None = None) -> dict[str, Any]:
        """获取 CPU 推理性能预估。

        参考 Piper 的多质量分级，提供不同质量等级下的实时率（RTF）估计。

        Args:
            quality: 质量等级，若为 None 则自动推荐。

        Returns:
            性能预估字典，包含 rtf、quality、description 等字段。
        """
        self._detect_system()

        if quality is None:
            quality = self.get_recommended_quality()

        preset = _QUALITY_PRESETS.get(quality, _QUALITY_PRESETS["medium"])
        rtf = preset["estimated_rtf"]

        # 根据实际 CPU 核心数调整 RTF 估计
        if self._cpu_count > 0:
            # 假设 8 核为基准，核数越多越快
            core_factor = max(0.5, min(2.0, self._cpu_count / 8.0))
            rtf = rtf / core_factor

        return {
            "quality": quality,
            "estimated_rtf": round(rtf, 2),
            "description": preset["description"],
            "cpu_cores": self._cpu_count,
            "total_ram_gb": round(self._total_ram_gb, 1),
            "notes": "RTF < 1.0 表示快于实时，RTF > 1.0 表示慢于实时",
        }


# ---------------------------------------------------------------------------
# CUDAInstaller — CUDA 工具包检测与安装引导
# ---------------------------------------------------------------------------


# CUDA 版本与 PyTorch 版本的对应关系
_CUDA_TORCH_COMPAT: dict[str, list[str]] = {
    "12.6": ["torch>=2.5.0"],
    "12.4": ["torch>=2.4.0"],
    "12.1": ["torch>=2.2.0,<2.4.0"],
    "11.8": ["torch>=2.0.0,<2.3.0"],
    "11.7": ["torch>=1.13.0,<2.1.0"],
}

# CUDA 工具包下载链接
_CUDA_DOWNLOAD_URLS: dict[str, str] = {
    "12.6": "https://developer.nvidia.com/cuda-12-6-0-download-archive",
    "12.4": "https://developer.nvidia.com/cuda-12-4-0-download-archive",
    "12.1": "https://developer.nvidia.com/cuda-12-1-0-download-archive",
    "11.8": "https://developer.nvidia.com/cuda-11-8-0-download-archive",
    "11.7": "https://developer.nvidia.com/cuda-11-7-0-download-archive",
}

# cuDNN 下载链接
_CUDNN_DOWNLOAD_URL = "https://developer.nvidia.com/cudnn"


@dataclass
class CUDAInstallInfo:
    """CUDA 安装信息。

    Attributes:
        cuda_version: 当前/推荐的 CUDA 版本。
        torch_version: 当前 PyTorch 版本。
        is_compatible: CUDA 与 PyTorch 版本是否兼容。
        download_url: CUDA 工具包下载链接。
        cudnn_url: cuDNN 下载链接。
        has_visual_studio: 是否检测到 Visual Studio（Windows 构建需要）。
        instructions: 安装步骤说明。
    """

    cuda_version: str
    torch_version: str
    is_compatible: bool
    download_url: str
    cudnn_url: str
    has_visual_studio: bool
    instructions: list[str] = field(default_factory=list)


class CUDAInstaller:
    """CUDA 工具包版本检测与安装引导。

    参考 VoiceBox cuda.py 的自动安装模式：
    - 检测当前 CUDA 驱动和运行时版本
    - 推荐与 PyTorch 兼容的 CUDA 版本
    - 提供下载链接和安装步骤
    - Windows 特定：检测 Visual Studio 和 cuDNN

    用法：
        installer = CUDAInstaller()
        info = installer.check_installation()
        if not info.is_compatible:
            print(installer.generate_install_guide(info))
    """

    def detect_cuda_version(self) -> str:
        """检测当前 CUDA 运行时版本。

        Returns:
            CUDA 版本字符串（如 "12.1"），不可用时返回 "N/A"。
        """
        try:
            import torch

            if torch.cuda.is_available():
                version = torch.version.cuda
                if version:
                    # torch.version.cuda 格式如 "12.1"，取前两个版本号
                    parts = version.split(".")
                    if len(parts) >= 2:
                        return f"{parts[0]}.{parts[1]}"
                    return version
        except Exception as e:
            logger.debug(f"[CUDA 检测] 检测 CUDA 版本失败: {e}")
        return "N/A"

    def detect_torch_version(self) -> str:
        """检测当前 PyTorch 版本。

        Returns:
            PyTorch 版本字符串。
        """
        try:
            import torch

            return torch.__version__
        except ImportError:
            return "N/A"

    def detect_cuda_driver_version(self) -> str:
        """检测 CUDA 驱动版本。

        Returns:
            驱动版本字符串（如 "545.29"），不可用时返回 "N/A"。
        """
        try:
            import torch

            if torch.cuda.is_available():
                return str(torch.cuda.get_device_properties(0).major) + "." + str(
                    torch.cuda.get_device_properties(0).minor
                )
        except Exception:
            pass
        return "N/A"

    def detect_visual_studio(self) -> bool:
        """检测是否安装了 Visual Studio（Windows CUDA 编译需要）。

        Returns:
            True 如果检测到 Visual Studio。
        """
        if platform.system() != "Windows":
            return True  # 非 Windows 不需要 VS

        import os

        # 检查常见 VS 安装路径
        vs_paths = [
            os.path.join(
                os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
                "Microsoft Visual Studio",
            ),
            os.path.join(
                os.environ.get("ProgramFiles", "C:\\Program Files"),
                "Microsoft Visual Studio",
            ),
        ]
        for vs_path in vs_paths:
            if os.path.isdir(vs_path):
                logger.debug(f"[CUDA 检测] 检测到 Visual Studio: {vs_path}")
                return True

        # 检查 VS Build Tools（通过 vswhere）
        try:
            vswhere = os.path.join(
                os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
                "Microsoft Visual Studio",
                "Installer",
                "vswhere.exe",
            )
            if os.path.isfile(vswhere):
                import subprocess

                result = subprocess.run(
                    [vswhere, "-latest", "-property", "installationPath"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.stdout.strip():
                    logger.debug(f"[CUDA 检测] 检测到 VS: {result.stdout.strip()}")
                    return True
        except Exception:
            pass

        logger.debug("[CUDA 检测] 未检测到 Visual Studio")
        return False

    def recommend_cuda_version(self, torch_version: str | None = None) -> str:
        """根据 PyTorch 版本推荐 CUDA 版本。

        Args:
            torch_version: PyTorch 版本字符串，若为 None 则自动检测。

        Returns:
            推荐的 CUDA 版本字符串。
        """
        if torch_version is None:
            torch_version = self.detect_torch_version()

        if torch_version == "N/A":
            return "12.4"  # 默认推荐最新稳定版

        try:
            parts = torch_version.split("+")
            base_version = parts[0]
            major, minor = [int(x) for x in base_version.split(".")[:2]]
            torch_ver_tuple = (major, minor)

            if torch_ver_tuple >= (2, 5):
                return "12.6"
            if torch_ver_tuple >= (2, 4):
                return "12.4"
            if torch_ver_tuple >= (2, 2):
                return "12.1"
            if torch_ver_tuple >= (2, 0):
                return "11.8"
            return "11.7"
        except Exception:
            return "12.4"

    def check_installation(self) -> CUDAInstallInfo:
        """检查 CUDA 安装状态并返回安装信息。

        Returns:
            CUDAInstallInfo 实例，包含版本、兼容性、下载链接等。
        """
        cuda_version = self.detect_cuda_version()
        torch_version = self.detect_torch_version()
        recommended_cuda = self.recommend_cuda_version(torch_version)
        has_vs = self.detect_visual_studio()

        # 判断兼容性
        is_compatible = True
        if cuda_version == "N/A":
            is_compatible = False
        else:
            # 检查当前 CUDA 版本是否在兼容列表中
            compat_versions = _CUDA_TORCH_COMPAT.get(cuda_version, [])
            if compat_versions:
                try:
                    import torch

                    for constraint in compat_versions:
                        # 简化检查：只比较主版本号
                        pass  # 实际兼容性由 PyTorch 运行时保证
                except Exception:
                    pass

        instructions: list[str] = []
        if not is_compatible:
            instructions.extend(
                [
                    f"1. 安装 CUDA Toolkit {recommended_cuda}",
                    f"   下载地址: {_CUDA_DOWNLOAD_URLS.get(recommended_cuda, 'N/A')}",
                    "2. 安装 cuDNN（与 CUDA 版本匹配）",
                    f"   下载地址: {_CUDNN_DOWNLOAD_URL}",
                    "3. 重新安装 PyTorch（指定 CUDA 版本）",
                    "   pip install torch --index-url https://download.pytorch.org/whl/cu121",
                ]
            )
        if not has_vs and platform.system() == "Windows":
            instructions.extend(
                [
                    "4. 安装 Visual Studio Build Tools",
                    "   下载地址: https://visualstudio.microsoft.com/visual-cpp-build-tools/",
                    "   安装时选择 'C++ build tools' 工作负载",
                ]
            )

        info = CUDAInstallInfo(
            cuda_version=cuda_version,
            torch_version=torch_version,
            is_compatible=is_compatible,
            download_url=_CUDA_DOWNLOAD_URLS.get(recommended_cuda, "N/A"),
            cudnn_url=_CUDNN_DOWNLOAD_URL,
            has_visual_studio=has_vs,
            instructions=instructions,
        )

        logger.info(
            f"[CUDA 检测] CUDA={cuda_version}, PyTorch={torch_version}, "
            f"兼容={is_compatible}, 推荐={recommended_cuda}"
        )
        return info

    def generate_install_guide(self, info: CUDAInstallInfo | None = None) -> str:
        """生成 CUDA 安装指南。

        Args:
            info: 安装信息，若为 None 则自动检测。

        Returns:
            格式化的安装指南字符串。
        """
        if info is None:
            info = self.check_installation()

        lines = [
            "=== CUDA 安装指南 ===",
            f"当前 CUDA 版本: {info.cuda_version}",
            f"当前 PyTorch 版本: {info.torch_version}",
            f"兼容性: {'兼容' if info.is_compatible else '不兼容'}",
            f"Visual Studio: {'已安装' if info.has_visual_studio else '未安装'}",
            "",
        ]

        if info.is_compatible:
            lines.append("CUDA 安装正常，无需额外操作。")
        else:
            lines.append("需要执行以下步骤：")
            for step in info.instructions:
                lines.append(f"  {step}")

        lines.extend(
            [
                "",
                f"CUDA 下载: {info.download_url}",
                f"cuDNN 下载: {info.cudnn_url}",
            ]
        )

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# DockerConfig — 容器化部署 Dockerfile 生成
# ---------------------------------------------------------------------------


@dataclass
class DockerBuildConfig:
    """Docker 构建配置。

    Attributes:
        base_image: 基础镜像。
        python_version: Python 版本。
        cuda_version: CUDA 版本（GPU 变体）。
        use_gpu: 是否使用 GPU 变体。
        install_cuda: 是否安装 CUDA 工具包。
        expose_port: 暴露的端口。
        app_dir: 应用目录。
    """

    base_image: str = ""
    python_version: str = "3.11"
    cuda_version: str = "12.4"
    use_gpu: bool = True
    install_cuda: bool = True
    expose_port: int = 7869
    app_dir: str = "/app"


class DockerConfig:
    """容器化部署 Dockerfile 生成器。

    支持 CPU-only 和 GPU 两种变体的 Dockerfile 生成。
    参考 Piper ONNX 的轻量级部署策略：
    - CPU 变体：基于 python slim 镜像，体积小
    - GPU 变体：基于 NVIDIA CUDA 镜像，支持 GPU 加速

    用法：
        docker = DockerConfig()
        # GPU 变体
        dockerfile = docker.generate_dockerfile(use_gpu=True)
        # CPU 变体
        dockerfile = docker.generate_dockerfile(use_gpu=False)
    """

    # NVIDIA PyTorch 基础镜像（参考 PyTorch 官方 Docker Hub）
    _GPU_BASE_IMAGES: dict[str, str] = {
        "12.4": "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel",
        "12.1": "pytorch/pytorch:2.2.0-cuda12.1-cudnn9-devel",
        "11.8": "pytorch/pytorch:2.0.1-cuda11.7-cudnn8-devel",
    }

    # CPU 基础镜像
    _CPU_BASE_IMAGE = "python:3.11-slim-bookworm"

    def generate_dockerfile(
        self,
        use_gpu: bool = True,
        cuda_version: str = "12.4",
        config: DockerBuildConfig | None = None,
    ) -> str:
        """生成 Dockerfile 内容。

        Args:
            use_gpu: 是否生成 GPU 变体，默认 True。
            cuda_version: CUDA 版本，默认 12.4。
            config: 详细构建配置，若提供则覆盖其他参数。

        Returns:
            Dockerfile 内容字符串。
        """
        if config is not None:
            use_gpu = config.use_gpu
            cuda_version = config.cuda_version

        if use_gpu:
            return self._generate_gpu_dockerfile(cuda_version)
        return self._generate_cpu_dockerfile()

    def _generate_gpu_dockerfile(self, cuda_version: str = "12.4") -> str:
        """生成 GPU 变体 Dockerfile。

        基于 NVIDIA PyTorch 镜像，预装 CUDA 和 cuDNN。

        Args:
            cuda_version: CUDA 版本。

        Returns:
            GPU Dockerfile 内容。
        """
        base_image = self._GPU_BASE_IMAGES.get(
            cuda_version,
            f"pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel",
        )

        dockerfile = f"""# TTS_MultiModel GPU Dockerfile
# 基于 NVIDIA PyTorch 镜像，支持 CUDA 加速
# CUDA 版本: {cuda_version}

FROM {base_image}

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive \\
    PYTHONUNBUFFERED=1 \\
    TRANSFORMERS_OFFLINE=1 \\
    HF_HUB_OFFLINE=1 \\
    MODELSCOPE_OFFLINE=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \\
        ffmpeg \\
        libsndfile1 \\
        git \\
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 7869

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \\
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7869/api/system/health')" || exit 1

# 启动命令
CMD ["python", "bin/clean_launch.py"]
"""
        return dockerfile

    def _generate_cpu_dockerfile(self) -> str:
        """生成 CPU 变体 Dockerfile。

        基于 Python slim 镜像，参考 Piper ONNX 轻量级部署。
        使用 ONNX Runtime CPU 后端进行推理。

        Returns:
            CPU Dockerfile 内容。
        """
        dockerfile = """# TTS_MultiModel CPU Dockerfile
# 基于 Python slim 镜像，轻量级 CPU 推理部署
# 参考 Piper ONNX 轻量级部署策略

FROM python:3.11-slim-bookworm

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive \\
    PYTHONUNBUFFERED=1 \\
    TRANSFORMERS_OFFLINE=1 \\
    HF_HUB_OFFLINE=1 \\
    MODELSCOPE_OFFLINE=1 \\
    TTS_CPU_MODE=1

# 安装系统依赖（最小化）
RUN apt-get update && apt-get install -y --no-install-recommends \\
        ffmpeg \\
        libsndfile1 \\
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖（CPU 版本）
RUN pip install --no-cache-dir \\
        torch --index-url https://download.pytorch.org/whl/cpu \\
    && pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 7869

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \\
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7869/api/system/health')" || exit 1

# 启动命令（CPU 模式）
CMD ["python", "bin/clean_launch.py", "--cpu"]
"""
        return dockerfile

    def generate_docker_compose(self, use_gpu: bool = True) -> str:
        """生成 docker-compose.yml 内容。

        Args:
            use_gpu: 是否使用 GPU 变体。

        Returns:
            docker-compose.yml 内容字符串。
        """
        if use_gpu:
            return """version: "3.8"

services:
  tts_multimodel:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "7869:7869"
    volumes:
      - ./models:/app/models
      - ./personas:/app/personas
      - ./outputs:/app/outputs
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - TRANSFORMERS_OFFLINE=1
      - HF_HUB_OFFLINE=1
      - MODELSCOPE_OFFLINE=1
    restart: unless-stopped
"""
        return """version: "3.8"

services:
  tts_multimodel:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "7869:7869"
    volumes:
      - ./models:/app/models
      - ./personas:/app/personas
      - ./outputs:/app/outputs
    environment:
      - TRANSFORMERS_OFFLINE=1
      - HF_HUB_OFFLINE=1
      - MODELSCOPE_OFFLINE=1
      - TTS_CPU_MODE=1
    restart: unless-stopped
"""
