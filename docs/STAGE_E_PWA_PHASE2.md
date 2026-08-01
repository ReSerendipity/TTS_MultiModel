# Stage E PWA Phase 2 — IndexedDB 音频缓存设计

> **目标**：在 Service Worker 之上增加 IndexedDB（IDB）持久化音频缓存层，
> 实现「生成后秒开」「重复访问无网络往返」「跨标签页共享」三大体验提升。

---

## 1. 范围

### 1.1 已收集的用户决策（commit 前不可变）

| 决策项 | 用户选择 | 替代选项 |
|--------|---------|---------|
| 缓存策略 | **预存 + 按需读混合** | 仅按需读 / 仅预存 |
| 最大存储 | **100 MB（保守）** | 500 MB / 1 GB / 无限 |
| 缓存范围 | **仅本地生成** | + Persona 样本 / + reference |

### 1.2 不在 Phase 2 范围

- ❌ Persona sample 缓存（用户已剔除）
- ❌ Reference 音频缓存（用户已剔除）
- ❌ 前端「清空缓存」UI（聚焦 SW 层；UI 留待 Phase 2.5）
- ❌ i18n 键（前端无文案变化）
- ❌ VAPID 推送（Phase 3）
- ❌ Background Sync 离线队列（Phase 4）

### 1.3 兼容性约束（AGENTS.md §6 + §7）

- 不影响 `/api/sse/events` passthrough
- 不阻塞主流程：IDB 不可用时降级为 no-op
- 不修改后端 API：纯 SW 拦截
- 不修改 `audio_player.js`：通过 SW fetch handler 透明缓存

---

## 2. 数据模型

### 2.1 IndexedDB Schema

- **数据库名**：`tts-multimodel-audio-cache`
- **版本**：`1`（未来 schema 变更时升级）
- **Object Store**：`audios`
  - **keyPath**：`taskId`（来自 filename `{taskId}_{timestamp}.wav`）
- **索引**：
  - `by_last_accessed` — `lastAccessed`（升序，用于 LRU 清理）
  - `by_timestamp` — `timestamp`（升序，按时间排序）

### 2.2 记录结构

```js
{
  taskId: string,          // 主键，UUID4 hex（无连字符，32 位）
  blob: Blob,              // 音频二进制（wav / mp3）
  mimeType: string,        // 'audio/wav' 等
  size: number,            // 字节
  text: string,            // 生成文本（可空，仅作调试信息）
  engine: string,          // 'voxcpm2' / 'indextts2'（可空）
  voice: string,           // persona_id / 'design'（可空）
  duration: number,        // 音频时长（秒，可空）
  timestamp: number,       // 写入时间（Date.now()）
  lastAccessed: number     // LRU 标记（每次 get 时更新）
}
```

### 2.3 URL → taskId 解析

**规则**：从 `/{pathname}.wav` 提取 `taskId = path.basename.split('_')[0]`

- 合法示例：`abc123def456..._1700000000.wav` → `taskId = "abc123def456..."`（32 位 hex）
- 非法示例：`gen_xxx.wav` → `taskId = "gen"`（**不合法**，不是 32 位 hex）
  - **降级策略**：taskId 不是 32 位 hex → 跳过 IDB 缓存，走原 fetch

**强制校验**：`/^[a-f0-9]{32}$/i.test(taskId)` 才写入 IDB。

---

## 3. 缓存策略

### 3.1 写入（预存）

**触发点**：SW fetch handler 拦截 `/api/audio/{filename}.wav` 响应，Content-Type 是 `audio/*`

**流程**：
1. SW 调 `fetch(request)` 拿原始响应
2. 解析 URL 提取 taskId（32 位 hex 校验）
3. `response.blob()` → 异步调 `idbCache.put(record)`（不阻塞响应返回）
4. 响应原路返回给客户端

**失败处理**：
- `put()` 抛 `QuotaExceededError` → 触发 LRU 清理 → 重试 1 次
- 仍失败 → `console.warn` 记录，不影响用户

### 3.2 读取（按需）

**触发点**：SW fetch handler 拦截 `/api/audio/{filename}.wav` 请求

**流程**：
1. 解析 URL 提取 taskId
2. `idbCache.get(taskId)` 查 IDB
3. **命中** → 直接构造 `new Response(blob, headers)` 返回，附 `X-IDB-Cache: HIT` 头（调试用）
4. **未命中** → 走原 fetch，异步写入（见 3.1）

**更新 LRU**：
- 每次 `get` 命中后，原子更新 `lastAccessed = Date.now()`
- 使用 `objectStore.put(record)`（覆盖更新）

### 3.3 LRU 清理

**触发条件**：
- `put` 后总大小 > `idb_max_size_mb * 1024 * 1024`
- `put` 失败 `QuotaExceededError`

**算法**：
1. 用 `by_last_accessed` 索引升序遍历
2. 累计 `deletedSize`，直到 `currentSize - deletedSize <= idb_max_size_mb * 1024 * 1024 * (idb_lru_target_pct / 100)`
3. 默认 `idb_lru_target_pct = 80`（清理后保留 80% 容量作为缓冲）

