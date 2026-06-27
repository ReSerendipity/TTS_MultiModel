"""
IndexTTS 2.0 Model Download Script

Downloads IndexTTS 2.0 model files from ModelScope to the pretrained_models directory.
Requires: pip install modelscope

Usage:
    python scripts/download_indextts2.py
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def download_indextts2_model():
    """Download IndexTTS 2.0 model from ModelScope."""
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError:
        logger.error("modelscope 未安装，请先运行: pip install modelscope")
        sys.exit(1)

    project_root = Path(__file__).parent.parent
    model_dir = project_root / "pretrained_models" / "IndexTTS2"

    logger.info(f"目标目录: {model_dir}")
    logger.info("开始下载 IndexTTS 2.0 模型...")
    logger.info("模型列表:")
    logger.info("  - gpt.pth (~3.48GB)")
    logger.info("  - s2mel.pth (~1.20GB)")
    logger.info("  - bpe.model")
    logger.info("  - config.yaml")
    logger.info("  - feat1.pt")
    logger.info("  - feat2.pt")
    logger.info("  - wav2vec2bert_stats.pt")
    logger.info("")
    logger.info("总大小约 4.7GB，请耐心等待...")

    try:
        cache_dir = model_dir.parent / ".cache" / "indextts2"
        downloaded_path = snapshot_download("IndexTeam/IndexTTS-2", cache_dir=str(cache_dir), local_dir=str(model_dir))

        logger.info(f"下载完成: {downloaded_path}")

        # 验证文件
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
        for f in required_files:
            file_path = model_dir / f
            if not file_path.exists():
                missing_files.append(f)
            else:
                size_mb = file_path.stat().st_size / (1024 * 1024)
                logger.info(f"  ✓ {f} ({size_mb:.1f} MB)")

        if missing_files:
            logger.warning(f"缺少文件: {missing_files}")
        else:
            logger.info("所有文件下载完成！")

        return True

    except Exception as e:
        logger.error(f"下载失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("IndexTTS 2.0 模型下载工具")
    print("=" * 60)
    print()

    success = download_indextts2_model()

    print()
    if success:
        print("✅ 下载完成！")
        print()
        print("下一步:")
        print("  1. 安装 IndexTTS 2.0 依赖: pip install indextts")
        print("  2. 重启应用，IndexTTS 2.0 引擎将自动可用")
    else:
        print("❌ 下载失败，请检查网络连接后重试")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
