/* =============================================================================
 * TTS MultiModel - IndexedDB Audio Cache (Phase 2)
 *
 * 职责（SW 层）：
 *   1. 封装 IndexedDB 异步 API 为 Promise 接口
 *   2. 实现 LRU 清理（按 lastAccessed 升序删除）
 *   3. BroadcastChannel 跨标签页同步（PUT / GET_HIT / EVICTED / CLEARED）
 *   4. navigator.storage.persist() 请求持久化
 *   5. 失败降级：IDB 不可用时所有方法静默 no-op（不抛错、不阻塞调用方）
 *
 * 暴露 API（挂载到 self.__idbCache，供 SW 调用）：
 *   - isAvailable(): boolean — IDB 是否可用
 *   - open(): Promise<boolean> — 打开数据库，返回是否成功
 *   - put(record): Promise<boolean> — 写入或覆盖，触发 LRU
 *   - get(taskId): Promise<record | null> — 读取，更新 lastAccessed
 *   - delete(taskId): Promise<boolean> — 删除单条
 *   - clear(): Promise<boolean> — 清空全部
 *   - evictLRU(): Promise<{count, freedBytes}> — 强制 LRU 清理
 *   - estimate(): Promise<{usage, quota}> — 配额查询
 *   - requestPersist(): Promise<boolean> — 请求持久化
 *   - getTotalSize(): Promise<number> — 当前总字节
 *
 * 记录结构（与 STAGE_E_PWA_PHASE2.md §2.2 严格对齐）：
 *   { taskId, blob, mimeType, size, text?, engine?, voice?,
 *     duration?, timestamp, lastAccessed }
 *
 * 约束（AGENTS.md §1.5 禁止编造）：
 *   - 不假设 navigator.storage 存在（旧浏览器降级）
 *   - 不假设 BroadcastChannel 存在（旧浏览器降级为 no-op）
 *   - 所有 IDB 异常被捕获，调用方拿到 false / null 而非抛错
 * ============================================================================= */

