"""根路由模块：首页渲染、favicon 重定向、下载引导。

架构说明：
    - 首页 ``/`` 使用 Jinja2 ``TemplateResponse`` 渲染 ``base.html``，
      注入版本号、多语言 JSON、音频播放器配置和 UI 布局配置。
    - ``/favicon.ico`` 执行 301 永久重定向到 ``/static/favicon.ico``，
      利用浏览器长期缓存机制减少重复请求。
    - ``/download-guide/*`` 拦截 HuggingFace / ModelScope 模型文件的
      误下载请求，引导用户使用内置脚本（``start.bat`` 模型下载器）
      而非浏览器直接下载，避免大文件中断导致权重损坏。

路径前缀：
    ``/``（无前缀，直接注册到根）

权限：
    全部为 GET 只读接口，无需 CSRF / Bearer Token 认证。
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from ..config import get_config
from ..i18n import get_i18n_json, get_lang

logger = logging.getLogger("tts_multimodel.pages")

router = APIRouter(tags=["pages"])

_FALLBACK_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TTS MultiModel - 模板加载失败</title>
<style>
body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
       display: flex; align-items: center; justify-content: center;
       min-height: 100vh; margin: 0; background: #f5f3fa; color: #333; }
.card { text-align: center; padding: 48px 32px; max-width: 480px;
        background: #fff; border-radius: 16px; box-shadow: 0 8px 32px rgba(107,92,231,.12); }
h1 { color: #6B5CE7; margin: 0 0 16px; font-size: 22px; }
p  { line-height: 1.7; margin: 8px 0; color: #555; }
code { background: #f0edff; padding: 2px 8px; border-radius: 6px; font-size: 13px; }
</style>
</head>
<body>
<div class="card">
  <h1>模板加载失败</h1>
  <p>应用模板文件缺失或损坏，请重新安装应用。</p>
  <p>Windows 用户请执行：<code>start.bat --repair</code></p>
</div>
</body>
</html>
"""


@router.get("/", summary="首页", description="渲染 TTS MultiModel 主界面（Jinja2 base.html）")
async def index(request: Request) -> Response:
    """渲染首页主框架。

    Args:
        request: FastAPI ``Request`` 对象，用于获取 ``app.state.templates``、
            语言 Cookie 以及生成 ``TemplateResponse``。

    Returns:
        ``TemplateResponse`` — 渲染后的 ``base.html``，HTTP 响应头携带
        ``Cache-Control: no-cache`` 禁用首页缓存；模板渲染失败时降级为
        静态 HTML fallback（状态码 200，避免展示 500 白屏）。
    """
    templates: Jinja2Templates | None = getattr(request.app.state, "templates", None)
    lang = get_lang(request)
    config = get_config()
    ctx: dict[str, Any] = {
        "version": getattr(request.app.state, "version", "0.0.0"),
        "lang": lang,
        "i18n_json": get_i18n_json(lang),
        "audio_player_config": config.pydantic_config.audio_player.model_dump(),
        "ui_config": config.pydantic_config.ui.model_dump(),
    }
    headers = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    if templates is None:
        logger.error("app.state.templates 未初始化，退回静态 fallback")
        return HTMLResponse(content=_FALLBACK_HTML, status_code=200, headers=headers)

    try:
        return templates.TemplateResponse(
            request=request,
            name="base.html",
            context=ctx,
            headers=headers,
        )
    except Exception as exc:  # noqa: BLE001 - TemplateNotFound 等统一兜底
        logger.exception("渲染 base.html 模板失败: %s", exc)
        return HTMLResponse(content=_FALLBACK_HTML, status_code=200, headers=headers)


@router.get("/favicon.ico", summary="网站图标", include_in_schema=False)
async def favicon() -> Response:
    """网站图标：301 永久重定向到静态资源。

    Returns:
        ``RedirectResponse`` (301) → ``/static/favicon.ico``；
        若重定向目标不存在则降级为 ``204 No Content``，不影响页面显示。

    Why 301 而非 302:
        浏览器对 favicon 的 301 响应会缓存 1 个月以上，后续访问不再向
        ``/favicon.ico`` 发请求，显著节省带宽与应用日志量（静态目录由
        ASGI 服务器直接服务，不走 Python 路由层）。
    """
    import os

    from ..config import PROJECT_ROOT

    static_favicon = os.path.join(PROJECT_ROOT, "bin", "integrated_app", "static", "favicon.ico")
    if not os.path.isfile(static_favicon):
        svg_content = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<rect width="100" height="100" rx="20" fill="#6B5CE7"/>'
            '<text x="50" y="68" font-size="50" font-weight="bold" fill="white" '
            'text-anchor="middle" font-family="Arial">TTS</text></svg>'
        )
        return HTMLResponse(content=svg_content, media_type="image/svg+xml")
    return RedirectResponse(url="/static/favicon.ico", status_code=301)


