/* =============================================================================
 * TTS MultiModel Voice Studio - Service Worker (Phase 2)
 *
 * 缓存策略分层：
 *   ┌─────────── HTML GET (navigation) ───────────┐ network-first
 *   │   - 首页 / 模板页面                              │
 *   │   - 离线 fallback: precached '/'                │
 *   ├─────────── /static/* / /favicon.ico ───────────┤ cache-first + 后台 revalidate
 *   │   - JS / CSS / fonts / icons                    │
 *   ├───── /api/audio/*.wav (本地生成音频) ───────┤ IDB-first + 后台 revalidate
 *   │   - taskId 32-hex 解析                          │
 *   │   - LRU 100MB 自动清理                          │
 *   │   - X-IDB-Cache: HIT/MISS 调试头                │
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
 *
 * Phase 2 启用条件（与 config.yaml pwa.idb_audio_cache 同步）：
 *   - 硬编码 IDB_AUDIO_CACHE_ENABLED = true（修改此处需同步 cache_version 升级）
 *   - 完全运行时配置需要客户端在 SW 激活后 postMessage('CONFIGURE_IDB', { enabled: ... })
 * ============================================================================= */

const VERSION = "v2";  // ⚠️ 与 config.yaml pwa.cache_version 保持同步
const STATIC_CACHE = `tts-static-${VERSION}`;
const HTML_CACHE = `tts-html-${VERSION}`;
const API_CACHE = `tts-api-${VERSION}`;

// Phase 2 硬编码启用开关（与 config.yaml pwa.idb_audio_cache 保持同步）
// 修改此值时务必同时升级 VERSION 触发旧 SW 替换
const IDB_AUDIO_CACHE_ENABLED = true;
const IDB_MAX_SIZE_MB = 100;
const IDB_LRU_TARGET_PCT = 80;
const IDB_BROADCAST_ENABLED = true;
const IDB_PERSIST_REQUESTED = true;

// 预缓存关键资源（Phase 2 扩展：加 idb_cache.js 供 SW importScripts）
// 注意：URL 必须与路由层真实路径一致，否则 install 阶段会 404 失败。
const PRECACHE_URLS = [
  "/",
  "/favicon.ico",
  "/manifest.json",
  "/static_pwa/js/idb_cache.js",  // Phase 2: SW importScripts 依赖
];