**例子**：100 MB 上限，LRU 目标 80% → 总大小超 100 MB 时清理到 80 MB。

### 3.4 持久化请求

**启动时**（SW install 后）调 `navigator.storage.persist()`：
- Chrome：可能弹窗（用户可拒绝）
- Firefox：自动授权
- Safari：部分版本不支持

**失败**：catch 后降级，浏览器可能在压力下清理 IDB。

---

## 4. 跨标签页同步（BroadcastChannel）

### 4.1 设计

- **Channel 名**：`tts-idb-audio-cache`
- **消息类型**：
  - `{ type: "PUT", taskId, size }` — 写入后广播
  - `{ type: "GET_HIT", taskId }` — 命中后广播
  - `{ type: "EVICTED", count, freedBytes }` — LRU 清理后广播
  - `{ type: "CLEARED" }` — 清空后广播（Phase 2.5 UI 触发）

### 4.2 用例

- Tab A 写入新音频 → Tab B 收到 `PUT` 事件 → Tab B 的 history UI 可显示「已缓存」徽章
- Tab A LRU 清理 → Tab B 收到 `EVICTED` → Tab B 更新统计

**Phase 2 实现**：仅发送事件，前端 UI 不消费（避免过早优化）。

---

## 5. Service Worker 拦截设计

### 5.1 新增路由规则

在现有 fetch handler 中**新增**规则（在静态资源路由之前）：

```js
// ---- 路由 2.5: 本地生成音频 IDB-first ----
if (IDB_AUDIO_CACHE_ENABLED &&
    url.pathname.startsWith("/api/audio/") &&
    url.pathname.endsWith(".wav")) {
  event.respondWith(idbCacheFirstAudio(request));
  return;
}
```

**位置**：在 `networkOnlyWithBackgroundSync`（POST）之后，static cache-first 之前。
**理由**：audio 是 GET，不应走 POST handler；audio 不属于 static（动态生成）。

### 5.2 idbCacheFirstAudio 实现要点

```js
async function idbCacheFirstAudio(request) {
  const taskId = extractTaskId(request.url);  // 32 hex 校验
  if (!taskId) return fetch(request);  // 非法 URL，走原 fetch

  // 1. 查 IDB
  const cached = await self.__idbCache.get(taskId);
  if (cached) {
    return new Response(cached.blob, {
      headers: {
        "Content-Type": cached.mimeType,
        "Content-Length": String(cached.size),
        "X-IDB-Cache": "HIT",
        "Accept-Ranges": "bytes",  // 兼容 audio 播放器 seek
      },
    });
  }

  // 2. 未命中 → 走原 fetch
  const response = await fetch(request);
  if (response.ok && response.headers.get("Content-Type")?.startsWith("audio/")) {
    // 3. 异步写入（不阻塞响应）
    const blob = await response.clone().blob();
    self.__idbCache.put({
      taskId,
      blob,
      mimeType: response.headers.get("Content-Type"),
      size: blob.size,
      timestamp: Date.now(),
      lastAccessed: Date.now(),
    }).catch((err) => console.warn("[SW] IDB put failed:", taskId, err));
  }
  return response;
}
```

### 5.3 兼容性

- **`Accept-Ranges: bytes`**：原 `/api/audio/*` 路由已返回此头（audio.py:319），IDB 返回也需保持以支持 audio_player seek
- **Range 请求**：当前 SW 不实现 Range 切片（复杂），但普通整段播放可工作
- **206 Partial Content**：客户端用 Range 请求时 IDB 返回 200 整段，浏览器仍可播放（仅不支持 seek-bytes）

**Phase 2.1 优化**（如需）：实现 Range 切片返回 206。

---

## 6. Pydantic 配置扩展

### 6.1 PwaConfig 新增字段

```python
class PwaConfig(BaseModel):
    # ... 现有 8 字段 ...
    idb_audio_cache: bool = Field(
        default=False,
        description="Phase 2: 是否启用 IndexedDB 持久化音频缓存",
    )
    idb_max_size_mb: int = Field(
        default=100, ge=10, le=2000,
        description="IDB 音频缓存最大字节 (MB)，超出触发 LRU 清理",
    )
    idb_lru_target_pct: int = Field(
        default=80, ge=50, le=95,
        description="LRU 清理目标百分比（占 max_size），保留缓冲避免频繁清理",
    )
    idb_broadcast_channel: bool = Field(
        default=True,
        description="是否启用 BroadcastChannel 跨标签页同步",
    )
    idb_persist_request: bool = Field(
        default=True,
        description="启动时是否调 navigator.storage.persist() 请求持久化",
    )
```

### 6.2 config.yaml 同步

```yaml
pwa:
  enabled: true
  cache_version: "v2"  # 升级到 v2 触发旧缓存清理
  offline_enabled: true
  precache_urls:
    - "/"
    - "/favicon.ico"
    - "/manifest.json"
  api_cache_max_age_s: 300
  html_cache_max_entries: 50
  scope: "/"
  vapid_public_key: ""
  # ===== Phase 2: IndexedDB =====
  idb_audio_cache: true           # 用户决策：仅本地生成音频
  idb_max_size_mb: 100            # 用户决策：保守
  idb_lru_target_pct: 80
  idb_broadcast_channel: true
  idb_persist_request: true
```

