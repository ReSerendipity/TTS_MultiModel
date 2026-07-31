# -*- coding: utf-8 -*-
"""
TTS MultiModel - 批量语音合成示例
==================================

项目名称: TTS MultiModel (多引擎语音合成平台)
主要功能: 演示如何批量处理多条文本，实现大规模语音合成任务
核心技术栈: Python + httpx 异步 HTTP 客户端 + FastAPI 后端
适用场景:
    - 有声读物批量制作
    - 多角色对话批量生成
    - 语音数据集构建
    - 批量配音任务处理
关键注意事项:
    - 运行前需先启动服务端 (start.bat 或 python bin/clean_launch.py)
    - 默认服务地址: http://127.0.0.1:7869
    - 批量任务会按顺序串行处理，避免显存溢出
    - 建议单批次文本数量控制在 10-50 条，过多可能导致超时
    - 每条音频生成时间约 2-10 秒（取决于文本长度和硬件性能）
    - 生成失败的条目会被跳过，不影响后续任务

依赖要求:
    pip install httpx

使用方法:
    1. 启动服务端: start.bat (Windows) 或 python bin/clean_launch.py
    2. 运行示例: python examples/batch_example.py
"""

import json
import sys
import time
from pathlib import Path

# 尝试导入 httpx HTTP 客户端库
try:
    import httpx
except ImportError:
    print("请先安装 httpx 依赖: pip install httpx")
    sys.exit(1)

# 服务端基础 URL 配置
BASE_URL = "http://localhost:7869"


def batch_generate(
    texts: list[str],
    output_dir: str = "batch_output",
    engine: str = "voxcpm2",
) -> list[Path]:
    """
    批量语音合成函数

    功能说明:
        接收文本列表，逐条调用 TTS API 生成语音并保存到指定目录
        处理过程中实时显示进度、文件大小和耗时统计
        单条失败不中断整体流程，错误信息会打印到控制台

    Args:
        texts: 待合成的文本字符串列表，建议每条文本长度 10-200 字
        output_dir: 输出目录路径，默认 "batch_output"，不存在会自动创建
        engine: 使用的 TTS 引擎，可选 "voxcpm2" (默认) 或 "indextts2"

    Returns:
        list[Path]: 成功生成的音频文件路径列表，可用于后续处理或校验

    生成参数说明:
        - cfg_value: CFG 引导系数，控制生成语音与风格描述的匹配度 (默认 2.0)
        - inference_timesteps: 扩散模型推理步数，影响质量和速度 (默认 10)

    文件命名规则:
        输出文件按顺序命名为: batch_000.wav, batch_001.wav, ...
        三位数字序号便于排序和后续批量处理
    """
    # 创建输出目录，exist_ok=True 表示目录已存在时不报错
    out = Path(output_dir)
    out.mkdir(exist_ok=True)

    # 用于收集成功生成的文件路径
    results = []

    # 逐条处理文本，enumerate 同时获取索引和文本内容
    for i, text in enumerate(texts):
        # 打印进度，文本截取前 40 字符显示
        print(f"[{i+1}/{len(texts)}] 正在生成: {text[:40]}...")

        # 记录本条开始时间，用于统计单条耗时
        start = time.time()
        try:
            # 调用语音设计 API 端点
            resp = httpx.post(
                f"{BASE_URL}/api/generate/{engine}/design",
                data={
                    "text": text,
                    "cfg_value": "2.0",              # CFG 引导强度
                    "inference_timesteps": "10",     # 推理步数
                },
                timeout=120,  # 单条超时 120 秒，长文本需要更长时间
            )

            if resp.status_code == 200:
                # 生成成功: 构建输出文件路径，使用三位数字序号补零
                output_path = out / f"batch_{i:03d}.wav"
                # 写入音频二进制数据到文件
                output_path.write_bytes(resp.content)
                # 计算耗时和文件大小
                elapsed = time.time() - start
                size_kb = len(resp.content) / 1024
                print(f"  [成功] {output_path.name} ({size_kb:.1f} KB, 耗时 {elapsed:.1f}s)")
                results.append(output_path)
            else:
                # API 返回错误状态码
                print(f"  [失败] HTTP {resp.status_code}")

        except Exception as e:
            # 捕获网络超时、连接错误等异常
            print(f"  [异常] {e}")

    return results


def main():
    """
    主函数: 执行批量生成示例

    执行流程:
        1. 检查服务端连接状态
        2. 定义待合成的示例文本列表
        3. 调用 batch_generate 执行批量生成
        4. 统计并展示生成结果（成功率、总耗时）

    返回值:
        int: 0 表示执行完成（即使部分失败也返回 0），1 表示服务未启动
    """
    print("=" * 60)
    print("TTS MultiModel - 批量语音合成示例")
    print("=" * 60)
    print()

    # 步骤 1: 检查服务端是否运行
    print("[检查] 正在连接服务端...")
    try:
        httpx.get(f"{BASE_URL}/api/system/health", timeout=3)
        print("[OK] 服务端连接成功!")
    except httpx.ConnectError:
        print("[ERROR] 无法连接到服务端!")
        print("       请先启动服务: start.bat (Windows) 或 python bin/clean_launch.py")
        return 1
    print()

    # 步骤 2: 定义待合成的示例文本（可替换为自己的文本列表）
    texts = [
        "今天天气真不错，适合出去走走。",
        "欢迎使用 TTS MultiModel 语音合成平台。",
        "这个项目支持多种语音合成引擎。",
        "声音克隆技术让 AI 更加个性化。",
        "感谢所有开源贡献者的努力。",
    ]

    print(f"准备批量生成 {len(texts)} 条语音...")
    print(f"输出目录: batch_output/")
    print()

    # 步骤 3: 执行批量生成并计时
    start = time.time()
    results = batch_generate(texts, output_dir="batch_output")
    total_time = time.time() - start

    # 步骤 4: 输出统计结果
    print()
    print("=" * 60)
    print(f"批量生成完成!")
    print(f"成功: {len(results)}/{len(texts)} 条")
    success_rate = (len(results) / len(texts)) * 100 if texts else 0
    print(f"成功率: {success_rate:.1f}%")
    print(f"总耗时: {total_time:.1f} 秒")
    if len(results) > 0:
        avg_time = total_time / len(results)
        print(f"平均每条耗时: {avg_time:.1f} 秒")
    print(f"输出目录: batch_output/")
    print("=" * 60)

    return 0


# 脚本入口点
if __name__ == "__main__":
    sys.exit(main())
