# -*- coding: utf-8 -*-
"""
TTS MultiModel - REST API 使用示例
==================================

项目名称: TTS MultiModel (多引擎语音合成平台)
主要功能: 演示如何通过 Python 调用 TTS MultiModel 的 REST API 接口
核心技术栈: Python + httpx HTTP 客户端 + FastAPI 后端
适用场景:
    - 健康检查与服务状态监控
    - GPU 资源使用情况查询
    - 模型动态加载与切换
    - 语音设计（文本描述生成语音）
    - 生成历史记录查询
关键注意事项:
    - 运行前需先启动服务端 (start.bat 或 python bin/clean_launch.py)
    - 默认服务地址: http://127.0.0.1:7869
    - 需要安装 httpx 依赖: pip install httpx
    - 模型加载可能需要较长时间 (10-60秒)，请耐心等待
    - 生成语音时显存需满足模型要求 (VoxCPM2 建议 8GB+ VRAM)

依赖要求:
    pip install httpx

使用方法:
    1. 启动服务端: start.bat (Windows) 或 python bin/clean_launch.py
    2. 运行示例: python examples/api_example.py
"""

import json
import sys
from pathlib import Path

# 尝试导入 httpx HTTP 客户端库，用于发送 API 请求
try:
    import httpx
except ImportError:
    print("请先安装 httpx 依赖: pip install httpx")
    sys.exit(1)

# 服务端基础 URL 配置 - 默认本地地址，端口 7869
# 如需访问远程服务，请修改此地址为实际服务地址
BASE_URL = "http://localhost:7869"


