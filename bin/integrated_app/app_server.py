import asyncio
import importlib
import logging
import os
import pkgutil
import threading
import time
from logging.handlers import RotatingFileHandler

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import APIAuthMiddleware
from .exceptions import TTSError, ValidationError
from .middleware.csrf import CSRFMiddleware
from .middleware.error_handler import generic_error_handler, tts_error_handler, validation_error_handler
from .middleware.request_id import RequestIDLogFilter, RequestIDMiddleware

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_BASE_DIR))
logger = logging.getLogger("tts_multimodel")

# Reference to the running event loop, captured at startup so background
# threads can safely schedule state updates back onto the main loop.
_event_loop: asyncio.AbstractEventLoop | None = None


def _set_event_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Store the running event loop for cross-thread state updates."""
    global _event_loop
    _event_loop = loop


# --- Cache-aware StaticFiles ---

_CACHE_MAX_AGE = {
    ".css": 86400 * 7,  # 7 days
    ".js": 86400 * 7,  # 7 days
    ".png": 86400 * 30,  # 30 days
    ".jpg": 86400 * 30,
    ".jpeg": 86400 * 30,
    ".gif": 86400 * 30,
    ".svg": 86400 * 30,
    ".ico": 86400 * 30,
    ".webp": 86400 * 30,
    ".woff": 86400 * 30,
    ".woff2": 86400 * 30,
    ".ttf": 86400 * 30,
    ".eot": 86400 * 30,
    ".map": 86400 * 7,  # source maps
}

_NO_CACHE_EXTENSIONS = {".html", ".json"}


class CachedStaticFiles(StaticFiles):
    """StaticFiles subclass that adds Cache-Control headers based on file type.

    Strategy:
    - Versioned assets (CSS/JS/images/fonts): long-lived cache with immutable
    - HTML/JSON: no-cache to ensure fresh content
    """

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        if hasattr(response, "headers") and response.status_code == 200:
            ext = os.path.splitext(path)[1].lower()
            if ext in _NO_CACHE_EXTENSIONS:
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            elif ext in _CACHE_MAX_AGE:
                max_age = _CACHE_MAX_AGE[ext]
                response.headers["Cache-Control"] = f"public, max-age={max_age}, immutable"
        return response


def setup_logging():
    """配置日志轮转：单个文件 10MB，保留 3 个备份。所有入口点均可调用。"""
    root_logger = logging.getLogger()
    # 避免重复添加 handler
    if any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
        return
    log_dir = os.path.join(_PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(request_id)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    file_handler.addFilter(RequestIDLogFilter())
    root_logger.addHandler(file_handler)
    if not root_logger.level or root_logger.level == logging.NOTSET:
        root_logger.setLevel(logging.INFO)


def _auto_discover_routers(routes_package):
    routers = []
    for _importer, modname, _ispkg in pkgutil.iter_modules(routes_package.__path__):
        mod = importlib.import_module(f".routes.{modname}", package="integrated_app")
        if hasattr(mod, "router"):
            routers.append(mod.router)
    return routers


def create_app() -> FastAPI:
    app = FastAPI(
        title="TTS MultiModel Voice Studio",
        description="多模型语音合成平台，支持 VoxCPM2 和 IndexTTS2 引擎",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 注册全局异常处理器
    app.add_exception_handler(TTSError, tts_error_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    app.add_middleware(
        RequestIDMiddleware,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost", "http://127.0.0.1:7869", "http://localhost:7869"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "HX-Request", "HX-Target", "HX-Trigger"],
    )

    app.add_middleware(
        CSRFMiddleware,
    )

    from .config import get_config

    api_auth = get_config().api_auth_dict
    app.add_middleware(
        APIAuthMiddleware,
        enabled=api_auth.get("enabled", False),
        token=api_auth.get("token", ""),
    )

    static_dir = os.path.join(_BASE_DIR, "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", CachedStaticFiles(directory=static_dir), name="static")

    # 配置日志轮转（如果调用方未配置）
    setup_logging()

    templates_dir = os.path.join(_BASE_DIR, "templates")
    os.makedirs(templates_dir, exist_ok=True)
    templates = Jinja2Templates(directory=templates_dir)
    debug_mode = os.environ.get("TTS_DEBUG", "0") == "1"
    templates.env.auto_reload = debug_mode
    from .i18n import register_i18n_filters

    register_i18n_filters(templates.env)

    # Static asset cache-busting version (app version > env var > startup timestamp)
    app_version = getattr(app.state, "version", None) or os.environ.get("TTS_APP_VERSION")
    if not app_version:
        app_version = str(int(time.time()))
    templates.env.globals["app_version"] = app_version

    app.state.templates = templates

    # Lightweight health ping endpoint (no heavy dependencies)
    @app.get("/api/health/ping")
    async def health_ping():
        """Quick liveness probe -- returns 200 if the server is running."""
        return {
            "status": "ok",
            "timestamp": time.time(),
            "version": getattr(app.state, "version", "unknown"),
        }

    @app.get("/api/health/ready")
    async def health_ready():
        """Readiness probe -- checks if core models are available, with loading progress."""
        models_ok = getattr(app.state, "models_ok", False)
        model_loading = getattr(app.state, "model_loading", False)
        model_load_progress = getattr(app.state, "model_load_progress", "")

        if models_ok:
            status = "ok"
        elif model_loading:
            status = "loading"
        else:
            status = "degraded"

        return {
            "status": status,
            "models_available": models_ok,
            "loading": model_loading,
            "progress": model_load_progress,
            "missing_models": getattr(app.state, "missing_models", []),
        }

    from . import routes

    for r in _auto_discover_routers(routes):
        app.include_router(r)

    async def startup_event():
        """后台加载模型，服务器立即可接受请求。"""
        # Capture the event loop so background threads can dispatch state updates.
        _set_event_loop(asyncio.get_running_loop())

        # Initialize model loading state via the event loop for thread safety.
        app.state.models_ok = False
        app.state.model_loading = False
        app.state.model_load_progress = "等待手动加载模型"

        # Sync existing audio files into the history database once at startup.
        try:
            from .history_db import get_history_db

            history_manager = get_history_db()
            await run_in_threadpool(history_manager.sync_from_filesystem)
            logger.info("[启动] 历史记录全量同步完成")
        except Exception as e:
            logger.error(f"[启动] 历史记录全量同步失败: {e}")

        auto_load = os.environ.get("TTS_AUTO_LOAD_MODEL", "0") == "1"

        if not auto_load:
            logger.info("[启动] 自动加载已禁用，请通过界面手动加载模型")
            return

        auto_engine = os.environ.get("TTS_AUTO_LOAD_ENGINE", "voxcpm2")

        app.state.model_loading = True
        app.state.model_load_progress = "正在初始化..."

        def _load_in_background():
            from .middleware.request_id import set_request_id

            set_request_id(f"bg-{threading.current_thread().name}")

            async def _update_state(**kwargs):
                for k, v in kwargs.items():
                    setattr(app.state, k, v)

            def _schedule_state_update(**kwargs):
                loop = _event_loop
                if loop is not None and not loop.is_closed():
                    asyncio.run_coroutine_threadsafe(_update_state(**kwargs), loop)
                else:
                    # Fallback only when loop is unavailable (should not happen
                    # after startup); not safe across threads but preserves behavior.
                    for k, v in kwargs.items():
                        setattr(app.state, k, v)

            try:
                if auto_engine == "indextts2":
                    from .model_manager import load_indextts2

                    logger.info("[启动] 后台加载 IndexTTS 2.0 模型中...")
                    gen = load_indextts2()
                else:
                    from .model_manager import load_voxcpm2

                    logger.info("[启动] 后台加载 VoxCPM2 模型中...")
                    gen = load_voxcpm2()
                last_status = ""
                for status_text, _, _, _ in gen:
                    last_status = status_text
                    _schedule_state_update(model_load_progress=status_text)
                    logger.info(f"[启动] {status_text}")
                # Only mark as ready if the last status does NOT indicate failure
                if "失败" in last_status or "error" in last_status.lower():
                    _schedule_state_update(
                        models_ok=False,
                        model_loading=False,
                        model_load_progress=last_status,
                    )
                    logger.error(f"[启动] {auto_engine} 加载失败: {last_status}")
                else:
                    _schedule_state_update(
                        models_ok=True,
                        model_loading=False,
                        model_load_progress="模型已就绪",
                    )
                    logger.info(f"[启动] {auto_engine} 模型已就绪，服务完全启动")
            except Exception as e:
                _schedule_state_update(
                    models_ok=False,
                    model_loading=False,
                    model_load_progress=f"加载失败: {e}",
                )
                logger.error(f"[启动] {auto_engine} 模型后台加载失败: {e}")
                logger.info("[启动] 用户可通过界面手动加载模型")

        load_thread = threading.Thread(target=_load_in_background, daemon=True, name="model-startup-load")
        load_thread.start()
        logger.info("[启动] 服务已启动，模型正在后台加载...")

    # Compatible with both old and new FastAPI versions
    try:
        app.add_event_handler("startup", startup_event)  # type: ignore[attr-defined]
    except AttributeError:

        @app.on_event("startup")
        async def _startup():
            await startup_event()

    return app


def run_server(ip="127.0.0.1", port=7869):
    from .config import check_models_available, get_config

    app = create_app()
    models_ok, missing = check_models_available()
    app.state.models_ok = models_ok
    app.state.missing_models = missing
    version = get_config().version
    app.state.version = version

    if not models_ok:

        @app.route("/{path:path}", methods=["GET"])
        async def download_guide(request: Request, path: str = ""):
            templates: Jinja2Templates = request.app.state.templates
            return templates.TemplateResponse(
                request=request,
                name="download_guide.html",
                context={"missing": missing, "version": version},
            )

    uvicorn.run(app, host=ip, port=int(port))
