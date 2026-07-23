"""
TTS MultiModel - Batch Processing Example

Demonstrates how to batch-generate speech from a list of texts.

Requirements:
    pip install httpx

Usage:
    python examples/batch_example.py
"""

import json
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("请先安装依赖: pip install httpx")
    sys.exit(1)

BASE_URL = "http://localhost:7869"


def batch_generate(
    texts: list[str],
    output_dir: str = "batch_output",
    engine: str = "voxcpm2",
) -> list[Path]:
    """
    Batch-generate speech for a list of texts.

    Args:
        texts: List of text strings to synthesize.
        output_dir: Directory to save generated audio files.
        engine: TTS engine to use.

    Returns:
        List of output file paths.
    """
    out = Path(output_dir)
    out.mkdir(exist_ok=True)

    results = []
    for i, text in enumerate(texts):
        print(f"[{i+1}/{len(texts)}] Generating: {text[:40]}...")

        start = time.time()
        try:
            resp = httpx.post(
                f"{BASE_URL}/api/generate/{engine}/design",
                data={
                    "text": text,
                    "cfg_value": "2.0",
                    "inference_timesteps": "10",
                },
                timeout=120,
            )

            if resp.status_code == 200:
                output_path = out / f"batch_{i:03d}.wav"
                output_path.write_bytes(resp.content)
                elapsed = time.time() - start
                size_kb = len(resp.content) / 1024
                print(f"  [OK] {output_path.name} ({size_kb:.1f} KB, {elapsed:.1f}s)")
                results.append(output_path)
            else:
                print(f"  [ERROR] {resp.status_code}")

        except Exception as e:
            print(f"  [ERROR] {e}")

    return results


def main():
    print("=" * 60)
    print("TTS MultiModel - Batch Processing Example")
    print("=" * 60)
    print()

    # Check server
    try:
        httpx.get(f"{BASE_URL}/api/system/health", timeout=3)
    except httpx.ConnectError:
        print("[ERROR] 服务器未运行，请先启动: start.bat")
        return 1

    # Define texts to generate
    texts = [
        "今天天气真不错，适合出去走走。",
        "欢迎使用 TTS MultiModel 语音合成平台。",
        "这个项目支持多种语音合成引擎。",
        "声音克隆技术让 AI 更加个性化。",
        "感谢所有开源贡献者的努力。",
    ]

    print(f"准备生成 {len(texts)} 条语音...")
    print()

    start = time.time()
    results = batch_generate(texts, output_dir="batch_output")
    total_time = time.time() - start

    print()
    print(f"完成！成功生成 {len(results)}/{len(texts)} 条语音")
    print(f"总耗时: {total_time:.1f}s")
    print(f"输出目录: batch_output/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
