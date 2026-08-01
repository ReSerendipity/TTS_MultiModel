# 阶段 E.5 PWA 离线优先 — 可行性调研报告

> 创建日期：2026-08-01
> 调研者：AI 代理
> 决策状态：**建议降级到阶段 F**，本阶段 E 不实施

---

## 1. 背景与问题陈述

### 1.1 用户原始诉求

用户在阶段 E 推进中标注："PWA 离线优先（这个先了解一下）"。本报告回应"了解一下"的诉求，给出可量化评估与决策建议。

### 1.2 PWA 价值主张

Progressive Web App（PWA）通过 manifest.json + service worker 赋予 WebApp 接近原生应用的体验：

- **可安装**：用户从浏览器 "Add to Home Screen" 安装到桌面/主屏，启动时无浏览器 UI
- **离线访问**：service worker 缓存 app shell + 静态资源，断网仍可访问 UI
- **后台同步**：后台 API 调用（如生成任务）支持离线排队，在线时自动同步
- **推送通知**：服务端主动推送（如生成完成通知），无需打开 app
- **本地存储**：IndexedDB 缓存已生成音频，断网仍可播放历史音频

### 1.3 项目场景适配性

TTS_MultiModel 的典型使用场景：
1. 用户输入文本 → 点击"生成" → 等待 5-60 秒 → 播放/下载音频
2. 用户在生成过程中可能切换到其他 tab（生成耗时较长）
3. 用户可能希望随时回听历史生成结果
4. 用户可能希望离线访问最近一批生成结果

PWA 在 TTS 场景下的实际价值（按优先级）：

| 场景 | PWA 价值 | 优先级 |
|------|---------|--------|
| 已生成音频离线回听 | 高（IndexedDB 缓存） | ⭐⭐⭐ |
| "Add to Home Screen" 安装 | 中（提升可发现性） | ⭐⭐ |
| 生成完成推送通知 | 中（避免频繁 tab 切换） | ⭐⭐ |
| app shell 离线访问 | 低（用户几乎不"离线打开"一个 TTS 应用） | ⭐ |
| 离线生成 | **不可行**（模型 10GB+ 无法本地化） | ❌ |

---

## 2. 当前 PWA 基础设施审计

### 2.1 现有能力

| 资产 | 状态 | 来源 |
|------|------|------|
| `manifest.json` | **不存在**（项目内 0 命中） | `search_file manifest.json` |
| `service-worker.js` | **不存在**（项目内 0 命中） | `search_file service-worker` |
| `package.json` | **不存在**（仅 `reference_repos/` 和 WPy64-312101 第三方包） | `search_file package.json` |
| `tsconfig.json` | **不存在**（项目内 0 命中） | `search_file tsconfig.json` |
| 前端构建工具 | **无** | 当前是 FastAPI 静态文件直发 + Jinja2 模板 |
| 前端框架 | HTMX + Alpine.js + 原生 JS（28 个 .js） | `bin/integrated_app/static/js/` |
| 静态资源总量 | 9 个 CSS + 28 个 JS + fonts | `bin/integrated_app/static/` |

### 2.2 关键技术约束

1. **TTS 模型 10GB+**：无法在浏览器/service worker 缓存，**离线生成不可行**
2. **后端 FastAPI 强依赖**：即便前端 PWA 化，生成仍需联网
3. **HTTPS 推送要求**：PWA 推送通知要求 HTTPS + VAPID 密钥
4. **iOS Safari 限制**：不支持完整 PWA（service worker 2024 年才支持）
5. **CI 调试困难**：service worker 测试需 Playwright + 浏览器上下文隔离

### 2.3 现有 SSE 推送能力

项目已有 `/api/sse/events` 端点（[routes/sse.py](bin/integrated_app/routes/sse.py)），支持 progress / complete / status / engine_switch / cancelled / time_estimate 事件类型。**部分 PWA 推送功能已被 SSE 替代**——SSE 推送不需要 service worker，且服务器端代码已存在。

---

## 3. 技术方案选型

