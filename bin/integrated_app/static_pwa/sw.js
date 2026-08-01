/* =============================================================================
 * TTS MultiModel Voice Studio - Service Worker (Phase 1)
 *
 * 缓存策略分层：
 *   ┌─────────── HTML GET (navigation) ───────────┐ network-first
 *   │   - 首页 / 模板页面                              │
 *   │   - 离线 fallback: precached '/'                │
 *   ├─────────── /static/* / /favicon.ico ───────────┤ cache-first + 后台 revalidate
 *   │   - JS / CSS / fonts / icons                    │
 *   ├─────────── /api/* GET ────────────────────────┤ stale-while-revalidate
 *   │   - model status / persona list / config       │
 *   ├─────────── /api/* POST/PUT/DELETE ─────────────┤ network only + BG Sync（Phase 4）
 *   ├─────────── /api/sse/events  ──────────────────┤ passthrough (AGENTS.md §6.5)
 *   └─────────────────────────────────────────────────┘
 *
 * 关键约束（对齐 AGENTS.md）：
 *   - SW 文件本身必须 no-cache（路由层 /sw.js 已强制 Cache-Control: no-store）
 *   - 不缓存 /api/sse/events（会断流）
 *   - 不缓存 /api/auth/* 和 /api/system/health（鉴权/健康检查应实时）
 *   - 网络失败且无缓存时返回 offline fallback 页面
 *
 * 升级机制：
 *   - config.yaml 中 pwa.cache_version 改变时（v1 → v2），整体清空旧缓存
 *   - install 事件：self.skipWaiting() 立即激活
 *   - activate 事件：清理无 -${VERSION} 后缀的旧缓存
 *   - 客户端发 SKIP_WAITING 消息强制立即接管（更新提示按钮调用）
 * ============================================================================= */

const VERSION = "v1";  // ⚠️ 与 config.yaml pwa.cache_version 保持同步
const STATIC_CACHE = `tts-static-${VERSION}`;
const HTML_CACHE = `tts-html-${VERSION}`;
const API_CACHE = `tts-api-${VERSION}`;

// 预缓存关键资源（Phase 1 最小 app shell：足够打开应用首屏）
// 注意：URL 必须与路由层真实路径一致，否则 install 阶段会 404 失败。
const PRECACHE_URLS = [
  "/",
  "/favicon.ico",
  "/manifest.json",
];

// =============================================================================
// Install: 预缓存 + 立即激活
// =============================================================================
self.addEventListener("install", (event) => {
  event.waitUntil(
    Promise.all([
      caches.open(STATIC_CACHE).then((cache) =>
        // cache.addAll 任一失败则整个 install 失败；catch 容忍部分缺失
        // （开发环境可能没有全部资源，正式上线收紧为 cache.addAll）
        Promise.all(
          PRECACHE_URLS.map((url) =>
            cache
              .add(new Request(url + "?v=" + VERSION, { cache: "reload" }))
              .catch((err) => {
                console.warn("[SW] pre-cache skipped:", url, err.message);
              })
          )
        )
      ),
      self.skipWaiting(),  // 立即激活（不等旧 SW 终止）
    ])
  );
});

// =============================================================================
// Activate: 清理旧缓存 + 接管未受控页面
// =============================================================================
self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      caches.keys().then((cacheNames) =>
        Promise.all(
          cacheNames
            .filter((name) => !name.endsWith(`-${VERSION}`))
            .map((name) => {
              console.info("[SW] deleting stale cache:", name);
              return caches.delete(name);
            })
        )
      ),
      self.clients.claim(),  // 立即接管页面（不等 reload）
    ])
  );
});

// =============================================================================
// Fetch: 请求路由分发
// =============================================================================
self.addEventListener("fetch", (event) => {
  const { request } = event;
  // 只处理同源请求；跨域（如 CDN 字体）走默认网络
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // ---- 路由 1：SSE 事件流 ----
  // AGENTS.md §6.5：必须 passthrough，绝不缓存或重试
  if (url.pathname.endsWith("/api/sse/events")) {
    return;
  }

  // ---- 路由 2：写操作（POST/PUT/DELETE/PATCH）----
  if (request.method !== "GET") {
    event.respondWith(networkOnlyWithBackgroundSync(event));
    return;
  }

  // ---- 路由 3：静态资源（cache-first）----
  if (
    url.pathname.startsWith("/static/") ||
    url.pathname === "/favicon.ico" ||
    url.pathname === "/manifest.json"
  ) {
    event.respondWith(staleWhileRevalidate(request, STATIC_CACHE));
    return;
  }

  // ---- 路由 4：API 读取（stale-while-revalidate）----
  // 排除健康检查（需要实时状态，避免被陈旧响应误导）
  if (url.pathname.startsWith("/api/")) {
    if (url.pathname.includes("/health") || url.pathname.includes("/auth/")) {
      // 网络直接，不缓存
      return;
    }
    event.respondWith(staleWhileRevalidate(request, API_CACHE));
    return;
  }

  // ---- 路由 5：HTML 导航（network-first）----
  const accept = request.headers.get("accept") || "";
  if (accept.includes("text/html")) {
    event.respondWith(networkFirstHTML(request));
    return;
  }

  // ---- 默认：网络直连 ----
});

// =============================================================================
// 缓存策略实现
// =============================================================================

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const networkFetch = fetch(request)
    .then((response) => {
      if (response && response.ok && response.type === "basic") {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch((err) => {
      console.warn("[SW] network failed, returning cached:", request.url, err.message);
      return cached;
    });
  return cached || networkFetch;
}

async function networkFirstHTML(request) {
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      const cache = await caches.open(HTML_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    console.warn("[SW] HTML network failed, fallback to cache:", request.url, err.message);
    const cached = await caches.match(request);
    if (cached) return cached;
    // 最终 fallback：返回 precached '/'（home page）
    const fallback = await caches.match("/");
    if (fallback) return fallback;
    // 兜底：无任何缓存可用，返回 503
    return new Response(
      `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Offline</title></head>
       <body style="font-family:system-ui;padding:32px;text-align:center;">
       <h1>离线模式</h1>
       <p>当前网络不可用且未缓存本页面。请检查网络后重试。</p>
       </body></html>`,
      { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }
    );
  }
}

async function networkOnlyWithBackgroundSync(event) {
  try {
    return await fetch(event.request);
  } catch (err) {
    // Phase 1：不实现队列，仅日志
    // Phase 4：调用 self.registration.sync.register('tts-generate-queue')
    //        → 后台 sync 触发时通过 IndexedDB 取出队列重放
    console.warn(
      "[SW] write op failed (BG Sync deferred to Phase 4):",
      event.request.url,
      err.message
    );
    return new Response(
      JSON.stringify({
        error: "network_unavailable",
        message:
          "Network unavailable. Background sync queue is scheduled for Phase 4.",
      }),
      {
        status: 503,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      }
    );
  }
}

// =============================================================================
// 客户端消息：SKIP_WAITING 让新 SW 立即接管
// =============================================================================
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    console.info("[SW] received SKIP_WAITING, activating");
    self.skipWaiting();
  }
  if (event.data && event.data.type === "GET_VERSION") {
    if (event.ports && event.ports[0]) {
      event.ports[0].postMessage({ version: VERSION });
    }
  }
});
