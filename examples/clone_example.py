# -*- coding: utf-8 -*-
"""
TTS MultiModel - 零样本语音克隆示例
====================================

项目名称: TTS MultiModel (多引擎语音合成平台)
主要功能: 演示如何使用 VoxCPM2 引擎实现零样本语音克隆（仅需一段参考音频即可克隆音色）
核心技术栈: Python + httpx + VoxCPM2 扩散模型 + 声纹提取
适用场景:
    - 个性化语音助手定制
    - 有声读物角色配音
    - 视频/播客内容配音
    - 数字人语音驱动
    - 多语言音色迁移
关键注意事项:
    - 运行前需先启动服务端 (start.bat 或 python bin/clean_launch.py)
    - 默认服务地址: http://127.0.0.1:7869
    - 参考音频要求:
        * 格式: WAV (推荐)、MP3 等常见格式
        * 时长: 建议 5-30 秒，过短会导致克隆效果不稳定
        * 质量: 清晰无背景噪音、无混响、单人说话
        * 采样率: 建议 16kHz 及以上（系统会自动重采样）
    - VoxCPM2 引擎需要约 8GB+ 显存才能正常运行
    - 克隆效果取决于参考音频质量，建议使用专业录音设备采集
    - normalize 和 denoise 参数建议开启，可提升生成稳定性

依赖要求:
    pip install httpx
    # 如需处理音频可选安装: pip install soundfile numpy

使用方法:
    1. 准备一段 5-30 秒的参考音频 (.wav 格式)
    2. 启动服务端: start.bat (Windows) 或 python bin/clean_launch.py
    3. 修改下方 reference_audio 变量指向你的音频文件
    4. 运行示例: python examples/clone_example.py
"""

import sys
from pathlib import Path

# 尝试导入 httpx HTTP 客户端库
try:
    import httpx
except ImportError:
    print("请先安装 httpx 依赖: pip install httpx")
    sys.exit(1)

# 服务端基础 URL 配置
BASE_URL = "http://localhost:7869"


