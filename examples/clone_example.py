"""
TTS MultiModel - Voice Cloning Example

Demonstrates how to use the REST API to clone a voice using VoxCPM2.

Requirements:
    pip install httpx soundfile numpy

Usage:
    1. Start the TTS MultiModel server: start.bat (or python bin/clean_launch.py)
    2. Run this script: python examples/clone_example.py
"""

import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("请先安装依赖: pip install httpx")
    sys.exit(1)

BASE_URL = "http://localhost:7869"


def check_server() -> bool:
    """Check if the TTS MultiModel server is running."""
    try:
        resp = httpx.get(f"{BASE_URL}/api/system/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"[OK] 服务器运行中 - 状态: {data.get('status', 'unknown')}")
            return True
    except httpx.ConnectError:
        pass
    print("[ERROR] 服务器未运行，请先启动: start.bat 或 python bin/clean_launch.py")
    return False


def load_model(engine: str = "voxcpm2") -> bool:
    """Load a TTS engine."""
    print(f"[INFO] 正在加载 {engine} 引擎...")
    try:
        resp = httpx.post(
            f"{BASE_URL}/api/model/load",
            json={"engine": engine},
            timeout=120,
        )
        if resp.status_code == 200:
            print(f"[OK] {engine} 引擎加载成功")
            return True
        else:
            print(f"[ERROR] 加载失败: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"[ERROR] 加载异常: {e}")
        return False


def clone_voice(
    text: str,
    reference_audio_path: str,
    output_path: str = "output_clone.wav",
) -> bool:
    """
    Clone a voice using the VoxCPM2 clone API.

    Args:
        text: The text to synthesize.
        reference_audio_path: Path to the reference audio file (.wav).
        output_path: Path to save the generated audio.
    """
    ref_path = Path(reference_audio_path)
    if not ref_path.exists():
        print(f"[ERROR] 参考音频不存在: {reference_audio_path}")
        return False

    print(f"[INFO] 正在克隆语音...")
    print(f"  文本: {text}")
    print(f"  参考音频: {reference_audio_path}")

    try:
        with open(ref_path, "rb") as f:
            resp = httpx.post(
                f"{BASE_URL}/api/generate/voxcpm2/clone",
                data={
                    "text": text,
                    "cfg_value": "2.0",
                    "inference_timesteps": "10",
                    "normalize": "true",
                    "denoise": "true",
                },
                files={"reference_audio": (ref_path.name, f, "audio/wav")},
                timeout=120,
            )

        if resp.status_code == 200:
            # Save the audio response
            out = Path(output_path)
            out.write_bytes(resp.content)
            size_kb = len(resp.content) / 1024
            print(f"[OK] 语音生成成功: {output_path} ({size_kb:.1f} KB)")
            return True
        else:
            print(f"[ERROR] 生成失败: {resp.status_code} {resp.text[:200]}")
            return False

    except Exception as e:
        print(f"[ERROR] 生成异常: {e}")
        return False


def main():
    print("=" * 60)
    print("TTS MultiModel - Voice Cloning Example")
    print("=" * 60)
    print()

    # Step 1: Check server
    if not check_server():
        return 1

    # Step 2: Load model
    if not load_model("voxcpm2"):
        return 1

    # Step 3: Clone voice
    # You can replace this with any .wav reference audio
    reference_audio = "examples/reference_speaker.wav"
    if not Path(reference_audio).exists():
        print(f"[WARN] 参考音频不存在: {reference_audio}")
        print("  请准备一个 .wav 格式的参考音频文件")
        print("  或修改 reference_audio 变量指向你的音频文件")
        return 1

    success = clone_voice(
        text="你好，这是一段使用 TTS MultiModel 克隆的语音。",
        reference_audio_path=reference_audio,
        output_path="output_clone.wav",
    )

    if success:
        print()
        print("[DONE] 语音克隆完成！请播放 output_clone.wav 听效果。")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