### 方案 A：纯手写 manifest + service worker（轻量）

**技术栈**：无新增依赖，手写 2 个文件

```json
// bin/integrated_app/static_pwa/manifest.json
{
  "name": "TTS MultiModel",
  "short_name": "TTS",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0f1115",
  "theme_color": "#5b8def",
  "icons": [...]
}
```

```js
// bin/integrated_app/static_pwa/sw.js
self.addEventListener('install', e => {
  e.waitUntil(caches.open('v1').then(c => c.addAll(['/static/...'])))
})
self.addEventListener('fetch', e => {
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)))
})
```

**优点**：
- 零依赖、零构建、零 npm install
- 与现有 FastAPI 静态文件直接对接
- 文件小（manifest < 1KB，SW < 100 行）
- 学习曲线低

**缺点**：
- 缓存策略需手写（Workbox 功能需自实现）
- IndexedDB 音频缓存需自实现
- 无 Workbox 那种"过期/容量"管理

**工期**：manifest 半天 + SW 基础 1 天 + 离线测试 1 天 = **2.5 天**

---

### 方案 B：引入 vite-plugin-pwa（重量级）

**技术栈**：Node.js + Vite + vite-plugin-pwa + Workbox

**实施步骤**：
1. 引入 npm：`package.json` + 28 个 JS 重构为 ES modules
2. Vite 配置多入口打包
3. vite-plugin-pwa 注入 manifest + Workbox SW
4. 构建产物替换 FastAPI 静态文件

**优点**：
- Workbox 完整缓存策略（StaleWhileRevalidate / CacheFirst / NetworkFirst）
- HMR 开发体验
- 自动生成 SW 清单

**缺点**：
- **破坏性极大**：28 个原生 JS + 31 个 HTML + Jinja2 模板必须重构为 Vite 工程
- 与 FastAPI Jinja2 模板冲突（Vite 也是模板，需要适配）
- CI 需要 npm install（+5-10 分钟）
- 学习成本高（团队需要懂 Vite）
- 开发体验破坏：现在改 HTML 刷新即可，未来要 `npm run dev`

**工期**：1 周（环境搭建）+ 2 周（28 JS 迁移） = **3 周**（保守）

---

### 方案 C：渐进式增强（推荐——但本报告建议先不做）

**实施步骤**：
1. **阶段 1（1 周）**：仅添加 manifest.json + 手写 SW（缓存静态资源）
2. **阶段 2（2 周）**：IndexedDB 缓存已生成音频（前端 ~200 行代码）
3. **阶段 3（2 周）**：推送通知（需 HTTPS + VAPID 密钥）
4. **阶段 4（0.5 周）**：后台同步（生成任务离线排队）

**优点**：
- 渐进式，每阶段可独立交付
- 不破坏现有架构
- 可在阶段 1 看到初步收益

**缺点**：
- **总工期 5.5 周**——投入产出比不理想
- 见第 4 节 ROI 分析

---

## 4. ROI 分析

### 4.1 工作量 vs 价值矩阵

| 方案 | 工期 | 价值 | 性价比 |
|------|------|------|--------|
| A 手写 | 2.5 天 | 中（仅 manifest + 基础离线） | ⭐⭐⭐ |
| B Vite | 3 周 | 高（完整 PWA 套件） | ⭐（破坏性太大） |
| C 渐进 | 5.5 周 | 高（完整 PWA + 推送） | ⭐ |

### 4.2 用户实际收益

**场景 A：用户想"安装到桌面"**
- 方案 A 即可：manifest + "Add to Home Screen"
- 投入 2.5 天，收益永久

**场景 B：用户想"断网回听历史音频"**
- 需 IndexedDB 缓存：方案 C 阶段 2
- 投入 2 周，但用户量小（TTS 重度用户才需要）

**场景 C：用户想"生成完成推送"**
- 需推送通知：方案 C 阶段 3
- 投入 2 周，但**已有 SSE 替代**——前端可监听 `/api/sse/events` 播放音效即可

