#!/usr/bin/env python
"""GPT-SoVITS API 调用示例脚本。

演示如何通过 HTTP API 调用 GPT-SoVITS 引擎进行语音克隆。

使用前请确保：
1. 服务器已启动（python bin/integrated_app/app_server.py 或 start.bat）
2. GPT-SoVITS 模型已加载
3. 已准备好参考音频文件（WAV/MP3/FLAC/OGG，3-10秒）

用法：
    python examples/call_gptsovits_api.py --server http://127.0.0.1:7869 --ref ref.wav --text "你好世界"
"""

import argparse
import sys
import os

import requests


def main():
    parser = argparse.ArgumentParser(description="GPT-SoVITS API 调用示例")
    parser.add_argument("--server", default="http://127.0.0.1:7869", help="服务器地址")
    parser.add_argument("--ref", required=True, help="参考音频文件路径")
    parser.add_argument("--text", default="你好，这是GPT-SoVITS语音合成测试。", help="合成文本")
    parser.add_argument("--text-lang", default="zh", choices=["zh", "en", "ja", "ko", "yue"], help="文本语言")
    parser.add_argument("--prompt-lang", default="zh", choices=["zh", "en", "ja"], help="参考音频语言")
    parser.add_argument("--prompt-text", default="", help="参考音频转录文本（可选）")
    parser.add_argument("--top-k", type=int, default=20, help="Top-K 采样")
    parser.add_argument("--top-p", type=float, default=0.6, help="Top-P 采样")
    parser.add_argument("--temperature", type=float, default=0.6, help="温度")
    parser.add_argument("--speed", type=float, default=1.0, help="语速倍率")
    parser.add_argument("--output", default="output_gptsovits.wav", help="输出文件路径")
    args = parser.parse_args()

    # 检查参考音频
    if not os.path.exists(args.ref):
        print(f"错误：参考音频文件不存在: {args.ref}", file=sys.stderr)
        sys.exit(1)

    # 调用 API
    url = f"{args.server}/api/generate/generic/clone"
    files = {"ref_audio": open(args.ref, "rb")}
    data = {
        "engine": "gptsovits",
        "text": args.text,
        "text_lang": args.text_lang,
        "prompt_lang": args.prompt_lang,
        "prompt_text": args.prompt_text,
        "top_k": str(args.top_k),
        "top_p": str(args.top_p),
        "temperature": str(args.temperature),
        "speed_factor": str(args.speed),
    }

    print(f"正在调用 GPT-SoVITS API: {url}")
    print(f"  参考音频: {args.ref}")
    print(f"  合成文本: {args.text}")
    print(f"  语言: {args.text_lang}")

    try:
        response = requests.post(url, files=files, data=data, timeout=120)
        response.raise_for_status()

        # 检查响应类型
        content_type = response.headers.get("content-type", "")
        if "audio" in content_type:
            with open(args.output, "wb") as f:
                f.write(response.content)
            print(f"音频已保存至: {args.output}")
        else:
            # JSON 响应
            result = response.json()
            if "audio_path" in result:
                audio_url = f"{args.server}/api/audio/{result['audio_path']}"
                print(f"音频 URL: {audio_url}")
                # 下载音频
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
