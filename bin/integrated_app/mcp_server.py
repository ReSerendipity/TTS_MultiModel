# -*- coding: utf-8 -*-
"""MCP (Model Context Protocol) 服务器模块 (Chapter 17)。

提供三大核心能力：
1. TTSMCPServer — MCP 协议服务器，暴露 speak / list_voices / get_model_status 工具
2. AgentVoiceAPI — REST API，供 MCP 感知的 Agent 调用 TTS
3. VoicePersonaSystem (P3) — 本地 LLM 驱动的角色文本改写（桩实现）

设计要点：
- TTSMCPServer 使用 Streamable HTTP 传输，兼容 FastMCP 模式
- AgentVoiceAPI 复用现有 ApiAuthConfig 进行简单 API Key 认证
- VoicePersonaSystem 定义完整接口，LLM 集成以桩实现占位
- 所有日志统一使用 logging.getLogger("tts_multimodel")
- 延迟导入（lazy import）避免启动时加载不必要的依赖
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("tts_multimodel")


# ======================================================================
# 数据类
# ======================================================================


@dataclass
class SpeakRequest:
    """speak 工具请求参数。

    Attributes:
        text: 待合成文本。
        voice: 音色名称（persona name），空字符串表示默认音色。
        engine: 引擎名称（"voxcpm2" / "indextts2"），默认自动选择。
        speed: 语速倍率，默认 1.0。
        cfg: CFG 值，默认 2.0。
        steps: 推理步数，默认 10。
        seed: 随机种子，-1 表示随机。
        emotion: 情感向量（仅 IndexTTS2），JSON 字符串。
    """

    text: str = ""
    voice: str = ""
    engine: str = ""
    speed: float = 1.0
    cfg: float = 2.0
    steps: int = 10
    seed: int = -1
    emotion: str = ""


@dataclass
class SpeakResponse:
    """speak 工具响应数据。

    Attributes:
        audio_url: 生成音频的 HTTP URL（相对路径，如 /api/audio/file/xxx.wav）。
        duration_seconds: 音频时长（秒）。
        sample_rate: 采样率。
        engine: 实际使用的引擎名称。
        generation_id: 生成记录 ID。
    """

    audio_url: str = ""
    duration_seconds: float = 0.0
    sample_rate: int = 24000
    engine: str = ""
    generation_id: str = ""


@dataclass
class VoiceInfo:
    """音色信息。

    Attributes:
        name: 音色名称。
        display_name: 显示名称。
        description: 描述文本。
        audio_url: 参考音频 URL。
    """

    name: str = ""
    display_name: str = ""
    description: str = ""
    audio_url: str = ""


@dataclass
class ModelStatus:
    """模型状态信息。

    Attributes:
        current_engine: 当前活跃引擎名称。
        is_ready: 引擎是否就绪。
        is_loaded: 模型是否已加载。
        vram_usage_percent: 显存使用百分比。
        available_engines: 可用引擎列表。
    """

    current_engine: str = ""
    is_ready: bool = False
    is_loaded: bool = False
    vram_usage_percent: float = 0.0
    available_engines: list[str] = field(default_factory=list)


# ======================================================================
# TTSMCPServer — MCP 协议服务器
# ======================================================================


class TTSMCPServer:
    """MCP (Model Context Protocol) 服务器。

    通过 Streamable HTTP 传输暴露 TTS 工具，供 MCP 客户端（如 Claude、
    ChatGPT 等）调用。工具列表：
    - speak: 文本转语音，返回音频 URL
    - list_voices: 列出可用音色
    - get_model_status: 获取当前引擎状态

    实现模式：
    - 优先使用 FastMCP 库（若已安装）
    - 否则使用简单 HTTP 服务器作为后备

    Usage::

        server = TTSMCPServer(host="127.0.0.1", port=8765)
        server.start()  # 启动 MCP 服务器（后台线程）
        server.stop()   # 停止服务器
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        """初始化 MCP 服务器。

        Args:
            host: 绑定地址，默认 127.0.0.1。
            port: 绑定端口，默认 8765。
        """
        self._host = host
        self._port = port
        self._server = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # MCP 工具实现
    # ------------------------------------------------------------------

    def tool_speak(self, request: SpeakRequest) -> SpeakResponse:
        """speak 工具：文本转语音。

        根据 request.engine 选择引擎，调用生成接口合成语音，
        返回音频 URL 供客户端下载。

        Args:
            request: 合成请求参数。

        Returns:
            SpeakResponse 包含音频 URL 和元信息。

        Raises:
            RuntimeError: 引擎未就绪或生成失败。
        """
        from .model_registry import registry

        # 确定引擎
        engine_name = request.engine or registry.current_engine or "voxcpm2"

        # 检查引擎就绪
        if not registry.is_engine_ready():
            raise RuntimeError("TTS 引擎未就绪，请先加载模型")

        # 验证文本
        if not request.text.strip():
            raise ValueError("文本不能为空")

        # 解析 persona 参考音频
        ref_audio_path = None
        if request.voice:
            ref_audio_path = self._resolve_voice_path(request.voice)

        # 调用生成接口
        try:
            engine = registry.get_current_engine()
            if engine is None:
                raise RuntimeError("无法获取当前引擎实例")

            if engine_name == "indextts2" and request.emotion:
                # IndexTTS2 情感控制模式
                result, msg = engine.generate_voice_clone(
                    text=request.text,
                    reference_audio_path=ref_audio_path,
                    **self._parse_emotion_params(request.emotion),
                )
            elif ref_audio_path:
                # 克隆模式
                result, msg = engine.generate_voice_clone(
                    text=request.text,
                    reference_audio_path=ref_audio_path,
                )
            else:
                # 设计模式
                result, msg = engine.generate_voice_design(
                    text=request.text,
                )

            if result is None:
                raise RuntimeError(f"语音生成失败: {msg}")

            # 构建响应
            audio_path = self._extract_audio_path(result)
            audio_url = self._path_to_url(audio_path)
            duration = self._estimate_duration(request.text)

            return SpeakResponse(
                audio_url=audio_url,
                duration_seconds=duration,
                sample_rate=24000,
                engine=engine_name,
                generation_id=str(uuid.uuid4()),
            )

        except Exception as e:
            logger.error(f"[TTSMCPServer] speak 工具调用失败: {e}")
            raise

    def tool_list_voices(self) -> list[VoiceInfo]:
        """list_voices 工具：列出可用音色。

        Returns:
            VoiceInfo 列表。
        """
        try:
            from .persona_manager import get_persona_list

            persona_names = get_persona_list()
            voices: list[VoiceInfo] = []

            for name in persona_names:
                safe_name = os.path.basename(name)
                voices.append(
                    VoiceInfo(
                        name=safe_name,
                        display_name=safe_name,
                        description="",
                        audio_url=f"/api/audio/persona/audio/{safe_name}",
                    )
                )

            return voices

        except Exception as e:
            logger.error(f"[TTSMCPServer] list_voices 工具调用失败: {e}")
            return []

    def tool_get_model_status(self) -> ModelStatus:
        """get_model_status 工具：获取当前引擎状态。

        Returns:
            ModelStatus 实例。
        """
        try:
            from .engine_interface import engine_registry
            from .model_registry import registry

            current_engine = registry.current_engine or ""
            is_ready = registry.is_engine_ready()
            is_loaded = registry.model_loaded

            # 尝试获取显存信息
            vram_percent = 0.0
            try:
                from .gpu_utils import GPUMemoryMonitor
                monitor = GPUMemoryMonitor()
                vram_info = monitor.get_status()
                vram_percent = vram_info.get("usage_percent", 0.0)
            except Exception:
                pass

            available = engine_registry.list_engines()

            return ModelStatus(
                current_engine=current_engine,
                is_ready=is_ready,
                is_loaded=is_loaded,
                vram_usage_percent=vram_percent,
                available_engines=available,
            )

        except Exception as e:
            logger.error(f"[TTSMCPServer] get_model_status 工具调用失败: {e}")
            return ModelStatus()

    # ------------------------------------------------------------------
    # 服务器启动/停止
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动 MCP 服务器（后台线程）。

        优先尝试 FastMCP 模式，若不可用则使用简单 HTTP 服务器。
        """
        with self._lock:
            if self._running:
                logger.warning("[TTSMCPServer] 服务器已在运行中")
                return

            self._running = True

            # 尝试 FastMCP
            try:
                self._start_fastmcp()
                return
            except ImportError:
                logger.info("[TTSMCPServer] FastMCP 未安装，使用简单 HTTP 服务器")

            # 后备：简单 HTTP 服务器
            self._start_simple_http()

    def stop(self) -> None:
        """停止 MCP 服务器。"""
        with self._lock:
            self._running = False
            if self._server is not None:
                try:
                    if hasattr(self._server, "shutdown"):
                        self._server.shutdown()
                except Exception as e:
                    logger.debug(f"[TTSMCPServer] 停止服务器时出错: {e}")
                self._server = None
            logger.info("[TTSMCPServer] MCP 服务器已停止")

    @property
    def is_running(self) -> bool:
        """服务器是否正在运行。"""
        return self._running

    @property
    def url(self) -> str:
        """服务器 URL。"""
        return f"http://{self._host}:{self._port}"

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _start_fastmcp(self) -> None:
        """使用 FastMCP 库启动 MCP 服务器。

        Raises:
            ImportError: FastMCP 未安装。
        """
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]

        mcp = FastMCP("TTS_MultiModel", host=self._host, port=self._port)

        @mcp.tool()
        def speak(text: str, voice: str = "", engine: str = "",
                  speed: float = 1.0, cfg: float = 2.0,
                  steps: int = 10, seed: int = -1, emotion: str = "") -> str:
            """文本转语音。返回包含音频 URL 的 JSON 字符串。"""
            request = SpeakRequest(
                text=text, voice=voice, engine=engine,
                speed=speed, cfg=cfg, steps=steps, seed=seed, emotion=emotion,
            )
            response = self.tool_speak(request)
            return json.dumps({
                "audio_url": response.audio_url,
                "duration_seconds": response.duration_seconds,
                "sample_rate": response.sample_rate,
                "engine": response.engine,
                "generation_id": response.generation_id,
            }, ensure_ascii=False)

        @mcp.tool()
        def list_voices() -> str:
            """列出可用音色。返回 JSON 数组字符串。"""
            voices = self.tool_list_voices()
            return json.dumps([
                {"name": v.name, "display_name": v.display_name,
                 "audio_url": v.audio_url}
                for v in voices
            ], ensure_ascii=False)

        @mcp.tool()
        def get_model_status() -> str:
            """获取当前模型状态。返回 JSON 字符串。"""
            status = self.tool_get_model_status()
            return json.dumps({
                "current_engine": status.current_engine,
                "is_ready": status.is_ready,
                "is_loaded": status.is_loaded,
                "vram_usage_percent": status.vram_usage_percent,
                "available_engines": status.available_engines,
            }, ensure_ascii=False)

        def _run():
            mcp.run(transport="streamable-http")

        self._thread = threading.Thread(target=_run, daemon=True, name="mcp-server")
        self._thread.start()
        logger.info(f"[TTSMCPServer] FastMCP 服务器已启动: {self.url}")

    def _start_simple_http(self) -> None:
        """使用简单 HTTP 服务器作为后备。"""
        from http.server import HTTPServer, BaseHTTPRequestHandler

        server_ref = self

        class MCPHTTPHandler(BaseHTTPRequestHandler):
            """简单 MCP HTTP 请求处理器。"""

            def do_POST(self):
                """处理 POST 请求（工具调用）。"""
                if self.path == "/mcp/tools/speak":
                    self._handle_speak()
                elif self.path == "/mcp/tools/list_voices":
                    self._handle_list_voices()
                elif self.path == "/mcp/tools/get_model_status":
                    self._handle_get_model_status()
                else:
                    self._send_json({"error": "未知端点"}, status=404)

            def do_GET(self):
                """处理 GET 请求（健康检查）。"""
                if self.path == "/mcp/health":
                    self._send_json({"status": "ok", "service": "TTS_MultiModel MCP"})
                else:
                    self._send_json({"error": "未知端点"}, status=404)

            def _handle_speak(self):
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length)
                    data = json.loads(body) if body else {}

                    request = SpeakRequest(
                        text=data.get("text", ""),
                        voice=data.get("voice", ""),
                        engine=data.get("engine", ""),
                        speed=data.get("speed", 1.0),
                        cfg=data.get("cfg", 2.0),
                        steps=data.get("steps", 10),
                        seed=data.get("seed", -1),
                        emotion=data.get("emotion", ""),
                    )

                    # API Key 认证
                    api_key = data.get("api_key", "")
                    if not server_ref._verify_api_key(api_key):
                        self._send_json({"error": "认证失败：无效的 API Key"}, status=401)
                        return

                    response = server_ref.tool_speak(request)
                    self._send_json({
                        "audio_url": response.audio_url,
                        "duration_seconds": response.duration_seconds,
                        "sample_rate": response.sample_rate,
                        "engine": response.engine,
                        "generation_id": response.generation_id,
                    })
                except Exception as e:
                    self._send_json({"error": str(e)}, status=500)

            def _handle_list_voices(self):
                try:
                    voices = server_ref.tool_list_voices()
                    self._send_json([
                        {"name": v.name, "display_name": v.display_name,
                         "audio_url": v.audio_url}
                        for v in voices
                    ])
                except Exception as e:
                    self._send_json({"error": str(e)}, status=500)

            def _handle_get_model_status(self):
                try:
                    status = server_ref.tool_get_model_status()
                    self._send_json({
                        "current_engine": status.current_engine,
                        "is_ready": status.is_ready,
                        "is_loaded": status.is_loaded,
                        "vram_usage_percent": status.vram_usage_percent,
                        "available_engines": status.available_engines,
                    })
                except Exception as e:
                    self._send_json({"error": str(e)}, status=500)

            def _send_json(self, data, status=200):
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                logger.debug(f"[MCP-HTTP] {format % args}")

        try:
            self._server = HTTPServer((self._host, self._port), MCPHTTPHandler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="mcp-http-server",
            )
            self._thread.start()
            logger.info(f"[TTSMCPServer] HTTP 服务器已启动: {self.url}")
        except Exception as e:
            self._running = False
            logger.error(f"[TTSMCPServer] HTTP 服务器启动失败: {e}")

    @staticmethod
    def _resolve_voice_path(voice_name: str) -> str | None:
        """解析音色名称到参考音频路径。

        Args:
            voice_name: 音色名称。

        Returns:
            参考音频文件路径，不存在则返回 None。
        """
        try:
            from .persona_manager import load_persona_embedding

            safe_name = os.path.basename(voice_name)
            persona_data = load_persona_embedding(safe_name)
            if persona_data is not None:
                wav_path, _ = persona_data
                if wav_path and os.path.isfile(wav_path):
                    return wav_path
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_audio_path(result: Any) -> str:
        """从生成结果中提取音频文件路径。

        Args:
            result: 生成函数返回值（可能是元组或字符串）。

        Returns:
            音频文件路径字符串。
        """
        if isinstance(result, tuple) and len(result) >= 1:
            return str(result[0]) if result[0] else ""
        return str(result) if result else ""

    @staticmethod
    def _path_to_url(audio_path: str) -> str:
        """将本地文件路径转换为 HTTP URL。

        Args:
            audio_path: 本地音频文件路径。

        Returns:
            相对 URL 路径（如 /api/audio/file/xxx.wav）。
        """
        filename = os.path.basename(audio_path)
        return f"/api/audio/file/{filename}"

    @staticmethod
    def _estimate_duration(text: str, chars_per_second: float = 5.0) -> float:
        """根据文本长度估算音频时长。

        Args:
            text: 输入文本。
            chars_per_second: 每秒字符数，默认 5.0（中文典型语速）。

        Returns:
            估算时长（秒）。
        """
        return max(1.0, len(text) / max(chars_per_second, 0.1))

    @staticmethod
    def _parse_emotion_params(emotion_json: str) -> dict[str, Any]:
        """解析 IndexTTS2 情感向量参数。

        Args:
            emotion_json: 情感向量 JSON 字符串。

        Returns:
            适合传递给 generate_voice_clone 的参数字典。
        """
        try:
            emotion = json.loads(emotion_json)
            return {"emotion": emotion}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _verify_api_key(self, api_key: str) -> bool:
        """验证 API Key（复用 ApiAuthConfig）。

        使用恒定时间比较防止定时攻击。

        Args:
            api_key: 客户端提供的 API Key。

        Returns:
            验证是否通过。
        """
        try:
            from .config import get_config

            auth_config = get_config().api_auth
            if not auth_config.enabled:
                return True  # 认证未启用，直接通过

            if not api_key or not auth_config.token:
                return False

            # 恒定时间比较
            return hmac.compare_digest(
                api_key.encode("utf-8"),
                auth_config.token.encode("utf-8"),
            )
        except Exception:
            return False


# ======================================================================
# AgentVoiceAPI — REST API 路由
# ======================================================================


class AgentVoiceAPI:
    """MCP 感知 Agent 的 REST API 路由定义。

    提供 REST 端点供外部 Agent 调用 TTS 服务：
    - POST /api/agent/speak — 文本转语音
    - GET  /api/agent/voices — 列出可用音色
    - GET  /api/agent/status — 获取引擎状态

    认证：复用 ApiAuthConfig，通过 X-API-Key 请求头传递。

    Usage::

        api = AgentVoiceAPI()
        router = api.create_router()
        app.include_router(router)
    """

    def __init__(self) -> None:
        self._mcp_server = TTSMCPServer()
        self._lock = threading.RLock()

    def create_router(self):
        """创建 FastAPI 路由器。

        Returns:
            FastAPI APIRouter 实例。
        """
        from fastapi import APIRouter, Header, HTTPException, Request
        from fastapi.responses import JSONResponse

        router = APIRouter(prefix="/api/agent", tags=["agent-voice"])
        mcp = self._mcp_server

        @router.post("/speak", summary="文本转语音")
        async def agent_speak(request: Request):
            """Agent 语音合成端点。

            请求体（JSON）：
                text: str — 待合成文本（必填）
                voice: str — 音色名称（可选）
                engine: str — 引擎名称（可选，默认自动选择）
                speed: float — 语速倍率（可选，默认 1.0）
                cfg: float — CFG 值（可选，默认 2.0）
                steps: int — 推理步数（可选，默认 10）
                seed: int — 随机种子（可选，默认 -1）
                emotion: str — 情感向量 JSON（可选，仅 IndexTTS2）

            请求头：
                X-API-Key: API 密钥（当认证启用时必填）
            """
            # 认证
            api_key = request.headers.get("X-API-Key", "")
            if not mcp._verify_api_key(api_key):
                raise HTTPException(status_code=401, detail="认证失败：无效的 API Key")

            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="无效的 JSON 请求体")

            text = body.get("text", "").strip()
            if not text:
                raise HTTPException(status_code=400, detail="text 字段不能为空")

            speak_req = SpeakRequest(
                text=text,
                voice=body.get("voice", ""),
                engine=body.get("engine", ""),
                speed=body.get("speed", 1.0),
                cfg=body.get("cfg", 2.0),
                steps=body.get("steps", 10),
                seed=body.get("seed", -1),
                emotion=body.get("emotion", ""),
            )

            try:
                # 在线程池中执行同步生成
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, mcp.tool_speak, speak_req)
                return JSONResponse({
                    "status": "ok",
                    "audio_url": response.audio_url,
                    "duration_seconds": response.duration_seconds,
                    "sample_rate": response.sample_rate,
                    "engine": response.engine,
                    "generation_id": response.generation_id,
                })
            except RuntimeError as e:
                raise HTTPException(status_code=503, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.error(f"[AgentVoiceAPI] speak 端点异常: {e}")
                raise HTTPException(status_code=500, detail="内部服务器错误")

        @router.get("/voices", summary="列出可用音色")
        async def agent_voices(request: Request):
            """列出可用音色端点。

            请求头：
                X-API-Key: API 密钥（当认证启用时必填）
            """
            api_key = request.headers.get("X-API-Key", "")
            if not mcp._verify_api_key(api_key):
                raise HTTPException(status_code=401, detail="认证失败：无效的 API Key")

            voices = mcp.tool_list_voices()
            return JSONResponse({
                "status": "ok",
                "voices": [
                    {
                        "name": v.name,
                        "display_name": v.display_name,
                        "audio_url": v.audio_url,
                    }
                    for v in voices
                ],
                "total": len(voices),
            })

        @router.get("/status", summary="引擎状态")
        async def agent_status(request: Request):
            """获取引擎状态端点。

            请求头：
                X-API-Key: API 密钥（当认证启用时必填）
            """
            api_key = request.headers.get("X-API-Key", "")
            if not mcp._verify_api_key(api_key):
                raise HTTPException(status_code=401, detail="认证失败：无效的 API Key")

            status = mcp.tool_get_model_status()
            return JSONResponse({
                "status": "ok",
                "current_engine": status.current_engine,
                "is_ready": status.is_ready,
                "is_loaded": status.is_loaded,
                "vram_usage_percent": status.vram_usage_percent,
                "available_engines": status.available_engines,
            })

        return router


# ======================================================================
# VoicePersonaSystem (P3) — 角色文本改写系统（桩实现）
# ======================================================================


class VoicePersonaSystem:
    """本地 LLM 驱动的角色文本改写系统（P3 优先级，桩实现）。

    核心思路：
    1. 接收用户输入的原始文本和目标角色设定
    2. 通过本地 LLM 将文本改写为目标角色的口吻/风格
    3. 将改写后的文本送入 TTS 引擎生成语音

    当前为桩实现，定义了完整接口供未来 LLM 集成。
    桩实现行为：原样返回输入文本，附带日志说明。

    Usage::

        persona = VoicePersonaSystem()
        rewritten = await persona.rewrite_text(
            text="你好，今天天气怎么样？",
            character="温柔的大姐姐",
            style="温暖、关怀、略带撒娇",
        )
        # rewritten = "你好呀~今天天气怎么样呢？要不要我陪你出去走走呀？"
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._llm_available = False
        self._llm_model = None
        self._rewrite_history: list[dict[str, str]] = []

        # 尝试检测本地 LLM 可用性
        self._check_llm_availability()

    def _check_llm_availability(self) -> None:
        """检测本地 LLM 是否可用。

        当前仅做日志提示，未来可集成：
        - llama.cpp / ollama
        - vLLM / TGI
        - Transformers 本地推理
        """
        try:
            # 尝试导入 ollama
            import importlib
            importlib.import_module("ollama")
            self._llm_available = True
            logger.info("[VoicePersonaSystem] 检测到 ollama 可用")
        except ImportError:
            pass

        if not self._llm_available:
            logger.info(
                "[VoicePersonaSystem] 本地 LLM 未检测到，角色改写功能"
                "将以桩模式运行（原样返回文本）"
            )

    async def rewrite_text(
        self,
        text: str,
        character: str = "",
        style: str = "",
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        """将输入文本改写为目标角色的口吻/风格。

        Args:
            text: 原始输入文本。
            character: 角色设定描述（如 "温柔的大姐姐"）。
            style: 风格要求（如 "温暖、关怀"）。
            temperature: LLM 采样温度，默认 0.7。
            max_tokens: 最大生成 token 数，默认 512。

        Returns:
            改写后的文本。桩实现直接返回原始文本。
        """
        if not text.strip():
            return text

        if not self._llm_available:
            # 桩实现：原样返回
            logger.debug(
                f"[VoicePersonaSystem] 桩模式：跳过角色改写 "
                f"(character={character!r}, style={style!r})"
            )
            return text

        # 未来 LLM 集成点
        try:
            rewritten = await self._call_llm(text, character, style, temperature, max_tokens)
            # 记录改写历史
            with self._lock:
                self._rewrite_history.append({
                    "original": text,
                    "rewritten": rewritten,
                    "character": character,
                    "style": style,
                    "timestamp": str(time.time()),
                })
            return rewritten
        except Exception as e:
            logger.warning(f"[VoicePersonaSystem] LLM 改写失败，回退到原始文本: {e}")
            return text

    async def _call_llm(
        self,
        text: str,
        character: str,
        style: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """调用本地 LLM 进行文本改写（未来实现）。

        Args:
            text: 原始文本。
            character: 角色设定。
            style: 风格要求。
            temperature: 采样温度。
            max_tokens: 最大 token 数。

        Returns:
            改写后的文本。

        Raises:
            NotImplementedError: 当前未实现。
        """
        # 构建 prompt
        system_prompt = (
            f"你是一个角色扮演助手。请将以下文本改写为符合角色设定的口吻。\n"
            f"角色设定：{character}\n"
            f"风格要求：{style}\n"
            f"要求：保持原意不变，仅调整语气和表达方式。"
        )

        # 尝试使用 ollama
        try:
            import ollama  # type: ignore[import-untyped]

            response = await asyncio.to_thread(
                ollama.chat,
                model="llama3",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                options={"temperature": temperature, "num_predict": max_tokens},
            )
            return response.get("message", {}).get("content", text)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[VoicePersonaSystem] ollama 调用失败: {e}")

        raise NotImplementedError("本地 LLM 调用尚未实现")

    async def generate_with_persona(
        self,
        text: str,
        character: str = "",
        style: str = "",
        voice: str = "",
        engine: str = "",
    ) -> SpeakResponse:
        """角色改写 + 语音合成一体化流程。

        先将文本改写为目标角色口吻，再调用 TTS 生成语音。

        Args:
            text: 原始输入文本。
            character: 角色设定描述。
            style: 风格要求。
            voice: 音色名称。
            engine: 引擎名称。

        Returns:
            SpeakResponse 包含音频 URL 和元信息。
        """
        # 第一步：角色改写
        rewritten_text = await self.rewrite_text(text, character, style)

        # 第二步：调用 TTS
        mcp = TTSMCPServer()
        request = SpeakRequest(
            text=rewritten_text,
            voice=voice,
            engine=engine,
        )
        return mcp.tool_speak(request)

    @property
    def is_llm_available(self) -> bool:
        """本地 LLM 是否可用。"""
        return self._llm_available

    def get_rewrite_history(self, limit: int = 50) -> list[dict[str, str]]:
        """获取改写历史记录。

        Args:
            limit: 最大返回条数，默认 50。

        Returns:
            改写历史列表（按时间倒序）。
        """
        with self._lock:
            return list(reversed(self._rewrite_history[-limit:]))


# ======================================================================
# 模块级单例
# ======================================================================

_mcp_server: TTSMCPServer | None = None
_agent_voice_api: AgentVoiceAPI | None = None
_voice_persona_system: VoicePersonaSystem | None = None
_singleton_lock = threading.Lock()


def get_mcp_server() -> TTSMCPServer:
    """获取全局 TTSMCPServer 单例。"""
    global _mcp_server
    if _mcp_server is None:
        with _singleton_lock:
            if _mcp_server is None:
                _mcp_server = TTSMCPServer()
    return _mcp_server


def get_agent_voice_api() -> AgentVoiceAPI:
    """获取全局 AgentVoiceAPI 单例。"""
    global _agent_voice_api
    if _agent_voice_api is None:
        with _singleton_lock:
            if _agent_voice_api is None:
                _agent_voice_api = AgentVoiceAPI()
    return _agent_voice_api


def get_voice_persona_system() -> VoicePersonaSystem:
    """获取全局 VoicePersonaSystem 单例。"""
    global _voice_persona_system
    if _voice_persona_system is None:
        with _singleton_lock:
            if _voice_persona_system is None:
                _voice_persona_system = VoicePersonaSystem()
    return _voice_persona_system