**场景 D：用户想"离线生成"**
- **不可行**——模型 10GB+ 无任何方案能本地化

### 4.3 与阶段 E 其他子项对比

| 阶段 E 子项 | 工期 | 价值 | 性价比 |
|------------|------|------|--------|
| E.1 Streaming 实时 TTS | 1 周 | **高**（核心体验） | ⭐⭐⭐⭐⭐ |
| E.2 LLM-driven 提示词编排 | 2 周 | **高**（差异化功能） | ⭐⭐⭐⭐ |
| E.3 TypeScript 类型化 | 3 周 | 中（工程化渐进收益） | ⭐⭐⭐ |
| E.4 插件化架构 | 2 周 | 中（生态扩展） | ⭐⭐⭐ |
| E.5 PWA 离线优先 | 5.5 周 | 低（功能重复 SSE） | ⭐ |

**结论**：PWA 在阶段 E 5 子项中 ROI 最低，且与现有 SSE 能力重叠。

---

## 5. 风险评估

### 5.1 技术风险

| 风险 | 等级 | 说明 |
|------|------|------|
| service worker 缓存策略错误导致新功能失效 | 高 | 必须设计 cache busting（如 `?v=<hash>`） |
| IndexedDB 容量管理（用户可能生成几十 MB 音频） | 中 | 需 LRU + 容量限制（建议 200MB） |
| 推送通知需要 HTTPS + VAPID | 中 | 本地开发可用 `localhost`，生产需配证书 |
| iOS Safari PWA 兼容性 | 高 | 2024 年才支持 SW，IndexedDB 同步有问题 |
| CI 自动化测试困难 | 高 | service worker 需 Playwright，CI 时间 +5-10 分钟 |
| 与现有 SSE 路径冲突 | 低 | 推送和 SSE 是补充关系，不冲突 |

### 5.2 工程风险

- **HTMX + Alpine.js + 原生 JS 体系**：无需构建链，引入 SW 后调试复杂度 ↑30%
- **静态资源缓存策略**：CSS/JS 改动后必须确保 SW 更新（用 `skipWaiting` + `clients.claim`）
- **离线状态管理**：UI 需显示"在线/离线"指示器（已有 network status 工具？需调研）

### 5.3 维护风险

- service worker 一旦上线，需长期维护缓存策略
- 每次前端改动都要测试离线场景
- 用户报告"缓存问题"难以复现

---

## 6. 决策建议

### 6.1 推荐方案：**本阶段 E 不实施 PWA**

**理由**：
1. **ROI 最低**：5.5 周工期 vs 有限用户场景
2. **与 SSE 重复**：核心场景（生成完成通知）已被 SSE 解决
3. **离线生成不可行**：TTS 模型 10GB+ 无任何方案能本地化
4. **技术栈冲突**：方案 B 破坏现有 HTMX + Jinja2 架构
5. **CI 调试成本高**：service worker 测试需要专门的 Playwright 流程

### 6.2 替代方案

如果用户坚持要做 PWA，建议：
- **最小化方案**：仅做 manifest.json（半天）+ 静态资源离线缓存（1 天）= **2 天**
- 不做 IndexedDB、不做推送通知、不做后台同步
- 部署 2-3 周后看用户反馈，再决定是否扩大投入

### 6.3 延后到阶段 F

PWA 完整功能（IndexedDB 音频缓存 + 推送通知）建议作为阶段 F 子项：
- 等阶段 E 的 Streaming（E.1）和 LLM-driven（E.2）落地后，前端有更多缓存需求
- 等用户量增长后，"断网回听"和"推送通知"才有真实用户基础
- 阶段 F 时机：阶段 E 完成 + 用户量 > 1k 后

---

## 7. 实施检查清单（如未来要做 PWA）

仅供未来参考，本阶段 E 不实施。

### 7.1 阶段 1：manifest + 基础 SW（2.5 天）

