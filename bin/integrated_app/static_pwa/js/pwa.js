/* =============================================================================
 * TTS MultiModel Voice Studio - PWA Client (Phase 1-4)
 *
 * 职责（客户端层）：
 *   1. 注册 Service Worker（/sw.js, scope=/）
 *   2. 监听 beforeinstallprompt 事件，捕获并显示自定义安装按钮
 *   3. 监听 iOS Safari（无 beforeinstallprompt），显示手动指引
 *   4. 监听 SW updatefound，提示用户刷新以激活新版本
 *   5. 监听 controllerchange，新 SW 接管后自动 reload
 *   6. Phase 3: 推送通知订阅（请求权限 + PushManager.subscribe + 发送后端）
 *   7. Phase 2.5: IDB 缓存管理（查询用量 + 清空缓存）
 *
 * 不依赖任何框架（Alpine.js / HTMX / jQuery 都可兼容）
 * ============================================================================= */

(function pwaBootstrap() {
  "use strict";

  // ----- 能力检测 -----
  if (!("serviceWorker" in navigator)) {
    console.info("[PWA] Service workers not supported in this browser");
    return;
  }

  // 安全上下文校验：SW 仅在 HTTPS / localhost 注册
  // localhost 在 Chrome 中视为 secure context，因此开发模式可注册
  if (!window.isSecureContext) {
    console.info(
      "[PWA] Insecure context: PWA features disabled (require HTTPS or localhost)"
    );
    // 不 return：localStorage / NetworkInformation 等 API 仍可工作
  }

  let installPromptEvent = null;  // beforeinstallprompt 捕获的 deferred prompt
  let controllerFirstSet = false; // 区分首次注册 vs SW 升级切换

  // =============================================================================
  // 1. 注册 SW
  // =============================================================================
  navigator.serviceWorker
    .register("/sw.js", {
      scope: "/",
      updateViaCache: "none",  // 不通过 HTTP 缓存验证 SW 自身（路由已 no-cache 兜底）
    })
    .then((reg) => {
      console.info("[PWA] Service worker registered, scope:", reg.scope);
      // 已注册过且新 SW 已就绪：可能是新访问，检查更新
      if (reg.active) {
        console.info("[PWA] Active SW already present");
      }
      return reg;
    })
    .then((reg) => reg.update())  // 强制检查 update（后台静默）
    .catch((err) => {
      console.warn("[PWA] Service worker registration failed:", err);
    });

  // 监听 updatefound：新 SW 已 install 但等旧 SW 终止
  navigator.serviceWorker.ready.then((reg) => {
    reg.addEventListener("updatefound", () => {
      const newSw = reg.installing;
      if (!newSw) return;
      newSw.addEventListener("statechange", () => {
        // 关键时序：
        //   installing → installed → activating → activated
        // 注意：只有当旧 SW 被替换时新 SW 才会 activated
        // （首次注册直接跳过等待，进入 activating → activated）
        if (
          newSw.state === "activated" &&
          navigator.serviceWorker.controller
        ) {
          // 区分首次注册 vs 升级：
          // 首次注册时 controller 为 null，升级时 controller 是旧 SW
          if (controllerFirstSet) {
            console.info("[PWA] New SW activated, notifying update");
            showUpdateBanner();
          } else {
            console.info("[PWA] First SW activation, no update prompt");
          }
        }
      });
    });
  });

  // =============================================================================
  // 2. 监听 controllerchange：SW 切换后自动 reload
  // =============================================================================
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (controllerFirstSet) {
      // 这是 SW 升级而非首次注册 → 自动刷新应用新 SW
      console.info("[PWA] controller changed, reloading");
      location.reload();
    }
    controllerFirstSet = true;
  });

  // =============================================================================
  // 3. Android / Desktop Chrome：beforeinstallprompt
  // =============================================================================
  window.addEventListener("beforeinstallprompt", (e) => {
    // 阻止 Chrome 默认 mini-infobar，使用我们的自定义 UI
    e.preventDefault();
    installPromptEvent = e;
    showInstallButton();
    console.info("[PWA] beforeinstallprompt captured, install button shown");
  });

  window.addEventListener("appinstalled", () => {
    installPromptEvent = null;
    hideInstallButton();
    console.info("[PWA] App installed successfully");
  });

  // =============================================================================
  // 4. iOS Safari 检测（无 beforeinstallprompt，需手动 UI）
  // =============================================================================
  const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) &&
    !window.MSStream;
  const isStandalone = window.navigator.standalone === true ||
    window.matchMedia("(display-mode: standalone)").matches;

  if (isIOS && !isStandalone) {
    // 延迟显示 iOS banner（避开首屏加载）
    setTimeout(showIOSBanner, 3000);
  }

  // =============================================================================
  // UI 辅助函数（暴露 window.__pwa_* 命名空间给 inline onclick 调用）
  // =============================================================================

  function showInstallButton() {
    const btn = document.getElementById("pwa-install-btn");
    if (btn) btn.hidden = false;
  }
  function hideInstallButton() {
    const btn = document.getElementById("pwa-install-btn");
    if (btn) btn.hidden = true;
  }
  function showIOSBanner() {
    const banner = document.getElementById("pwa-ios-banner");
    if (banner) banner.hidden = false;
  }
  function showUpdateBanner() {
    const banner = document.getElementById("pwa-update-banner");
    if (banner) banner.hidden = false;
  }

  /**
   * 用户点击安装按钮 → 触发 PWA 安装
   * iOS 上无 installPromptEvent：显示手动指引
   */
  window.__pwa_install__ = function () {
    if (!installPromptEvent) {
      showIOSBanner();
      return;
    }
    installPromptEvent.prompt();
    installPromptEvent.userChoice
      .then((choice) => {
        if (choice.outcome === "accepted") {
          console.info("[PWA] User accepted install prompt");
        } else {
          console.info("[PWA] User dismissed install prompt");
        }
        installPromptEvent = null;
        hideInstallButton();
      })
      .catch((err) => {
        console.warn("[PWA] Install prompt error:", err);
      });
  };

  /**
   * 用户点击"立即刷新"→ SKIP_WAITING 新 SW 接管
   */
  window.__pwa_apply_update__ = function () {
    if (navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "SKIP_WAITING" });
      // controllerchange 监听会自动 reload，无需在这里手动调用
    } else {
      location.reload();
    }
  };

  // 暴露 SW 版本查询（调试用）
  window.__pwa_get_version__ = function () {
    return new Promise((resolve) => {
      if (!navigator.serviceWorker.controller) {
        resolve(null);
        return;
      }
      const channel = new MessageChannel();
      channel.port1.onmessage = (event) => resolve(event.data.version);
      navigator.serviceWorker.controller.postMessage(
        { type: "GET_VERSION" },
        [channel.port2]
      );
    });
  };

  // =============================================================================
  // 6. Phase 3: 推送通知订阅
  // =============================================================================

  /**
   * Base64URL -> Uint8Array（VAPID 公钥转换，PushManager.subscribe 要求）
   */
  function urlBase64ToUint8Array(base64Url) {
    const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
    const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = atob(base64);
    const output = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      output[i] = rawData.charCodeAt(i);
    }
    return output;
  }

  /**
   * 获取 CSRF Token（从 cookie 或 meta 标签）
   */
  function getCsrfToken() {
    // 从 cookie 读取
    const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
    // 从 meta 标签读取
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute("content") || "";
    return "";
  }

  /**
   * 初始化推送通知：检查 VAPID 公钥 + 通知权限 → 自动或手动订阅
   */
  async function initPushNotifications() {
    try {
      const response = await fetch("/api/pwa/push/status");
      if (!response.ok) return;
      const status = await response.json();

      if (!status.enabled || !status.vapid_public_key) {
        // 推送未配置：隐藏推送按钮
        const btn = document.getElementById("pwa-push-btn");
        if (btn) btn.hidden = true;
        return;
      }

      // 检查通知权限
      if (!("Notification" in window)) {
        const btn = document.getElementById("pwa-push-btn");
        if (btn) btn.hidden = true;
        return;
      }

      if (Notification.permission === "granted") {
        // 已授权：自动订阅
        await subscribePush(status.vapid_public_key);
        const btn = document.getElementById("pwa-push-btn");
        if (btn) {
          btn.hidden = true;
        }
      } else if (Notification.permission === "denied") {
        // 已拒绝：隐藏按钮
        const btn = document.getElementById("pwa-push-btn");
        if (btn) btn.hidden = true;
      } else {
        // 默认：显示订阅按钮
        const btn = document.getElementById("pwa-push-btn");
        if (btn) {
          btn.hidden = false;
          btn.dataset.vapidKey = status.vapid_public_key;
        }
      }
    } catch (err) {
      console.warn("[PWA] initPushNotifications failed:", err);
    }
  }

  /**
   * 订阅推送服务
   */
  async function subscribePush(vapidPublicKey) {
    try {
      const reg = await navigator.serviceWorker.ready;
      const subscription = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
      });

      // 发送订阅到后端
      const csrfToken = getCsrfToken();
      const headers = { "Content-Type": "application/json" };
      if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

      await fetch("/api/pwa/push/subscribe", {
        method: "POST",
        headers: headers,
        body: JSON.stringify(subscription),
      });

      console.info("[PWA] Push subscription sent to backend");
    } catch (err) {
      console.warn("[PWA] subscribePush failed:", err);
    }
  }

  /**
   * 用户点击“开启推送通知”按钮
   */
  window.__pwa_subscribe_push__ = async function () {
    const btn = document.getElementById("pwa-push-btn");
    const vapidKey = btn ? btn.dataset.vapidKey : "";
    if (!vapidKey) return;

    const permission = await Notification.requestPermission();
    if (permission === "granted") {
      await subscribePush(vapidKey);
      if (btn) btn.hidden = true;
    }
  };

  // =============================================================================
  // 7. Phase 2.5: IDB 缓存管理 UI
  // =============================================================================

  /**
   * 查询 IDB 缓存统计并更新 UI
   */
  async function updateIdbCacheStats() {
    const el = document.getElementById("pwa-cache-usage");
    if (!el) return;

    if (!navigator.serviceWorker.controller) {
      el.textContent = "—";
      return;
    }

    try {
      const channel = new MessageChannel();
      channel.port1.onmessage = (event) => {
        const stats = event.data;
        if (stats && stats.available) {
          const usedMB = (stats.totalSize / 1024 / 1024).toFixed(1);
          const maxMB = stats.maxSizeMB;
          el.textContent = usedMB + " / " + maxMB + " MB";
          // 更新进度条（如有）
          const bar = document.getElementById("pwa-cache-bar");
          if (bar) {
            const pct = Math.min(100, (stats.totalSize / (maxMB * 1024 * 1024)) * 100);
            bar.style.width = pct + "%";
          }
        } else {
          el.textContent = "不可用";
        }
      };
      navigator.serviceWorker.controller.postMessage(
        { type: "GET_IDB_STATS" },
        [channel.port2]
      );
    } catch (err) {
      console.warn("[PWA] updateIdbCacheStats failed:", err);
      el.textContent = "—";
    }
  }

  /**
   * 清空 IDB 音频缓存（用户点击“清空缓存”按钮）
   */
  window.__pwa_clear_cache__ = async function () {
    // 优先使用 window.__idbCache（idb_cache.js 在窗口上下文加载时可用）
    if (window.__idbCache && typeof window.__idbCache.clear === "function") {
      const ok = await window.__idbCache.clear();
      if (ok) {
        console.info("[PWA] IDB cache cleared via window.__idbCache");
        updateIdbCacheStats();
        return;
      }
    }
    // 降级：通过 SW 消息清空
    if (navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "CLEAR_IDB" });
      console.info("[PWA] IDB cache clear requested via SW");
      setTimeout(updateIdbCacheStats, 500);
    }
  };

  // 监听 BroadcastChannel 更新缓存统计
  if (typeof BroadcastChannel !== "undefined") {
    try {
      const bc = new BroadcastChannel("tts-idb-audio-cache");
      bc.onmessage = (event) => {
        if (event.data && (event.data.type === "PUT" || event.data.type === "EVICTED" || event.data.type === "CLEARED")) {
          updateIdbCacheStats();
        }
      };
    } catch (e) {
      console.warn("[PWA] BroadcastChannel for cache stats failed:", e);
    }
  }

  // SW ready 后初始化推送 + 缓存统计
  navigator.serviceWorker.ready.then(() => {
    initPushNotifications();
    updateIdbCacheStats();
  });
})();