### 6.3 load_config_dict 路径

`config_models.py` 的 `load_config_dict` 使用 `extra="ignore"`，新字段**自动**被识别。
但仍需在 `PwaConfig` 定义字段以保证类型安全。

### 6.4 routes/pages.py phase 字段同步

将硬编码的 `"idb_audio_cache": False` 改为读 `pwa.idb_audio_cache`：

```python
"idb_audio_cache": pwa.idb_audio_cache,
```

同时 `idb_max_size_mb` 和 `idb_lru_target_pct` 也要返回（SW 启动时从 `/api/system/pwa-config` 读取）：

```python
return {
    # ... 现有字段 ...
    "idb": {
        "enabled": pwa.idb_audio_cache,
        "max_size_mb": pwa.idb_max_size_mb,
        "lru_target_pct": pwa.idb_lru_target_pct,
        "broadcast_channel": pwa.idb_broadcast_channel,
        "persist_request": pwa.idb_persist_request,
    },
    "phase": { ... 现有 ... },
}
```

**但**：SW 不读此端点（按 §5 设计，SW 硬编码 IDB_AUDIO_CACHE_ENABLED）——**这个改动只为前端 /api/system/pwa-config 调试用**。

---

## 7. 文件变更清单

### 7.1 新建（2）

| 文件 | 行数预估 | 职责 |
|------|---------|------|
| `bin/integrated_app/static_pwa/js/idb_cache.js` | 200-250 | IDB Promise 封装、LRU、broadcast、estimate、put/get/clear、降级 stub |
| `docs/STAGE_E_PWA_PHASE2.md` | (本文件) | 本 spec |

### 7.2 修改（5）

| 文件 | 改动 |
|------|------|
| `bin/integrated_app/static_pwa/sw.js` | VERSION v1→v2；`importScripts` 引入 idb_cache；新增 `/api/audio/*.wav` 拦截 handler；新增 `extractTaskId` + `idbCacheFirstAudio` 函数 |
| `bin/integrated_app/config_models.py` | `PwaConfig` 加 5 字段 |
| `config.yaml` | `pwa:` 节加 5 字段；`cache_version: "v2"` |
| `bin/integrated_app/routes/pages.py` | `/api/system/pwa-config` 加 `idb` 字典；`phase.idb_audio_cache` 读 Pydantic |
| `docs/STAGE_E_PWA_FEASIBILITY.md` | 同步 Phase 2 决策摘要（链接到本 spec） |

---

## 8. 验证计划

### 8.1 静态

- `read_lints` 0 错误（`config_models.py` / `pages.py` / `idb_cache.js` / `sw.js`）
- `python -c "from bin.integrated_app.app_server import create_app"` 成功
- `python -c "from bin.integrated_app.config_models import PwaConfig; PwaConfig()"` 成功
- FastAPI TestClient 实测 5 路由（含 pwa-config 新字段）

### 8.2 运行时（手动 Phase 2.5+）

- 浏览器 DevTools → Application → IndexedDB → `tts-multimodel-audio-cache` → `audios` store
- 触发生成 → 等待 → 检查 IDB 中出现对应 taskId 记录
- 重新触发同文本生成（history click）→ Network 面板确认请求被 SW 处理，Response Header 含 `X-IDB-Cache: HIT`
- 填满 100 MB → 检查 LRU 自动清理

### 8.3 降级

- 浏览器隐私模式 → IDB 不可用 → SW 拦截代码 try/catch 降级到原 fetch
- 配额超限 → LRU 清理 + 重试 1 次 + 最终放弃

---

## 9. 风险评估

| 风险 | 缓解 |
|------|------|
| IDB 跨浏览器 bug（Safari 隐私模式） | 所有 IDB 操作 try/catch 降级到 no-op |
| Quota 超限 | LRU 清理 + 重试 1 次 + 放弃 |
| Range 请求不支持 206 | Phase 2.0 接受 200 整段（播放器仍可播放，仅失去 seek-bytes） |
| 多 tab 并发写 | IDB 事务保护；BroadcastChannel 仅通知 |
| 历史记录 taskId 重复 | 32 hex 校验 + 重复时 lastAccessed 更新（LRU 仍正确） |
| SW 升级失败 | `skipWaiting + clients.claim` 已配置，强制接管 |

---

## 10. 后续 Phase 接口预留

- **Phase 2.5**（可选）：暴露「清空缓存」UI → 调 `idb_cache.clear()` + BroadcastChannel
- **Phase 3**：VAPID 推送通知（`pwa.vapid_public_key` 已有占位）
- **Phase 4**：Background Sync 离线生成队列（`networkOnlyWithBackgroundSync` 已留入口）

---

## 11. 变更日志

- **2026-08-01** — 初始版本（用户决策：预存+按需读 / 100MB / 仅本地生成）
