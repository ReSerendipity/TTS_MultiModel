"""
TTS MultiModel - API Usage Examples

Demonstrates how to interact with the TTS MultiModel REST API using Python.

Requirements:
    pip install httpx

Usage:
    1. Start the server: start.bat
    2. Run: python examples/api_example.py
"""

import json
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("请先安装依赖: pip install httpx")
    sys.exit(1)

BASE_URL = "http://localhost:7869"


def example_health_check():
    """Example: Check server health."""
    print("--- Health Check ---")
    resp = httpx.get(f"{BASE_URL}/api/system/health", timeout=5)
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
    print()


def example_gpu_info():
    """Example: Get GPU utilization info."""
    print("--- GPU Info ---")
    resp = httpx.get(f"{BASE_URL}/api/system/gpu", timeout=5)
    print(f"Status: {resp.status_code}")
    data = resp.json()
    if "gpu_name" in data:
        print(f"GPU: {data.get('gpu_name', 'N/A')}")
        print(f"VRAM Used: {data.get('vram_used_mb', 0):.0f} MB")
        print(f"VRAM Total: {data.get('vram_total_mb', 0):.0f} MB")
        print(f"Utilization: {data.get('gpu_utilization', 0):.0f}%")
    else:
        print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
    print()


def example_model_management():
    """Example: Load and unload models."""
    print("--- Model Management ---")

    # Load VoxCPM2
    print("[1] Loading VoxCPM2 engine...")
    resp = httpx.post(
        f"{BASE_URL}/api/model/load",
        json={"engine": "voxcpm2"},
        timeout=120,
    )
    print(f"    Status: {resp.status_code}")

    # Check model status
    print("[2] Checking model status...")
    resp = httpx.get(f"{BASE_URL}/api/model/status", timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        print(f"    Current engine: {data.get('current_engine', 'N/A')}")

    print()


def example_voice_design():
    """Example: Generate speech from voice description."""
    print("--- Voice Design (VoxCPM2) ---")

    resp = httpx.post(
        f"{BASE_URL}/api/generate/voxcpm2/design",
        data={
            "text": "(温柔的女声) 你好，欢迎使用 TTS MultiModel 语音合成平台。",
            "cfg_value": "2.0",
            "inference_timesteps": "10",
        },
        timeout=60,
    )

    if resp.status_code == 200:
        output_path = "output_design.wav"
        Path(output_path).write_bytes(resp.content)
        print(f"[OK] 语音设计完成: {output_path}")
    else:
        print(f"[ERROR] {resp.status_code}: {resp.text[:200]}")
    print()


def example_history():
    """Example: Query generation history."""
    print("--- History Query ---")

    resp = httpx.get(
        f"{BASE_URL}/api/history",
        params={"page": 1, "page_size": 5},
        timeout=5,
    )

    if resp.status_code == 200:
        data = resp.json()
        records = data.get("records", [])
        print(f"Total records: {data.get('total', 0)}")
        for i, record in enumerate(records[:5]):
            print(f"  [{i+1}] {record.get('text', '')[:50]}... ({record.get('engine', 'N/A')})")
    else:
        print(f"[ERROR] {resp.status_code}")
    print()


def main():
    print("=" * 60)
    print("TTS MultiModel - API Usage Examples")
    print("=" * 60)
    print()

    # Check server first
    try:
        httpx.get(f"{BASE_URL}/api/system/health", timeout=3)
    except httpx.ConnectError:
        print("[ERROR] 服务器未运行，请先启动: start.bat")
        return 1

    # Run examples
    example_health_check()
    example_gpu_info()
    example_model_management()
    example_voice_design()
    example_history()

    print("=" * 60)
    print("All examples completed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