// =============================================================================
// ImportScripts: 引入 IDB 缓存模块
// =============================================================================
// 注意：importScripts 必须在 SW 顶层同步执行，不能放在事件回调中
try {
  importScripts("/static_pwa/js/idb_cache.js");
  // 立即配置（容量、广播、持久化参数来自硬编码常量，与 config.yaml 保持同步）
  if (self.__idbCache && typeof self.__idbCache.configure === "function") {
    self.__idbCache.configure({
      maxSizeMB: IDB_MAX_SIZE_MB,
      lruTargetPct: IDB_LRU_TARGET_PCT,
      broadcastEnabled: IDB_BROADCAST_ENABLED,
      persistRequested: IDB_PERSIST_REQUESTED,
    });
    // 异步打开 + 持久化请求（不阻塞 install）
    self.__idbCache.open().then((ok) => {
      if (ok) {
        console.info("[SW] IDB cache initialized, max=" + IDB_MAX_SIZE_MB + "MB");
        if (IDB_PERSIST_REQUESTED) {
          self.__idbCache.requestPersist().catch(() => {});
        }
      }
    });
  } else {
    console.warn("[SW] idb_cache.js not loaded, IDB audio cache disabled");
  }
} catch (err) {
  console.warn("[SW] importScripts('idb_cache.js') failed:", err);
}

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

  // ---- 路由 2.5: 本地生成音频 IDB-first (Phase 2) ----
  if (
    IDB_AUDIO_CACHE_ENABLED &&
    self.__idbCache &&
    self.__idbCache.isAvailable() &&
    url.pathname.startsWith("/api/audio/") &&
    url.pathname.endsWith(".wav")
  ) {
    event.respondWith(idbCacheFirstAudio(request));
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
// Phase 2: IDB-first 音频缓存
// =============================================================================

/**
 * 从 /api/audio/{filename}.wav 提取 taskId（32 hex 校验）。
 * 返回 null 表示 URL 不合法（不是本地生成音频或格式不符），调用方应走原 fetch。
 */
function extractTaskId(audioUrl) {
  try {
    const pathname = new URL(audioUrl).pathname;
    const filename = pathname.split("/").pop() || "";
    const stem = filename.replace(/\.wav$/i, "");
    const taskId = stem.split("_")[0];
    if (self.__idbCache && self.__idbCache.TASK_ID_PATTERN.test(taskId)) {
      return taskId;
    }
    return null;
  } catch (err) {
    return null;
  }
}

/**
 * Phase 2 IDB-first 音频响应：
 *   1. 解析 taskId（32 hex 校验）
 *   2. 查 IDB 命中 → 直接返回 blob
 *   3. 未命中 → 走原 fetch + 异步写入
 */
async function idbCacheFirstAudio(request) {
  const taskId = extractTaskId(request.url);
  if (!taskId) {
    // 非法 URL（不是本地生成音频或格式不符）→ 走原 fetch
    return fetch(request);
  }

  // 1. 查 IDB
  const cached = await self.__idbCache.get(taskId);
  if (cached && cached.blob) {
    return new Response(cached.blob, {
      status: 200,
      headers: {
        "Content-Type": cached.mimeType || "audio/wav",
        "Content-Length": String(cached.size || cached.blob.size || 0),
        "X-IDB-Cache": "HIT",
        "Accept-Ranges": "bytes",  // 兼容 audio_player seek（虽然 Phase 2.0 不支持 206）
        "Cache-Control": "private, max-age=3600",
      },
    });
  }

  // 2. 未命中 → 走原 fetch
  try {
    const response = await fetch(request);
    if (
      response.ok &&
      (response.headers.get("Content-Type") || "").startsWith("audio/")
    ) {
      // 3. 异步写入（不阻塞响应；写失败仅 warn，不影响用户）
      response.clone().blob().then((blob) => {
        self.__idbCache
          .put({
            taskId: taskId,
            blob: blob,
            mimeType: response.headers.get("Content-Type"),
            size: blob.size,
            timestamp: Date.now(),
            lastAccessed: Date.now(),
          })
          .catch((err) => {
            console.warn("[SW] IDB put failed (async):", taskId, err);
          });
      });
    }
    return response;
  } catch (err) {
    console.warn("[SW] idbCacheFirstAudio fetch failed:", request.url, err);
    // 降级：返回 503（前端可重试或 fallback）
    return new Response(
      JSON.stringify({ error: "fetch_failed", message: err.message }),
      {
        status: 503,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      }
    );
  }
}

// =============================================================================
// 客户端消息：SKIP_WAITING / GET_VERSION / IDB 控制
// =============================================================================
self.addEventListener("message", (event) => {
  const data = event.data;
  if (!data || typeof data !== "object") return;

  if (data.type === "SKIP_WAITING") {
    console.info("[SW] received SKIP_WAITING, activating");
    self.skipWaiting();
    return;
  }
  if (data.type === "GET_VERSION") {
    if (event.ports && event.ports[0]) {
      event.ports[0].postMessage({ version: VERSION });
    }
    return;
  }
  // Phase 2: 客户端可请求 IDB 统计（调试用）
  if (data.type === "GET_IDB_STATS") {
    handleGetIdbStats(event);
    return;
  }
});

async function handleGetIdbStats(event) {
  if (!self.__idbCache) {
    if (event.ports && event.ports[0]) {
      event.ports[0].postMessage({ available: false });
    }
    return;
  }
  const [totalSize, estimateResult] = await Promise.all([
    self.__idbCache.getTotalSize(),
    self.__idbCache.estimate(),
  ]);
  const response = {
    available: self.__idbCache.isAvailable(),
    totalSize: totalSize,
    maxSizeMB: IDB_MAX_SIZE_MB,
    usage: estimateResult.usage,
    quota: estimateResult.quota,
    version: VERSION,
  };
  if (event.ports && event.ports[0]) {
    event.ports[0].postMessage(response);
  } else if (event.source && event.source.postMessage) {
    event.source.postMessage({ type: "IDB_STATS", ...response });
  }
}
