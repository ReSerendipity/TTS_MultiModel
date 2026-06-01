import logging
import os
import threading
import time
from logging.handlers import RotatingFileHandler

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import APIAuthMiddleware

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_BASE_DIR))
logger = logging.getLogger("tts_multimodel")


# --- Cache-aware StaticFiles ---

_CACHE_MAX_AGE = {
    ".css": 86400 * 7,       # 7 days
    ".js": 86400 * 7,        # 7 days
    ".png": 86400 * 30,      # 30 days
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
    ".map": 86400 * 7,       # source maps
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
            "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    root_logger.addHandler(file_handler)
    if not root_logger.level or root_logger.level == logging.NOTSET:
        root_logger.setLevel(logging.INFO)


def create_app() -> FastAPI:
    app = FastAPI(title="TTS MultiModel Voice Studio")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost", "http://127.0.0.1:7869", "http://localhost:7869"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .config import API_AUTH
    app.add_middleware(
        APIAuthMiddleware,
        enabled=API_AUTH.get("enabled", False),
        token=API_AUTH.get("token", ""),
    )

    static_dir = os.path.join(_BASE_DIR, "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", CachedStaticFiles(directory=static_dir), name="static")

    # 配置日志轮转（如果调用方未配置）
    setup_logging()

    templates_dir = os.path.join(_BASE_DIR, "templates")
    os.makedirs(templates_dir, exist_ok=True)
    templates = Jinja2Templates(directory=templates_dir)
    templates.env.auto_reload = True
    from .i18n import register_i18n_filters
    register_i18n_filters(templates.env)
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

    from .routes import audio, generate, model, pages, persona, sse, system, tabs
    from .routes.training import router as training_router
    app.include_router(pages.router)
    app.include_router(tabs.router)
    app.include_router(audio.router)
    app.include_router(generate.router)
    app.include_router(model.router)
    app.include_router(model.switch_router)
    app.include_router(persona.router)
    app.include_router(sse.router)
    app.include_router(system.router)
    app.include_router(training_router)

    def startup_event():
        """后台加载模型，服务器立即可接受请求。"""
        app.state.models_ok = False
        app.state.model_loading = False
        app.state.model_load_progress = "等待手动加载模型"

        auto_load = os.environ.get("TTS_AUTO_LOAD_MODEL", "0") == "1"

        if not auto_load:
            logger.info("[启动] 自动加载已禁用，请通过界面手动加载模型")
            return

        app.state.model_loading = True
        app.state.model_load_progress = "正在初始化..."

        def _load_in_background():
            try:
                from .model_manager import load_voxcpm2
                logger.info("[启动] 后台加载 VoxCPM2 模型中...")
                gen = load_voxcpm2()
                for status_text, _, _, _ in gen:
                    app.state.model_load_progress = status_text
                    logger.info(f"[启动] {status_text}")
                app.state.models_ok = True
                app.state.model_loading = False
                app.state.model_load_progress = "模型已就绪"
                logger.info("[启动] VoxCPM2 模型已就绪，服务完全启动")
            except Exception as e:
                app.state.models_ok = False
                app.state.model_loading = False
                app.state.model_load_progress = f"加载失败: {e}"
                logger.error(f"[启动] VoxCPM2 模型后台加载失败: {e}")
                logger.info("[启动] 用户可通过界面手动加载模型")

        load_thread = threading.Thread(target=_load_in_background, daemon=True, name="model-startup-load")
        load_thread.start()
        logger.info("[启动] 服务已启动，模型正在后台加载...")

    app.add_event_handler("startup", startup_event)

    return app


def run_server(ip="127.0.0.1", port=7869):
    from .config import VERSION, check_models_available

    app = create_app()
    models_ok, missing = check_models_available()
    app.state.models_ok = models_ok
    app.state.missing_models = missing
    app.state.version = VERSION

    if not models_ok:
        @app.route("/{path:path}", methods=["GET"])
        async def download_guide(request: Request, path: str = ""):
            templates: Jinja2Templates = request.app.state.templates
            return templates.TemplateResponse(
                "download_guide.html",
                {"request": request, "missing": missing, "version": VERSION},
            )

    uvicorn.run(app, host=ip, port=int(port))