def check_server() -> bool:
    """
    检查 TTS 服务端是否正常运行

    功能说明:
        调用健康检查接口，验证服务端是否可访问且状态正常
        在执行克隆操作前必须先通过此检查，避免后续请求失败

    Returns:
        bool: True 表示服务正常运行，False 表示连接失败或状态异常

    API 端点:
        GET /api/system/health
    """
    try:
        resp = httpx.get(f"{BASE_URL}/api/system/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get('status', 'unknown')
            print(f"[OK] 服务端运行中 - 状态: {status}")
            return True
    except httpx.ConnectError:
        # 连接被拒绝，服务未启动
        pass
    print("[ERROR] 服务端未运行!")
    print("       请先启动服务: start.bat (Windows) 或 python bin/clean_launch.py")
    return False


def load_model(engine: str = "voxcpm2") -> bool:
    """
    加载指定的 TTS 引擎模型

    功能说明:
        调用模型加载接口，将指定引擎加载到 GPU 显存中
        模型加载是耗时操作，首次加载需要 10-60 秒（取决于硬件和模型大小）

    Args:
        engine: 引擎名称，目前支持:
            - "voxcpm2": VoxCPM2 主引擎（支持语音克隆、设计、剧本工坊等）
            - "indextts2": IndexTTS2 情感引擎（支持 8 维情感控制）

    Returns:
        bool: True 表示加载成功，False 表示加载失败

    API 端点:
        POST /api/model/load

    注意事项:
        - 加载前系统会自动进行显存预检，显存不足时会返回错误
        - 同一时间只能加载一个引擎，切换引擎会自动卸载当前引擎
        - 加载失败时请检查 GPU 显存是否足够，或查看服务端控制台日志
    """
    print(f"[INFO] 正在加载 {engine} 引擎...")
    try:
        resp = httpx.post(
            f"{BASE_URL}/api/model/load",
            json={"engine": engine},
            timeout=120,  # 加载超时设为 120 秒
        )
        if resp.status_code == 200:
            print(f"[OK] {engine} 引擎加载成功!")
            return True
        else:
            print(f"[ERROR] 加载失败: HTTP {resp.status_code}")
            print(f"       错误信息: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"[ERROR] 加载过程发生异常: {e}")
        return False


def clone_voice(
    text: str,
    reference_audio_path: str,
    output_path: str = "output_clone.wav",
) -> bool:
    """
    使用 VoxCPM2 进行零样本语音克隆

    功能说明:
        上传一段参考音频，VoxCPM2 会提取其中的说话人特征（声纹），
        然后用该音色合成指定文本的语音。仅需一段音频即可实现音色克隆。

    Args:
        text: 要合成的目标文本，建议长度 10-200 字
        reference_audio_path: 参考音频文件路径（.wav 格式）
        output_path: 生成音频的保存路径，默认 "output_clone.wav"

    Returns:
        bool: True 表示生成成功，False 表示生成失败

    API 端点:
        POST /api/generate/voxcpm2/clone

    请求参数说明 (multipart/form-data):
        - text: 要合成的文本内容
        - reference_audio: 参考音频文件（文件上传）
        - cfg_value: CFG 引导系数 (默认 2.0，值越高与参考音色相似度越高)
        - inference_timesteps: 扩散推理步数 (默认 10，步数越多质量越好)
        - normalize: 是否对参考音频进行响度归一化 ("true"/"false"，建议 true)
        - denoise: 是否对参考音频进行降噪处理 ("true"/"false"，建议 true)
        - seed (可选): 随机种子，用于结果复现

    参考音频最佳实践:
        - 环境安静，无背景噪音、音乐或回声
        - 说话人情绪平稳，语速正常
        - 避免过多的停顿、呼吸声或语气词
        - 音频中只有一个人说话
    """
    # 检查参考音频文件是否存在
    ref_path = Path(reference_audio_path)
    if not ref_path.exists():
        print(f"[ERROR] 参考音频文件不存在: {reference_audio_path}")
        print(f"       请准备一段 WAV 格式的参考音频，或修改 reference_audio 路径")
        return False

    print(f"[INFO] 开始语音克隆...")
    print(f"  目标文本: {text}")
    print(f"  参考音频: {reference_audio_path}")
    print(f"  输出路径: {output_path}")

    try:
        # 以二进制模式打开参考音频文件，通过 multipart/form-data 上传
        with open(ref_path, "rb") as f:
            resp = httpx.post(
                f"{BASE_URL}/api/generate/voxcpm2/clone",
                data={
                    "text": text,
                    "cfg_value": "2.0",              # CFG 强度: 控制与参考音色的相似度
                    "inference_timesteps": "10",     # 推理步数: 影响生成质量和速度
                    "normalize": "true",              # 响度归一化: 统一音频音量
                    "denoise": "true",                # 降噪: 去除参考音频背景噪音
                },
                # 文件上传: 指定文件名、文件对象、MIME 类型
                files={"reference_audio": (ref_path.name, f, "audio/wav")},
                timeout=120,  # 生成超时 120 秒
            )

        if resp.status_code == 200:
            # 生成成功: 保存音频文件
            out = Path(output_path)
            out.write_bytes(resp.content)
            size_kb = len(resp.content) / 1024
            print(f"[OK] 语音克隆成功!")
            print(f"     已保存到: {output_path}")
            print(f"     文件大小: {size_kb:.1f} KB")
            return True
        else:
            # API 返回错误
            print(f"[ERROR] 生成失败: HTTP {resp.status_code}")
            print(f"       错误信息: {resp.text[:300]}")
            return False

    except Exception as e:
        # 网络错误、文件读取错误等异常
        print(f"[ERROR] 生成过程发生异常: {e}")
        return False


def main():
    """
    主函数: 执行语音克隆完整流程

    执行流程:
        1. 打印欢迎信息
        2. 检查服务端连接状态
        3. 加载 VoxCPM2 模型
        4. 检查参考音频文件是否存在
        5. 执行语音克隆
        6. 输出结果提示

    返回值:
        int: 0 表示成功，1 表示失败（任意步骤出错）
    """
    print("=" * 60)
    print("TTS MultiModel - 零样本语音克隆示例")
    print("=" * 60)
    print()

    # 步骤 1: 检查服务端
    print("[步骤 1/4] 检查服务端状态...")
    if not check_server():
        return 1
    print()

    # 步骤 2: 加载模型
    print("[步骤 2/4] 加载语音合成模型...")
    if not load_model("voxcpm2"):
        return 1
    print()

    # 步骤 3: 准备参考音频
    print("[步骤 3/4] 检查参考音频...")
    # ============================================================
    # 注意: 请将此路径修改为你自己的参考音频文件路径!
    # 推荐使用 5-30 秒的清晰 WAV 音频作为参考
    # ============================================================
    reference_audio = "examples/reference_speaker.wav"

    if not Path(reference_audio).exists():
        print(f"[WARN] 参考音频不存在: {reference_audio}")
        print()
        print("请按以下步骤操作:")
        print("  1. 准备一段 5-30 秒的 WAV 格式参考音频")
        print("  2. 将音频放到 examples/ 目录下，命名为 reference_speaker.wav")
        print("  3. 或者修改 clone_example.py 中的 reference_audio 变量")
        print("     指向你的音频文件绝对路径")
        print()
        print("参考音频要求:")
        print("  - 格式: WAV")
        print("  - 时长: 5-30 秒")
        print("  - 质量: 清晰无噪音、单人说话")
        return 1
    print(f"[OK] 找到参考音频: {reference_audio}")
    print()

    # 步骤 4: 执行语音克隆
    print("[步骤 4/4] 开始语音克隆...")
    print()
    success = clone_voice(
        text="你好，这是一段使用 TTS MultiModel 克隆的语音。希望你喜欢这个效果！",
        reference_audio_path=reference_audio,
        output_path="output_clone.wav",
    )

    print()
    if success:
        print("=" * 60)
        print("[完成] 语音克隆流程执行成功!")
        print(f"       请播放 output_clone.wav 收听克隆效果。")
        print()
        print("提示:")
        print("  - 如果效果不理想，可以尝试更换参考音频")
        print("  - 调整 cfg_value 参数可以控制相似度（2.0-4.0 之间）")
        print("  - 增加 inference_timesteps 可以提升质量但会变慢")
        print("=" * 60)
    return 0 if success else 1


# 脚本入口点
if __name__ == "__main__":
    sys.exit(main())