(function (global) {
  "use strict";

  // ----- 配置常量（与 config.yaml pwa.idb_* 同步，靠人工保证） -----
  const DB_NAME = "tts-multimodel-audio-cache";
  const DB_VERSION = 1;
  const STORE_NAME = "audios";
  const INDEX_LAST_ACCESSED = "by_last_accessed";
  const INDEX_TIMESTAMP = "by_timestamp";
  const CHANNEL_NAME = "tts-idb-audio-cache";
  const TASK_ID_PATTERN = /^[a-f0-9]{32}$/i;

  // 容量配置（默认与 config.yaml 一致；SW 启动后可被外部覆盖）
  let MAX_SIZE_MB = 100;
  let LRU_TARGET_PCT = 80;
  let BROADCAST_ENABLED = true;
  let PERSIST_REQUESTED = false;

  // ----- 内部状态 -----
  let dbPromise = null;
  let broadcastChannel = null;
  let available = null;  // null = 未知，true/false = 已检测

  // ===========================================================================
  // 0. 能力检测
  // ===========================================================================
  function isAvailable() {
    if (available !== null) return available;
    try {
      available = typeof global.indexedDB !== "undefined";
    } catch (e) {
      available = false;
    }
    if (!available) {
      console.warn("[IDB] IndexedDB not available, all methods will no-op");
    }
    return available;
  }

  // ===========================================================================
  // 1. 打开数据库（幂等）
  // ===========================================================================
  function open() {
    if (!isAvailable()) return Promise.resolve(false);
    if (dbPromise) return dbPromise.then(() => true);

    dbPromise = new Promise((resolve, reject) => {
      const req = global.indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: "taskId" });
          store.createIndex(INDEX_LAST_ACCESSED, "lastAccessed", { unique: false });
          store.createIndex(INDEX_TIMESTAMP, "timestamp", { unique: false });
          console.info("[IDB] Schema created: store=audios, indexes=lastAccessed/timestamp");
        }
      };
      req.onsuccess = (event) => {
        console.info("[IDB] Database opened, version=" + event.target.result.version);
        resolve(event.target.result);
      };
      req.onerror = (event) => {
        console.warn("[IDB] open() error:", event.target.errorCode);
        dbPromise = null;  // 允许重试
        available = false;
        reject(event.target.error);
      };
      req.onblocked = () => {
        console.warn("[IDB] open() blocked by another connection");
      };
    }).catch((err) => {
      console.warn("[IDB] open() failed:", err);
      return null;
    });

    return dbPromise.then((db) => db !== null);
  }

  function getDB() {
    if (!dbPromise) return Promise.resolve(null);
    return dbPromise.catch(() => null);
  }

  // ===========================================================================
  // 2. BroadcastChannel 初始化（幂等）
  // ===========================================================================
  function getChannel() {
    if (!BROADCAST_ENABLED) return null;
    if (broadcastChannel !== null) return broadcastChannel;
    if (typeof global.BroadcastChannel === "undefined") {
      console.warn("[IDB] BroadcastChannel not supported, sync disabled");
      BROADCAST_ENABLED = false;
      return null;
    }
    try {
      broadcastChannel = new global.BroadcastChannel(CHANNEL_NAME);
      console.info("[IDB] BroadcastChannel ready:", CHANNEL_NAME);
      return broadcastChannel;
    } catch (e) {
      console.warn("[IDB] BroadcastChannel init failed:", e);
      BROADCAST_ENABLED = false;
      return null;
    }
  }

  function broadcast(message) {
    const ch = getChannel();
    if (!ch) return;
    try {
      ch.postMessage(message);
    } catch (e) {
      console.warn("[IDB] broadcast() failed:", e);
    }
  }

  // ===========================================================================
  // 3. 写入（put）—— 触发 LRU 检查
  // ===========================================================================
  async function put(record) {
    if (!isAvailable()) return false;
    if (!record || !record.taskId || !TASK_ID_PATTERN.test(record.taskId)) {
      console.warn("[IDB] put() rejected: invalid taskId", record && record.taskId);
      return false;
    }
    if (!(record.blob instanceof global.Blob)) {
      console.warn("[IDB] put() rejected: missing or invalid blob");
      return false;
    }

    try {
      const db = await getDB();
      if (!db) return false;

      // 补充字段
      const now = Date.now();
      const fullRecord = {
        taskId: record.taskId,
        blob: record.blob,
        mimeType: record.mimeType || "audio/wav",
        size: record.size || record.blob.size,
        text: record.text || "",
        engine: record.engine || "",
        voice: record.voice || "",
        duration: record.duration || 0,
        timestamp: record.timestamp || now,
        lastAccessed: now,
      };

      // 先尝试直接写入
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      store.put(fullRecord);
      await txComplete(tx);

      // 写入后检查容量，触发 LRU
      const totalSize = await getTotalSize();
      const maxBytes = MAX_SIZE_MB * 1024 * 1024;
      if (totalSize > maxBytes) {
        console.info("[IDB] over capacity, triggering LRU:", totalSize, ">", maxBytes);
        const result = await evictLRU();
        broadcast({ type: "EVICTED", count: result.count, freedBytes: result.freedBytes });
      }

      broadcast({ type: "PUT", taskId: record.taskId, size: fullRecord.size });
      return true;
    } catch (err) {
      // QuotaExceededError：尝试 LRU 清理后重试 1 次
      if (err && err.name === "QuotaExceededError") {
        console.warn("[IDB] QuotaExceededError, attempting LRU + retry");
        const result = await evictLRU().catch(() => ({ count: 0, freedBytes: 0 }));
        broadcast({ type: "EVICTED", count: result.count, freedBytes: result.freedBytes });
        try {
          const db2 = await getDB();
          if (!db2) return false;
          const tx2 = db2.transaction(STORE_NAME, "readwrite");
          tx2.objectStore(STORE_NAME).put(fullRecord);
          await txComplete(tx2);
          broadcast({ type: "PUT", taskId: record.taskId, size: fullRecord.size });
          return true;
        } catch (err2) {
          console.warn("[IDB] put() retry failed, giving up:", err2);
          return false;
        }
      }
      console.warn("[IDB] put() failed:", err);
      return false;
    }
  }

  // ===========================================================================
  // 4. 读取（get）—— 更新 lastAccessed
  // ===========================================================================
  async function get(taskId) {
    if (!isAvailable() || !TASK_ID_PATTERN.test(taskId)) return null;
    try {
      const db = await getDB();
      if (!db) return null;
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      const record = await promisifyRequest(store.get(taskId));
      if (!record) {
        await txComplete(tx);
        return null;
      }
      // 更新 lastAccessed（LRU 标记）
      record.lastAccessed = Date.now();
      store.put(record);
      await txComplete(tx);

      broadcast({ type: "GET_HIT", taskId });
      return record;
    } catch (err) {
      console.warn("[IDB] get() failed:", taskId, err);
      return null;
    }
  }

  // ===========================================================================
  // 5. 删除单条
  // ===========================================================================
  async function deleteRecord(taskId) {
    if (!isAvailable() || !TASK_ID_PATTERN.test(taskId)) return false;
    try {
      const db = await getDB();
      if (!db) return false;
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete(taskId);
      await txComplete(tx);
      return true;
    } catch (err) {
      console.warn("[IDB] delete() failed:", taskId, err);
      return false;
    }
  }

  // ===========================================================================
  // 6. 清空全部
  // ===========================================================================
  async function clear() {
    if (!isAvailable()) return false;
    try {
      const db = await getDB();
      if (!db) return false;
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).clear();
      await txComplete(tx);
      broadcast({ type: "CLEARED" });
      console.info("[IDB] cache cleared");
      return true;
    } catch (err) {
      console.warn("[IDB] clear() failed:", err);
      return false;
    }
  }

  // ===========================================================================
  // 7. LRU 清理
  // ===========================================================================
  async function evictLRU() {
    if (!isAvailable()) return { count: 0, freedBytes: 0 };
    try {
      const db = await getDB();
      if (!db) return { count: 0, freedBytes: 0 };

      const totalSize = await getTotalSize();
      const maxBytes = MAX_SIZE_MB * 1024 * 1024;
      const targetBytes = maxBytes * (LRU_TARGET_PCT / 100);

      if (totalSize <= maxBytes) {
        return { count: 0, freedBytes: 0 };
      }

      let deletedCount = 0;
      let freedBytes = 0;
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      const index = store.index(INDEX_LAST_ACCESSED);

      await new Promise((resolve, reject) => {
        const cursorReq = index.openCursor();
        cursorReq.onsuccess = (event) => {
          const cursor = event.target.result;
          if (!cursor) {
            resolve();
            return;
          }
          // 已降到目标以下，停止清理
          if (totalSize - freedBytes <= targetBytes) {
            resolve();
            return;
          }
          const record = cursor.value;
          freedBytes += record.size || 0;
          cursor.delete();
          deletedCount++;
          cursor.continue();
        };
        cursorReq.onerror = (event) => reject(event.target.error);
      });
      await txComplete(tx);

      console.info(
        "[IDB] LRU evicted:",
        deletedCount, "items,", freedBytes, "bytes freed"
      );
      return { count: deletedCount, freedBytes: freedBytes };
    } catch (err) {
      console.warn("[IDB] evictLRU() failed:", err);
      return { count: 0, freedBytes: 0 };
    }
  }

  // ===========================================================================
  // 8. 配额查询
  // ===========================================================================
  async function estimate() {
    if (typeof global.navigator === "undefined" ||
        !global.navigator.storage ||
        typeof global.navigator.storage.estimate !== "function") {
      return { usage: 0, quota: 0, supported: false };
    }
    try {
      const result = await global.navigator.storage.estimate();
      return {
        usage: result.usage || 0,
        quota: result.quota || 0,
        supported: true,
      };
    } catch (err) {
      console.warn("[IDB] estimate() failed:", err);
      return { usage: 0, quota: 0, supported: false };
    }
  }

  // ===========================================================================
  // 9. 持久化请求
  // ===========================================================================
  async function requestPersist() {
    if (!PERSIST_REQUESTED) return false;
    if (typeof global.navigator === "undefined" ||
        !global.navigator.storage ||
        typeof global.navigator.storage.persist !== "function") {
      return false;
    }
    try {
      const granted = await global.navigator.storage.persist();
      console.info("[IDB] storage.persist() granted:", granted);
      return granted === true;
    } catch (err) {
      console.warn("[IDB] requestPersist() failed:", err);
      return false;
    }
  }

  // ===========================================================================
  // 10. 统计当前总字节
  // ===========================================================================
  async function getTotalSize() {
    if (!isAvailable()) return 0;
    try {
      const db = await getDB();
      if (!db) return 0;
      const tx = db.transaction(STORE_NAME, "readonly");
      const store = tx.objectStore(STORE_NAME);
      let total = 0;
      await new Promise((resolve, reject) => {
        const cursorReq = store.openCursor();
        cursorReq.onsuccess = (event) => {
          const cursor = event.target.result;
          if (!cursor) {
            resolve();
            return;
          }
          total += cursor.value.size || 0;
          cursor.continue();
        };
        cursorReq.onerror = (event) => reject(event.target.error);
      });
      return total;
    } catch (err) {
      console.warn("[IDB] getTotalSize() failed:", err);
      return 0;
    }
  }

  // ===========================================================================
  // 11. 内部辅助：Promise 化 IDBRequest
  // ===========================================================================
  function promisifyRequest(request) {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  function txComplete(tx) {
    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("transaction aborted"));
    });
  }

  // ===========================================================================
  // 12. 配置（运行时覆盖）
  // ===========================================================================
  function configure(options) {
    if (!options) return;
    if (typeof options.maxSizeMB === "number" && options.maxSizeMB > 0) {
      MAX_SIZE_MB = options.maxSizeMB;
    }
    if (typeof options.lruTargetPct === "number" &&
        options.lruTargetPct >= 50 && options.lruTargetPct <= 95) {
      LRU_TARGET_PCT = options.lruTargetPct;
    }
    if (typeof options.broadcastEnabled === "boolean") {
      BROADCAST_ENABLED = options.broadcastEnabled;
    }
    if (typeof options.persistRequested === "boolean") {
      PERSIST_REQUESTED = options.persistRequested;
    }
  }

  // ===========================================================================
  // 13. 暴露 API
  // ===========================================================================
  const idbCache = {
    isAvailable: isAvailable,
    open: open,
    put: put,
    get: get,
    delete: deleteRecord,
    clear: clear,
    evictLRU: evictLRU,
    estimate: estimate,
    requestPersist: requestPersist,
    getTotalSize: getTotalSize,
    configure: configure,
    // 常量（供 SW 判断 taskId 格式）
    TASK_ID_PATTERN: TASK_ID_PATTERN,
  };

  // SW 内部：self.__idbCache
  // Window 内部：window.__idbCache（Phase 2.5 UI 复用）
  global.__idbCache = idbCache;
})(typeof self !== "undefined" ? self : this);