@router.get("/download-guide", include_in_schema=False)
@router.get("/download-guide/{path:path}", include_in_schema=False)
async def download_guide(request: Request, path: str = "") -> Any:
    """模型下载引导页。

    拦截形如 ``/download-guide/models/voxcpm2/...`` 的路径（通常是用户
    误点浏览器链接或脚本重定向导致），渲染 ``download_guide.html``
    提示用户使用 ``start.bat`` 自带的模型下载器，避免浏览器不支持
    断点续传造成大文件（4~12GB）下载中断后权重文件损坏。

    Args:
        request: FastAPI ``Request`` 对象。
        path:    匹配到的剩余路径段（仅用于日志审计，不参与拼接）。

    Returns:
        ``TemplateResponse`` — ``download_guide.html``；模板缺失时
        返回纯 HTML 引导文本。
    """
    if path:
        logger.info("download-guide 拦截路径: %s", path[:120])

    templates: Jinja2Templates | None = getattr(request.app.state, "templates", None)
    lang = get_lang(request)
    headers = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    if templates is not None:
        try:
            return templates.TemplateResponse(
                request=request,
                name="download_guide.html",
                context={
                    "request": request,
                    "lang": lang,
                    "intercepted_path": path,
                },
                headers=headers,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("渲染 download_guide.html 失败: %s", exc)

    fallback = (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>"
        "<title>模型下载引导 - TTS MultiModel</title></head>"
        "<body style='font-family:system-ui,sans-serif;padding:48px;max-width:720px;margin:0 auto;'>"
        "<h2 style='color:#6B5CE7;'>请使用内置脚本下载模型</h2>"
        "<p>模型文件较大（4~12 GB），直接用浏览器下载容易中断损坏。</p>"
        "<p>Windows 用户请双击运行：<code>start.bat</code>，选择菜单中的"
        "<b>「下载模型」</b>选项（支持断点续传 + 自动校验 MD5）。</p>"
        "<p><a href='/'>← 返回首页</a></p></body></html>"
    )
    return HTMLResponse(content=fallback, status_code=200, headers=headers)


@router.get("/@vite/client", include_in_schema=False)
async def vite_client() -> Response:
    """Vite 开发服务器 HMR 客户端占位符端点。

    开发模式下 Vite 会注入 ``/@vite/client`` 脚本实现热更新；生产环境
    不运行 Vite 开发服务器，但模板中可能仍保留对该路径的引用。本端点
    返回 ``204 No Content`` 避免浏览器控制台出现 404 错误，不影响页面
    正常功能。

    Returns:
        ``Response`` (204 No Content) — 空响应体，媒体类型未设置。
    """
    return Response(status_code=204)


# =============================================================================
# PWA (Progressive Web App) 端点 - Phase 1
# =============================================================================
#
# 设计要点（对齐 AGENTS.md §6.5）：
#   - Service Worker 文件必须从根 scope 注册，且响应必须强制 ``no-cache``，
#     否则浏览器会缓存 SW 文件，导致 SW 升级永远无法生效（用户卡在旧版本）。
#   - ``/manifest.json`` 必须返回 ``application/manifest+json`` MIME（Chrome 严格
#     验证），且与 Pydantic ``PwaConfig`` 中的 ``precache_urls`` 保持一致。
#   - ``/api/system/pwa-config`` 返回运行时配置，前端 ``pwa.js`` 启动时拉取；
#     4-Phase 路线（manifest → service worker → IndexedDB → VAPID push →
#     Background Sync）通过该端点的 ``phase`` 字段控制前端功能启用。
#
# 详见：
#   - docs/ROADMAP.md §5.5 stage E
#   - docs/STAGE_E_EXECUTION_PLAN.md TB.6
#   - docs/STAGE_E_PWA_FEASIBILITY.md §6
# =============================================================================


@router.get("/manifest.json", include_in_schema=False)
async def web_app_manifest() -> Response:
    """返回 PWA Web App Manifest。

    文件位于 ``bin/integrated_app/static_pwa/manifest.json``（PWA 专用目录，
    与 ``static/`` 平级但独立可追踪）。此路由优先级
    高于 ``/static_pwa/*`` 的 ``CachedStaticFiles`` mount，并显式声明
    ``Content-Type: application/manifest+json``（Chrome 严格验证），同时
    强制 ``no-cache`` 头以便后续更新 manifest 时（旧 manifest 可能被某些
    浏览器长时间缓存而阻碍升级）。
    """
    manifest_path = Path(__file__).parent.parent / "static_pwa" / "manifest.json"
    if not manifest_path.is_file():
        return Response(status_code=404)
    content = manifest_path.read_text(encoding="utf-8")
    return Response(
        content=content,
        media_type="application/manifest+json; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/sw.js", include_in_schema=False)
async def service_worker() -> Response:
    """返回 Service Worker 主文件。

    **关键约束**：

    1. **必须从根 scope 提供**：浏览器默认只允许 SW 注册在自身所在路径及子
       目录下。``/sw.js`` 在根 path 时，发送 ``Service-Worker-Allowed: /``
       头允许其注册到根 scope，匹配 ``manifest.json`` 的 ``scope: "/"``。

    2. **必须强制 no-cache**：浏览器会缓存 SW 文件本身，旧 SW 不会被新版本
       替换。即使 server 端更新了 ``/sw.js``，浏览器仍会使用旧版本（24h 内），
       导致 SW 升级永远无法生效。此端点强制 ``Cache-Control: no-cache``，
       保证浏览器每次页面访问都会 revalidate（即使中途失联，仍能在下次访问时升级）。

    3. **Content-Type 必须为 JS MIME**（部分浏览器对 MIME 不通过会拒绝注册）：
       ``application/javascript`` 是标准 MIME；同时发 ``X-Content-Type-Options:
       nosniff`` 避免被代理服务器错误嗅探为 HTML。
    """
    sw_path = Path(__file__).parent.parent / "static_pwa" / "sw.js"
    if not sw_path.is_file():
        return Response(status_code=404)
    content = sw_path.read_text(encoding="utf-8")
    return Response(
        content=content,
        media_type="application/javascript; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Service-Worker-Allowed": "/",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/system/pwa-config")
async def pwa_config() -> dict[str, object]:
    """PWA 运行时配置（前端 ``pwa.js`` 和 SW 启动时拉取）。

    返回字段说明：
        - **enabled** (``bool``) — 总开关；``False`` 时前端不注册 SW、不显示安装 banner
        - **offline_enabled** (``bool``) — 是否启用离线功能
        - **cache_version** (``str``) — 与 SW 内部 ``VERSION`` 常量保持一致
        - **scope** (``str``) — SW scope，对应 ``manifest.json`` 的 ``scope``
        - **api_cache_max_age_s** (``int``) — API stale-while-revalidate 最长秒数
        - **precache_urls** (``list[str]``) — install 预缓存清单（调试用）
        - **vapid_public_key** (``str``) — VAPID 公钥，Phase 3 启用推送时填充
        - **phase** (``dict[str, bool]``) — Phase 1-4 启用标记，前端据此启用对应功能

    详见 ``PwaConfig`` 模型（``config_models.py``）。
    """
    from ..config import get_config

    cfg = get_config()
    pwa = cfg.pydantic_config.pwa
    return {
        "enabled": pwa.enabled,
        "offline_enabled": pwa.offline_enabled,
        "cache_version": pwa.cache_version,
        "scope": pwa.scope,
        "api_cache_max_age_s": pwa.api_cache_max_age_s,
        "precache_urls": pwa.precache_urls,
        "vapid_public_key": pwa.vapid_public_key,
        # ===== Phase 2: IndexedDB 音频缓存运行时配置 =====
        # 前端 /api/system/pwa-config 调试 UI 可读；SW 自身硬编码 IDB_* 常量
        "idb": {
            "enabled": pwa.idb_audio_cache,
            "max_size_mb": pwa.idb_max_size_mb,
            "lru_target_pct": pwa.idb_lru_target_pct,
            "broadcast_channel": pwa.idb_broadcast_channel,
            "persist_request": pwa.idb_persist_request,
        },
        "phase": {
            "manifest": True,
            "service_worker": True,
            "idb_audio_cache": pwa.idb_audio_cache,  # Phase 2: 已从 Pydantic 读取
            "vapid_push": bool(pwa.vapid_public_key and pwa.vapid_private_key),  # Phase 3: 公钥+私钥都填写才启用
            "background_sync": pwa.background_sync,  # Phase 4: 离线生成队列
        },
    }
