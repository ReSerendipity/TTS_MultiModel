#!/usr/bin/env python
"""dots.tts API 调用示例脚本。

演示如何通过 HTTP API 调用 dots.tts 引擎进行语音克隆。

使用前请确保：
1. 服务器已启动（python bin/integrated_app/app_server.py 或 start.bat）
2. dots.tts 模型已加载
3. 已准备好参考音频文件（WAV/MP3/FLAC/OGG，约10秒）

用法：
    python examples/call_dotstts_api.py --server http://127.0.0.1:7869 --ref ref.wav --text "你好世界"
"""

import argparse
import sys
import os

import requests


def main():
    parser = argparse.ArgumentParser(description="dots.tts API 调用示例")
    parser.add_argument("--server", default="http://127.0.0.1:7869", help="服务器地址")
    parser.add_argument("--ref", required=True, help="参考音频文件路径")
    parser.add_argument("--text", default="你好，这是dots.tts语音合成测试。", help="合成文本")
    parser.add_argument("--language", default="auto", choices=["auto", "zh", "en", "ja"], help="合成语言")
    parser.add_argument("--num-steps", type=int, default=10, help="推理步数（1-32）")
    parser.add_argument("--guidance", type=float, default=1.2, help="引导强度（0.5-3.0）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--random-seed", default="true", choices=["true", "false"], help="使用随机种子")
    parser.add_argument("--output", default="output_dotstts.wav", help="输出文件路径")
    args = parser.parse_args()

    # 检查参考音频
    if not os.path.exists(args.ref):
        print(f"错误：参考音频文件不存在: {args.ref}", file=sys.stderr)
        sys.exit(1)

    # 调用 API
    url = f"{args.server}/api/generate/generic/clone"
    files = {"ref_audio": open(args.ref, "rb")}
    data = {
        "engine": "dotstts",
        "text": args.text,
        "language": args.language,
        "num_steps": str(args.num_steps),
        "guidance_scale": str(args.guidance),
        "seed": str(args.seed),
        "random_seed": args.random_seed,
    }

    print(f"正在调用 dots.tts API: {url}")
    print(f"  参考音频: {args.ref}")
    print(f"  合成文本: {args.text}")
    print(f"  语言: {args.language}")
    print(f"  推理步数: {args.num_steps}")

    try:
        response = requests.post(url, files=files, data=data, timeout=120)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "audio" in content_type:
            with open(args.output, "wb") as f:
                f.write(response.content)
            print(f"音频已保存至: {args.output}")
        else:
            result = response.json()
            if "audio_path" in result:
                audio_url = f"{args.server}/api/audio/{result['audio_path']}"
                print(f"音频 URL: {audio_url}")
                audio_resp = requests.get(audio_url, timeout=30)
                with open(args.output, "wb") as f:
                    f.write(audio_resp.content)
                print(f"音频已保存至: {args.output}")
            else:
                print(f"API 响应: {result}")
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        files["ref_audio"].close()


if __name__ == "__main__":
    main()
