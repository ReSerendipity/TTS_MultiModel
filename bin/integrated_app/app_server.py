# -*- coding: utf-8 -*-
import os
import time
import logging
import asyncio
import threading

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger("tts_multimodel")


def _preload_voxcpm2_in_background():
    """Background thread to preload VoxCPM2 model on startup."""
    try:
        logger.info("[启动] 后台加载 VoxCPM2 模型中...")
        from .model_manager import load_voxcpm2
        gen = load_voxcpm2()
        for status_text, _, _, _ in gen:
            logger.info(f"[启动] {status_text}")
        logger.info("[启动] VoxCPM2 模型已就绪")
    except Exception as e:
        logger.error(f"[启动] VoxCPM2 模型后台加载失败: {e}")
        logger.info("[启动] 用户可手动点击加载按钮进行加载")


def create_app() -> FastAPI:
    app = FastAPI(title="TTS MultiModel Voice Studio")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost", "http://127.0.0.1:7869", "http://localhost:7869"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = os.path.join(_BASE_DIR, "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    templates_dir = os.path.join(_BASE_DIR, "templates")
    os.makedirs(templates_dir, exist_ok=True)
    templates = Jinja2Templates(directory=templates_dir)
    templates.env.auto_reload = os.environ.get("TTS_DEBUG", "0") == "1"
    from .i18n import register_i18n_filters
    register_i18n_filters(templates.env)
    app.state.templates = templates

    from .routes import pages, tabs, audio, generate, model, persona, sse, system
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

    # Auto-load VoxCPM2 model synchronously on startup
    def startup_event():
        from .model_manager import load_voxcpm2
        logger.info("[启动] 正在加载 VoxCPM2 模型...")
        try:
            gen = load_voxcpm2()
            for status_text, _, _, _ in gen:
                logger.info(f"[启动] {status_text}")
            logger.info("[启动] VoxCPM2 模型已就绪，服务完全启动")
        except Exception as e:
            logger.error(f"[启动] VoxCPM2 模型加载失败: {e}")
            logger.info("[启动] 用户可通过界面手动加载模型")

    app.add_event_handler("startup", startup_event)

    return app


def run_server(ip="127.0.0.1", port=7869):
    from .config import check_models_available, VERSION

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