def example_health_check():
    """
    示例 1: 服务健康检查

    功能说明:
        调用 /api/system/health 接口检查服务是否正常运行
        返回服务状态、版本号、运行时间等基本信息

    API 端点:
        GET /api/system/health

    返回字段说明:
        - status: 服务状态 (ok/degraded/error)
        - version: 服务版本号
        - uptime: 服务运行时长(秒)
    """
    print("--- 健康检查 ---")
    # 发送 GET 请求到健康检查端点，设置 5 秒超时
    resp = httpx.get(f"{BASE_URL}/api/system/health", timeout=5)
    print(f"HTTP 状态码: {resp.status_code}")
    # 格式化打印 JSON 响应，ensure_ascii=False 确保中文正常显示
    print(f"响应内容: {json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
    print()


def example_gpu_info():
    """
    示例 2: GPU 信息查询

    功能说明:
        调用 /api/system/gpu 接口获取 GPU 硬件信息和实时使用状态
        包括 GPU 型号、显存占用、GPU 利用率等关键指标

    API 端点:
        GET /api/system/gpu

    返回字段说明:
        - gpu_name: GPU 型号名称 (如 NVIDIA GeForce RTX 4090)
        - vram_total_mb: 总显存大小 (MB)
        - vram_used_mb: 已使用显存 (MB)
        - vram_free_mb: 可用显存 (MB)
        - gpu_utilization: GPU 利用率百分比 (0-100%)
    """
    print("--- GPU 信息 ---")
    resp = httpx.get(f"{BASE_URL}/api/system/gpu", timeout=5)
    print(f"HTTP 状态码: {resp.status_code}")
    data = resp.json()

    # 判断是否返回了 GPU 信息（CPU 模式下可能无此字段）
    if "gpu_name" in data:
        print(f"GPU 型号: {data.get('gpu_name', 'N/A')}")
        print(f"已用显存: {data.get('vram_used_mb', 0):.0f} MB")
        print(f"总显存: {data.get('vram_total_mb', 0):.0f} MB")
        print(f"GPU 利用率: {data.get('gpu_utilization', 0):.0f}%")
    else:
        # CPU 模式或未检测到 GPU 时打印完整响应
        print(f"响应内容: {json.dumps(data, indent=2, ensure_ascii=False)}")
    print()


def example_model_management():
    """
    示例 3: 模型管理（加载与状态查询）

    功能说明:
        演示如何动态加载 TTS 引擎并查询当前模型状态
        支持引擎: voxcpm2 (VoxCPM2 主引擎), indextts2 (IndexTTS2 情感引擎)

    API 端点:
        - POST /api/model/load - 加载指定引擎
        - GET /api/model/status - 查询当前模型状态

    加载参数说明:
        - engine: 引擎名称 ("voxcpm2" 或 "indextts2")

    注意事项:
        - 首次加载模型需要从磁盘读取权重，耗时较长 (10-60秒)
        - 加载前会自动进行显存预检，显存不足时会返回错误
        - 同一时间只能加载一个引擎（切换引擎会自动卸载当前引擎）
    """
    print("--- 模型管理 ---")

    # 步骤 1: 加载 VoxCPM2 引擎
    print("[1] 正在加载 VoxCPM2 引擎...")
    resp = httpx.post(
        f"{BASE_URL}/api/model/load",
        json={"engine": "voxcpm2"},  # 请求体: 指定要加载的引擎
        timeout=120,  # 加载超时时间设为 120 秒，模型加载可能较慢
    )
    print(f"    加载状态码: {resp.status_code}")

    # 步骤 2: 查询模型加载状态
    print("[2] 查询模型状态...")
    resp = httpx.get(f"{BASE_URL}/api/model/status", timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        print(f"    当前引擎: {data.get('current_engine', 'N/A')}")
        # 可扩展: 还可以查看 loaded_models、vram_usage 等字段

    print()


def example_voice_design():
    """
    示例 4: 语音设计（文本描述生成语音）

    功能说明:
        使用 VoxCPM2 引擎的语音设计功能，通过文本描述生成目标音色的语音
        支持在文本中嵌入风格标签，如 "(温柔的女声)"、"(低沉的男声)" 等

    API 端点:
        POST /api/generate/voxcpm2/design

    请求参数说明 (form-data):
        - text: 要合成的文本内容（可包含风格描述标签）
        - cfg_value: Classifier-Free Guidance 强度 (默认 2.0，值越高风格越强)
        - inference_timesteps: 推理步数 (默认 10，步数越多质量越高但速度越慢)
        - seed (可选): 随机种子，用于结果复现

    返回结果:
        成功时直接返回 WAV 音频二进制数据
        失败时返回 JSON 格式的错误信息
    """
    print("--- 语音设计 (VoxCPM2) ---")

    # 发送 POST 请求到语音设计端点
    resp = httpx.post(
        f"{BASE_URL}/api/generate/voxcpm2/design",
        data={
            # 文本中使用括号 () 嵌入风格描述，VoxCPM2 会自动解析
            "text": "(温柔的女声) 你好，欢迎使用 TTS MultiModel 语音合成平台。",
            "cfg_value": "2.0",        # CFG 引导系数，控制风格强度
            "inference_timesteps": "10",  # 扩散推理步数
        },
        timeout=60,  # 生成超时设为 60 秒
    )

    if resp.status_code == 200:
        # 成功: 将返回的音频二进制数据保存为 WAV 文件
        output_path = "output_design.wav"
        Path(output_path).write_bytes(resp.content)
        print(f"[OK] 语音设计完成，已保存到: {output_path}")
    else:
        # 失败: 打印错误信息（截取前 200 字符避免过长）
        print(f"[ERROR] 生成失败 {resp.status_code}: {resp.text[:200]}")
    print()


def example_history():
    """
    示例 5: 生成历史查询

    功能说明:
        查询历史生成记录，支持分页浏览
        历史记录存储在 SQLite 数据库中，包含文本、引擎、时间、文件路径等信息

    API 端点:
        GET /api/history

    请求参数说明 (query params):
        - page: 页码，从 1 开始
        - page_size: 每页记录数，默认 20
        - engine (可选): 按引擎筛选 ("voxcpm2" / "indextts2")

    返回字段说明:
        - total: 总记录数
        - records: 记录列表，每条记录包含:
            - text: 合成的文本
            - engine: 使用的引擎
            - created_at: 生成时间
            - file_path: 音频文件路径
            - duration: 音频时长(秒)
    """
    print("--- 历史记录查询 ---")

    resp = httpx.get(
        f"{BASE_URL}/api/history",
        params={"page": 1, "page_size": 5},  # 查询第 1 页，每页 5 条
        timeout=5,
    )

    if resp.status_code == 200:
        data = resp.json()
        records = data.get("records", [])
        print(f"总记录数: {data.get('total', 0)}")
        # 遍历打印最近 5 条记录（文本截取前 50 字符）
        for i, record in enumerate(records[:5]):
            text_preview = record.get('text', '')[:50]
            engine = record.get('engine', 'N/A')
            print(f"  [{i+1}] {text_preview}... (引擎: {engine})")
    else:
        print(f"[ERROR] 查询失败 {resp.status_code}")
    print()


def main():
    """
    主函数: 按顺序执行所有 API 示例

    执行流程:
        1. 检查服务连接性
        2. 健康检查
        3. GPU 信息查询
        4. 模型加载演示
        5. 语音设计生成
        6. 历史记录查询

    返回值:
        int: 0 表示成功，1 表示失败（服务未启动）
    """
    print("=" * 60)
    print("TTS MultiModel - REST API 使用示例")
    print("=" * 60)
    print()

    # 前置检查: 尝试连接服务端，超时 3 秒
    print("[前置检查] 正在连接服务端...")
    try:
        httpx.get(f"{BASE_URL}/api/system/health", timeout=3)
        print("[OK] 服务端连接成功!")
    except httpx.ConnectError:
        print("[ERROR] 无法连接到服务端!")
        print("       请先启动服务: start.bat (Windows) 或 python bin/clean_launch.py")
        print(f"       当前配置地址: {BASE_URL}")
        return 1
    print()

    # 按顺序执行各个示例函数
    example_health_check()      # 1. 健康检查
    example_gpu_info()          # 2. GPU 信息
    example_model_management()  # 3. 模型管理
    example_voice_design()      # 4. 语音设计
    example_history()           # 5. 历史记录

    print("=" * 60)
    print("所有示例执行完成!")
    print("=" * 60)
    return 0


# 脚本入口点: 当直接运行此文件时执行 main()
if __name__ == "__main__":
    sys.exit(main())
