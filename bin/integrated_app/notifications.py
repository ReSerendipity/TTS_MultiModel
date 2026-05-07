# -*- coding: utf-8 -*-
"""通知提示系统：统一的成功/失败/警告/信息提示与错误解决方案"""

from dataclasses import dataclass
from typing import Optional
import html


@dataclass
class Notification:
    type: str  # success, error, warning, info
    title: str
    message: str
    suggestion: Optional[str] = None

    def to_html(self) -> str:
        if self.type == "error":
            suggestion_html = ""
            if self.suggestion:
                suggestion_html = (
                    f'<div class="error-suggestion">'
                    f'<div class="error-suggestion-title">建议解决方案</div>'
                    f'<div class="error-suggestion-content">{html.escape(self.suggestion)}</div>'
                    f'</div>'
                )
            return (
                f'<div class="tts-error-block">'
                f'<div class="error-title">{self.title}</div>'
                f'<div class="error-message">{html.escape(self.message)}</div>'
                f'{suggestion_html}'
                f'</div>'
            )
        elif self.type == "warning":
            return f'<div class="tts-warning-block">{self.title}: {html.escape(self.message)}</div>'
        elif self.type == "success":
            return f'<div class="tts-success-block">{self.title}: {html.escape(self.message)}</div>'
        else:
            return (
                f'<div class="tts-step-guide">'
                f'<div class="step-title">{self.title}</div>'
                f'<div class="step-content">{html.escape(self.message)}</div>'
                f'</div>'
            )


ERROR_SOLUTIONS = {
    "显存不足": (
        "1. 关闭其他占用 GPU 显存的程序<br>"
        "2. 重启 Python 进程释放残留显存"
    ),
    "模型加载失败": (
        "1. 确认模型文件已下载到 pretrained_models/ 目录<br>"
        "2. 确认 PyTorch 版本与 CUDA 驱动兼容"
    ),
    "模型路径不存在": (
        "1. 确认 pretrained_models/ 目录路径正确"
    ),
    "音频文件不存在": (
        "1. 检查参考音频路径是否正确<br>"
        "2. 确认文件格式为 wav/mp3/m4a/flac"
    ),
    "播放失败": (
        "1. 检查浏览器是否支持该音频格式<br>"
        "2. 尝试下载音频到本地播放"
    ),
    "音色不存在": (
        "1. 刷新音色列表<br>"
        "2. 确认音色已正确保存"
    ),
    "引擎切换失败": (
        "1. 等待当前引擎完全卸载后重试<br>"
        "2. 检查 GPU 显存是否充足<br>"
        "3. 尝试重启应用"
    ),
    "CUDA error": (
        "1. 确认已安装匹配的 CUDA 驱动<br>"
        "2. 检查 GPU 是否被其他进程占用<br>"
        "3. 重启 Python 进程"
    ),
    "OOM": (
        "1. 减少生成长度<br>"
        "2. 关闭其他 GPU 程序释放显存"
    ),
}


def build_error_notification(error_message: str) -> Notification:
    suggestion = None
    for keyword, sol in ERROR_SOLUTIONS.items():
        if keyword in error_message:
            suggestion = sol
            break
    return Notification(
        type="error",
        title="生成失败",
        message=error_message,
        suggestion=suggestion,
    )


def build_success_notification(title: str, message: str = "") -> Notification:
    return Notification(type="success", title=title, message=message)


def build_warning_notification(title: str, message: str = "") -> Notification:
    return Notification(type="warning", title=title, message=message)


def build_info_notification(title: str, message: str = "") -> Notification:
    return Notification(type="info", title=title, message=message)


STEP_GUIDES = {
    "声音设计": (
        "操作步骤",
        "1. 在输入框中填写要合成的文本<br>"
        "2. 选择语言（可选）<br>"
        "3. 在声音描述中填写音色特征（如：极度撒娇的萝莉音）<br>"
        "4. 点击 <kbd>生成语音</kbd> 开始合成<br>"
        "5. 生成完成后可保存为自定义音色"
    ),
    "语音克隆": (
        "操作步骤",
        "1. 填写要合成的文本<br>"
        "2. 选择已保存的音色，或上传新的参考音频<br>"
        "3. 点击 <kbd>开始克隆语音</kbd> 开始合成<br>"
        "4. 参考音频建议时长 10-60 秒，清晰无背景噪音<br>"
        "5. 可展开「高级参数」调节 CFG 值、推理步数等"
    ),
    "极致克隆": (
        "操作步骤",
        "1. 填写要合成的文本<br>"
        "2. 上传参考音频<br>"
        "3. 展开「高级参数」调节 CFG 值、推理步数、降噪、种子等<br>"
        "4. 点击 <kbd>极致克隆生成</kbd> 开始合成"
    ),
    "剧本工坊": (
        "操作步骤",
        "1. 在剧本编辑器中按 <kbd>[角色名] 台词</kbd> 格式输入<br>"
        "2. 点击 <kbd>生成多人对话</kbd> 开始生成<br>"
        "3. 长文本会自动分段合成后合并"
    ),
}
