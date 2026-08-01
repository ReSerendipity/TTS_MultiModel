/* =============================================================================
 * TTS MultiModel Voice Studio - PWA Client (Phase 1)
 *
 * 职责（客户端层）：
 *   1. 注册 Service Worker（/sw.js, scope=/）
 *   2. 监听 beforeinstallprompt 事件，捕获并显示自定义安装按钮
 *   3. 监听 iOS Safari（无 beforeinstallprompt），显示手动指引
 *   4. 监听 SW updatefound，提示用户刷新以激活新版本
 *   5. 监听 controllerchange，新 SW 接管后自动 reload
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
})();