- [ ] 设计 icon 资源（192×192, 512×512, maskable）
- [ ] 创建 `bin/integrated_app/static_pwa/manifest.json`
- [ ] 创建 `bin/integrated_app/static_pwa/sw.js`（仅缓存静态资源）
- [ ] 在 `templates/base.html` 引入 `<link rel="manifest">` 和 SW 注册
- [ ] 浏览器 Console 验证 SW 注册成功
- [ ] DevTools → Application → Manifest 校验通过

### 7.2 阶段 2：IndexedDB 音频缓存（2 周）

- [ ] 选型：原生 IndexedDB（无依赖）vs idb（npm）
- [ ] 设计 schema：`audio` store（key: timestamp, value: blob + meta）
- [ ] 实现 LRU + 容量限制（建议 200MB）
- [ ] UI 增"已下载/可离线播放"图标
- [ ] `routes/audio.py` 响应头加 `Cache-Control: public, max-age=...`

### 7.3 阶段 3：推送通知（2 周）

- [ ] 生成 VAPID 密钥对（`py-vapid` 库）
- [ ] 后端：用户订阅表（SQLite 或扩展 `personas/` schema）
- [ ] 后端：生成完成时主动推送（`pywebpush`）
- [ ] 前端：监听 push 事件 + 显示通知
- [ ] HTTPS 证书配置（生产环境）

### 7.4 阶段 4：后台同步（0.5 周）

- [ ] SW 监听 `sync` 事件
- [ ] IndexedDB 任务队列
- [ ] 网络恢复时重试

---

## 8. 实施状态（已落地）

> 2026-08 起本项目决定完整实施 PWA 5.5 周方案（与第 6 节"不实施"建议相反——根据用户决策
> 调整，认为 PWA 对 TTS 多模型应用有"断网回听"和"安装到桌面"明确价值）。
> 详细设计见 [STAGE_E_PWA_PHASE2.md](./STAGE_E_PWA_PHASE2.md)。

### 8.1 Phase 1 — manifest + Service Worker（已 commit fde7575）

- ✅ Web App Manifest（`bin/integrated_app/static_pwa/manifest.json`）
- ✅ Service Worker v1（`bin/integrated_app/static_pwa/sw.js`）
- ✅ 客户端控制器（`bin/integrated_app/static_pwa/js/pwa.js`）
- ✅ `PwaConfig` 模型（5 字段，3 路由）
- ✅ 4 语言 i18n 键
- ✅ 复用现有 `/favicon.ico`（不生成新 PNG）

### 8.2 Phase 2 — IndexedDB 音频缓存（commit 待提）

- ✅ `idb_cache.js` 模块（Promise 封装、LRU、BroadcastChannel、降级）
- ✅ Service Worker v2（`/api/audio/*.wav` IDB-first 拦截 + 32-hex taskId 校验）
- ✅ `PwaConfig` 扩展 5 字段（idb_audio_cache / max_size_mb / lru_target_pct / broadcast_channel / persist_request）
- ✅ `/api/system/pwa-config` 返回 `idb` 字典 + `phase.idb_audio_cache` 从 Pydantic 读取
- ✅ 用户决策：预存+按需读混合 / 100MB 保守 / 仅本地生成

### 8.3 Phase 3 / 4（待实施）

- ⏳ Phase 3 — VAPID 推送通知（`pwa.vapid_public_key` 已留占位）
- ⏳ Phase 4 — Background Sync 离线生成队列（`networkOnlyWithBackgroundSync` 已留入口）

---

## 9. 参考资料

- MDN: [Progressive Web Apps (PWAs)](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps)
- Vite: [vite-plugin-pwa](https://vite-pwa-org.netlify.app/)
- Google: [Workbox](https://developer.chrome.com/docs/workbox)
- Web: [Push API](https://developer.mozilla.org/en-US/docs/Web/API/Push_API)
- Web: [Background Sync API](https://developer.mozilla.org/en-US/docs/Web/API/Background_Synchronization_API)

---

**报告结论**：本调研建议阶段 E 不实施 PWA，延后到阶段 F。最小化方案（仅 manifest + 基础 SW，2 天）可作为可选增强，由用户在阶段 E 完成后按需启动。
