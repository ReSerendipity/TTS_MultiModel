#!/usr/bin/env python
"""dots.tts 快速克隆示例 — 最简调用路径。

演示如何通过 HTTP API 使用 dots.tts 引擎进行语音克隆。
仅需 1 行代码即可完成克隆请求。

使用前请确保：
1. 服务器已启动（python bin/integrated_app/app_server.py 或 start.bat）
2. dots.tts 模型已加载
3. 已准备好参考音频文件（WAV/MP3，约10秒）

用法：
    python examples/dotstts_clone_quick.py
"""

import requests

SERVER = "http://127.0.0.1:7869"


def quick_clone(ref_audio_path: str, text: str, output: str = "output.wav"):
    """一行代码完成 dots.tts 克隆。

    Args:
        ref_audio_path: 参考音频文件路径。
        text: 要合成的文本。
        output: 输出文件路径。
    """
    with open(ref_audio_path, "rb") as f:
        resp = requests.post(
            f"{SERVER}/api/generate/generic/clone",
            files={"ref_audio": f},
            data={
                "engine": "dotstts",
                "text": text,
                "language": "auto",
                "num_steps": "10",
                "guidance_scale": "1.2",
                "random_seed": "true",
            },
            timeout=120,
        )
    resp.raise_for_status()

    if "audio" in resp.headers.get("content-type", ""):
        with open(output, "wb") as f:
            f.write(resp.content)
        print(f"音频已保存: {output}")
    else:
        print(f"API 响应: {resp.json()}")


if __name__ == "__main__":
    # 使用项目自带的参考音频
    import os

    ref = os.path.join(os.path.dirname(__file__), "reference_speaker.wav")
    if not os.path.exists(ref):
        print(f"参考音频不存在: {ref}")
        exit(1)

    quick_clone(ref, "你好，这是 dots.tts 快速克隆测试。")
