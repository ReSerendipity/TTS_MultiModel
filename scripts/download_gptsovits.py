"""
TTS MultiModel - GPT-SoVITS 模型下载脚本
========================================

项目名称: TTS MultiModel (多引擎语音合成平台)
主要功能: 从 ModelScope / HuggingFace 下载 GPT-SoVITS v2 引擎所需的预训练权重

GPT-SoVITS 引擎特性:
    - 少样本 / 零样本语音克隆（仅需 3~10 秒参考音频）
    - 中/英/日/韩/粤多语种与跨语种合成
    - 进程内推理（GPT s1 自回归 + SoVITS s2 声学双模型）
    - 最低硬件要求: 约 4GB VRAM

下载内容（放置于 pretrained_models/GPT-SoVITS/）:
    - GPT 权重 (*.ckpt)              - s1 自回归模型
    - SoVITS 权重 (*.pth)            - s2 声学模型
    - chinese-hubert-base/           - 中文 HuBERT 特征提取器
    - chinese-roberta-wwm-ext-large/ - 中文 RoBERTa BERT

依赖要求:
    pip install modelscope

使用方法:
    python scripts/download_gptsovits.py

下载完成后:
    1. 安装 GPT-SoVITS 推理依赖:
       pip install -r reference_repos/GPT-SoVITS/requirements.txt
    2. 重启应用，GPT-SoVITS 引擎将自动出现在引擎切换选项中

注意事项:
    - 仅在推理前离线下载，运行期不会自动联网下载
    - 支持断点续传，重复运行不会重复下载已有文件
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

#: ModelScope 上的 GPT-SoVITS 预训练权重仓库。
_REPO_ID = "AI-ModelScope/GPT-SoVITS"


def download_gptsovits_model() -> bool:
    """从 ModelScope 下载 GPT-SoVITS v2 预训练权重到本地目录。

    Returns:
        bool: True 表示下载成功，False 表示下载失败。
    """
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError:
        logger.error("modelscope 未安装，请先运行: pip install modelscope")
        sys.exit(1)

    project_root = Path(__file__).parent.parent
    model_dir = project_root / "pretrained_models" / "GPT-SoVITS"

    logger.info(f"目标目录: {model_dir}")
    logger.info("开始下载 GPT-SoVITS v2 预训练权重...")
    logger.info("内容清单:")
    logger.info("  - GPT 权重 (*.ckpt)")
    logger.info("  - SoVITS 权重 (*.pth)")
    logger.info("  - chinese-hubert-base/")
    logger.info("  - chinese-roberta-wwm-ext-large/")
    logger.info("")
    logger.info("请耐心等待...")

    try:
        cache_dir = model_dir.parent / ".cache" / "gptsovits"
        downloaded_path = snapshot_download(
            _REPO_ID, cache_dir=str(cache_dir), local_dir=str(model_dir)
        )
        logger.info(f"下载完成: {downloaded_path}")

        # 校验关键权重是否存在
        has_ckpt = any(model_dir.rglob("*.ckpt"))
        has_pth = any(model_dir.rglob("*.pth"))
        has_hubert = (model_dir / "chinese-hubert-base").is_dir()
        has_bert = (model_dir / "chinese-roberta-wwm-ext-large").is_dir()

        missing = []
        if not has_ckpt:
            missing.append("GPT 权重 (*.ckpt)")
        if not has_pth:
            missing.append("SoVITS 权重 (*.pth)")
        if not has_hubert:
            missing.append("chinese-hubert-base/")
        if not has_bert:
            missing.append("chinese-roberta-wwm-ext-large/")

        if missing:
            logger.warning(f"缺少内容: {missing}")
            logger.warning(
                "若使用的仓库结构不同，请手动将 GPT/SoVITS 权重与 "
                "chinese-hubert-base、chinese-roberta-wwm-ext-large 放入上述目录。"
            )
            return False
        logger.info("所有必需权重下载完成！")
        return True

    except Exception as e:
        logger.error(f"下载失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main() -> int:
    """脚本主入口。

    Returns:
        int: 0 表示成功，1 表示失败。
    """
    print("=" * 60)
    print("GPT-SoVITS 模型下载工具")
    print("=" * 60)
    print()

    success = download_gptsovits_model()

    print()
    if success:
        print("✅ 下载完成！")
        print()
        print("下一步:")
        print("  1. 安装依赖: pip install -r reference_repos/GPT-SoVITS/requirements.txt")
        print("  2. 重启应用，GPT-SoVITS 引擎将自动可用")
    else:
        print("❌ 下载未完成，请检查网络连接与仓库结构后重试")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
