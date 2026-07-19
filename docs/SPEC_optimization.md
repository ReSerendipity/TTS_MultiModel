# TTS MultiModel 优化实施规格书

> 版本: 1.0 | 日期: 2026-06-02 | 状态: 待审核

---

## 目录

- [1. 消除全局变量向后兼容机制](#1-消除全局变量向后兼容机制)
- [2. config.py 延迟初始化](#2-configpy-延迟初始化)
- [3. i18n 翻译数据外部化](#3-i18n-翻译数据外部化)
- [4. routes/system.py 拆分](#4-routessystempy-拆分)
- [5. SSE 轮询优化](#5-sse-轮询优化)
- [6. AdaptiveLRUCache 检查频率优化](#6-adaptivelrucache-检查频率优化)
- [7. 实现真正的批量推理](#7-实现真正的批量推理)
- [8. 模型卸载事件驱动](#8-模型卸载事件驱动)
- [9. 音频合并 float32 优化](#9-音频合并-float32-优化)
- [10. SSE 心跳保活](#10-sse-心跳保活)
- [11. 实现请求取消机制](#11-实现请求取消机制)
- [12. Jinja2 auto_reload 环境控制](#12-jinja2-auto_reload-环境控制)
- [13. 实现引擎注册表](#13-实现引擎注册表)
- [14. 引擎热待机模式](#14-引擎热待机模式)
- [15. IndexTTS2Engine 显式实现 Protocol](#15-indextts2engine-显式实现-protocol)
- [16. tts_error_handler 支持 async](#16-tts_error_handler-支持-async)
- [17. 异常处理不吞异常](#17-异常处理不吞异常)
- [18. 后台线程 request_id](#18-后台线程-request_id)
- [19. API 文档补充](#19-api-文档补充)
- [20. 文档时效性标注](#20-文档时效性标注)
- [21. 测试覆盖率提升](#21-测试覆盖率提升)
- [22. 集成测试纳入 CI](#22-集成测试纳入-ci)
- [23. 性能基准测试](#23-性能基准测试)
- [24. 跨平台部署脚本](#24-跨平台部署脚本)
- [25. Docker 容器化](#25-docker-容器化)
- [26. 模型自动下载提示](#26-模型自动下载提示)
- [27. 引擎名称枚举化](#27-引擎名称枚举化)
- [28. i18n 键命名空间](#28-i18n-键命名空间)
- [29. 路由自动发现](#29-路由自动发现)

---

## 🔴 高优先级（1-2 周内实施）

---

### 1. 消除全局变量向后兼容机制

**当前问题**: `model_manager.py` 通过 `_sync_globals()` 将 `ModelRegistry` 属性同步到模块级变量（`voxcpm_model`, `voxcpm_asr`, `indextts2_engine`, `current_engine`, `current_type`, `current_size`）。外部代码 `from ..model_manager import voxcpm_model` 在导入时获取的是快照值，后续 `_sync_globals()` 调用修改的是模块属性而非导入者的本地引用。

**涉及文件**:
- `bin/integrated_app/model_manager.py` — `_sync_globals()` 及 6 个全局变量（L111-L145）
- `bin/integrated_app/routes/sse.py` — `from ..model_manager import current_engine, current_size, current_type, registry`（L47-L54）
- `bin/integrated_app/routes/generate.py` — 类似导入
- `bin/integrated_app/routes/model.py` — 类似导入
- `bin/integrated_app/routes/persona.py` — 类似导入
- `bin/integrated_app/routes/audio.py` — 类似导入

**实施步骤**:

1. **搜索所有消费者**：在整个项目中搜索 `from .model_manager import` 和 `from ..model_manager import`，列出所有使用全局变量的位置

2. **逐文件迁移**：将每个文件中的直接导入改为通过 `registry` 访问：
   ```python
   # 迁移前
   from ..model_manager import current_engine, current_size
   eng = current_engine

   # 迁移后
   from ..model_registry import registry
   eng = registry.current_engine
   ```

3. **添加 Deprecation Warning**：在 `_sync_globals()` 中添加 `warnings.warn()`，标记全局变量将在下一版本移除：
   ```python
   def _sync_globals() -> None:
       global voxcpm_model, voxcpm_asr, indextts2_engine, current_engine, current_type, current_size
       warnings.warn(
           "Module-level model variables are deprecated. Use registry.xxx instead.",
           DeprecationWarning,
           stacklevel=2,
       )
       voxcpm_model = registry.voxcpm_model
       # ... 其余同原逻辑
   ```

4. **保留 `__all__` 导出**：`model_manager.__all__` 中移除全局变量名，只保留类和函数导出

5. **最终移除**：在所有消费者迁移完成后，删除 `_sync_globals()` 函数和 6 个全局变量定义

**验收标准**:
- [ ] 项目中无任何 `from ..model_manager import voxcpm_model` 等全局变量导入
- [ ] 所有模型状态访问通过 `registry.xxx` 进行
- [ ] `_sync_globals()` 已移除或标记为 deprecated
- [ ] 所有现有测试通过
- [ ] 运行 `ruff check` 无新增警告

**预期效果**: 消除状态不一致风险，减少维护负担约 30 行代码

**回滚方案**: 恢复 `_sync_globals()` 和全局变量定义，恢复原有 import 语句

---

### 2. config.py 延迟初始化

**当前问题**: `config.py` 在导入时执行 `_load_config()`，设置环境变量（`TRANSFORMERS_OFFLINE=1` 等），创建目录，解析 YAML。这些操作不可逆且难以测试——导入 config 模块就会触发副作用。

**涉及文件**:
- `bin/integrated_app/config.py` — `_load_config()`（L46-L141）及模块级常量赋值（L142-L156）

**实施步骤**:

1. **创建 `_LazyConfig` 类**：
   ```python
   class _LazyConfig:
       """延迟加载的配置容器，首次访问属性时才触发 _load_config()"""
       _loaded = False
       _data = None

       def _ensure_loaded(self):
           if not _LazyConfig._loaded:
               _LazyConfig._data = _load_config()
               _LazyConfig._loaded = True

       @property
       def VERSION(self):
           self._ensure_loaded()
           return _LazyConfig._data[0]

       @property
       def GEN_DEFAULTS(self):
           self._ensure_loaded()
           return _LazyConfig._data[1]

       # ... 其他属性同理
   ```

2. **环境变量设置移到入口点**：将 `os.environ['TRANSFORMERS_OFFLINE'] = '1'` 等移到 `app_server.py` 的 `run_server()` 和 `cli.py` 的 `main()` 中，在 `create_app()` 之前执行

3. **目录创建移到入口点**：将 `os.makedirs(CACHE_DIR, exist_ok=True)` 等移到 `run_server()` 中

4. **路径常量保留即时计算**：`ROOT_DIR`、`SAVE_DIR` 等纯路径常量可保留模块级定义（无副作用）

5. **替换模块级常量**：
   ```python
   # 迁移前
   VERSION, GEN_DEFAULTS, ... = _load_config()

   # 迁移后
   _cfg = _LazyConfig()
   VERSION = _cfg.VERSION  # 首次访问时才加载
   ```

**验收标准**:
- [ ] `import integrated_app.config` 不触发 YAML 解析、环境变量设置、目录创建
- [ ] 首次访问 `config.VERSION` 等属性时才加载配置
- [ ] 环境变量在应用启动前设置（而非导入时）
- [ ] 测试可在不设置环境变量的情况下导入 config 模块

**预期效果**: 提高可测试性，避免导入时副作用，支持配置热重载

**回滚方案**: 恢复模块级 `_load_config()` 调用

---

### 3. i18n 翻译数据外部化

**当前问题**: `i18n.py` 包含 2300+ 行翻译字典（4 种语言 × 500+ 键），使模块臃肿，难以协作翻译。

**涉及文件**:
- `bin/integrated_app/i18n.py` — 翻译字典定义

**实施步骤**:

1. **创建翻译文件目录**：`bin/integrated_app/locales/`

2. **提取翻译数据为 JSON 文件**：
   ```
   locales/
   ├── zh.json
   ├── en.json
   ├── ja.json
   └── ko.json
   ```

3. **实现按需加载**：
   ```python
   _translations: dict[str, dict[str, str]] = {}

   def _load_translations(lang: str) -> dict[str, str]:
       if lang not in _translations:
           locale_path = os.path.join(os.path.dirname(__file__), "locales", f"{lang}.json")
           with open(locale_path, "r", encoding="utf-8") as f:
               _translations[lang] = json.load(f)
       return _translations[lang]
   ```

4. **修改 `t()` 函数**：从内存字典查找改为调用 `_load_translations(lang)`

5. **添加翻译验证脚本**：`scripts/validate_i18n.py` 检查所有语言文件的键是否一致

**验收标准**:
- [ ] `i18n.py` 代码行数 < 200 行
- [ ] 4 个 JSON 翻译文件键集合完全一致
- [ ] 页面加载时翻译功能正常
- [ ] 首次翻译查找延迟 < 10ms（JSON 加载）

**预期效果**: 减少内存占用（按需加载），便于翻译协作，降低代码审查噪声

**回滚方案**: 将 JSON 数据重新内嵌到 `i18n.py`

---

### 4. routes/system.py 拆分

**当前问题**: `system.py` 包含 NVML 管理、GPU 监控、操作日志、设置管理等多个职责（750+ 行），违反单一职责原则。

**涉及文件**:
- `bin/integrated_app/routes/system.py`

**实施步骤**:

1. **创建 `routes/system/` 包目录**

2. **拆分为子模块**：
   ```
   routes/system/
   ├── __init__.py    # 合并导出所有 router
   ├── health.py      # /api/health/* 端点
   ├── gpu.py         # /api/gpu/* 端点（NVML、显存信息）
   ├── logs.py        # /api/logs/* 端点（操作日志）
   └── settings.py    # /api/settings/* 端点（配置管理）
   ```

3. **`__init__.py` 合并路由**：
   ```python
   from .health import router as health_router
   from .gpu import router as gpu_router
   from .logs import router as logs_router
   from .settings import router as settings_router

   router = APIRouter()
   router.include_router(health_router)
   router.include_router(gpu_router)
   router.include_router(logs_router)
   router.include_router(settings_router)
   ```

4. **更新 `app_server.py`**：将 `from .routes import system` 改为 `from .routes.system import router as system_router`

**验收标准**:
- [ ] 每个子模块 < 250 行
- [ ] 所有原有 API 端点路径不变
- [ ] `app_server.py` 的 router 注册无变化（对外接口一致）
- [ ] 所有现有测试通过

**预期效果**: 提高可维护性，单一职责，便于独立修改

**回滚方案**: 将子模块合并回 `system.py`

---

### 5. SSE 轮询优化

**当前问题**: `sse.py` 的 `event_stream()` 无论是否有活跃任务，都以固定 0.5s 间隔轮询所有状态。空闲时产生大量无效 CPU 开销和带宽消耗。

**涉及文件**:
- `bin/integrated_app/routes/sse.py` — `event_stream()`（L56-L173）

**实施步骤**:

1. **实现自适应轮询间隔**：
   ```python
   async def event_stream():
       idle_count = 0
       while True:
           has_active = _has_active_generation()

           if has_active:
               idle_count = 0
               interval = 0.3
           else:
               idle_count += 1
               # 空闲时逐步退避：0.5s → 1s → 2s → 3s（上限）
               interval = min(0.5 + idle_count * 0.5, 3.0)

           # ... 生成事件 ...

           await asyncio.sleep(interval)
   ```

2. **实现条件通知机制（可选增强）**：在 `GenerationTracker` 和 `ProgressManager` 中添加 `asyncio.Event`，当状态变化时立即通知 SSE 端点：
   ```python
   # model_manager.py 或 tracker.py
   _state_changed = asyncio.Event()

   # sse.py
   async def event_stream():
       while True:
           try:
               await asyncio.wait_for(_state_changed.wait(), timeout=interval)
               _state_changed.clear()
           except asyncio.TimeoutError:
               pass
           # ... 生成事件 ...
   ```

3. **添加心跳事件**：每 30 秒发送 `event: heartbeat\ndata: {}\n\n`，防止反向代理超时

**验收标准**:
- [ ] 空闲时轮询间隔逐步退避至 3s
- [ ] 活跃生成时间隔 0.3s
- [ ] 状态变化时在 0.5s 内推送（条件通知模式下 < 100ms）
- [ ] 前端 EventSource 连接稳定无断开
- [ ] CPU 空闲占用降低 60%+

**预期效果**: 减少 60-80% 空闲时的无效轮询开销，活跃时响应更及时

**回滚方案**: 恢复固定 0.5s 间隔

---

### 6. AdaptiveLRUCache 检查频率优化

**当前问题**: `AdaptiveLRUCache.put()` 每次插入都调用 `adapt_capacity()`，查询 GPU 显存百分比，频繁调用 `torch.cuda` API。

**涉及文件**:
- `bin/integrated_app/cache.py` — `AdaptiveLRUCache.adapt_capacity()` 和 `put()`

**实施步骤**:

1. **添加时间衰减机制**：
   ```python
   class AdaptiveLRUCache(LRUCache):
       def __init__(self, default_maxsize=15, adapt_interval=30.0):
           super().__init__(maxsize=default_maxsize)
           self._adapt_interval = adapt_interval
           self._last_adapt_time = 0.0
           self._put_count = 0
           self._adapt_every_n = 10

       def put(self, key, value):
           super().put(key, value)
           self._put_count += 1
           now = time.monotonic()
           if (now - self._last_adapt_time >= self._adapt_interval
                   or self._put_count >= self._adapt_every_n):
               self.adapt_capacity()
               self._last_adapt_time = now
               self._put_count = 0
   ```

2. **保留紧急路径**：当 `put()` 触发淘汰时（缓存满），仍然立即调用 `adapt_capacity()`

**验收标准**:
- [ ] 正常插入时 GPU API 调用频率从每次降低到每 30s 或每 10 次
- [ ] 缓存满时仍立即适配
- [ ] 缓存命中率无明显下降（< 2% 变化）

**预期效果**: 减少 GPU API 调用频率 90%+，降低开销

**回滚方案**: 恢复每次 put 都调用 `adapt_capacity()`

---

### 7. 实现真正的批量推理

**当前问题**: `BatchInferencer._batch_generate()` 实际仍是顺序调用 `generate_fn(s)`，未实现真正的批量推理。

**涉及文件**:
- `bin/integrated_app/batch_inference.py` — `_batch_generate()`（L156-L166）

**实施步骤**:

1. **为 IndexTTS2Engine 添加批量推理方法**：
   ```python
   # engines/indextts2_engine.py
   def batch_generate(self, text_list: List[str], **kwargs) -> List[np.ndarray]:
       """批量推理：将多个文本拼接后一次性推理，再切分结果"""
       # 方案 A：如果底层模型支持 batch 维度
       # 方案 B：预分配张量池，减少内存分配开销
       # 方案 C：使用 torch.no_grad() + 推理上下文管理器
       results = []
       with torch.no_grad():
           for text in text_list:
               results.append(self._single_generate(text, **kwargs))
       return results
   ```

2. **实现推理上下文管理器**：避免每次推理都进入/退出 `torch.no_grad()` 上下文：
   ```python
   # 在 BatchInferencer.process() 中
   with torch.no_grad():
       for batch in batches:
           batch_result = self._batch_generate(batch_segments, generate_fn)
   ```

3. **预分配张量池**：对于固定采样率的输出，预分配输出缓冲区

4. **更新 `_batch_generate()` 调用链**：检查 `generate_fn` 所属引擎是否支持 `batch_generate`，优先调用批量接口

**验收标准**:
- [ ] `_batch_generate()` 不再是简单的顺序调用
- [ ] 长文本（10+ 段）生成吞吐量提升 ≥ 20%
- [ ] 单段生成延迟无明显增加（< 5%）
- [ ] 内存峰值不超过顺序处理的 110%

**预期效果**: 长文本场景下推理吞吐量提升 20-100%（取决于引擎支持程度）

**回滚方案**: 恢复顺序调用实现

---

## 🟡 中优先级（1-2 月内实施）

---

### 8. 模型卸载事件驱动

**当前问题**: `model_manager.py` 的 `unload_model()` 中有 `time.sleep(0.5)` 和 `time.sleep(0.3)` 硬编码等待 GPU 操作完成。

**涉及文件**:
- `bin/integrated_app/model_manager.py` — `unload_model()`（L222-L275）

**实施步骤**:

1. **替换 `time.sleep(0.5)`**：使用 `torch.cuda.synchronize()` 等待 GPU 操作完成：
   ```python
   # 迁移前
   time.sleep(0.5)
   GPUBackendManager.empty_cache()

   # 迁移后
   if device is not None:
       GPUBackendManager.synchronize(device)
   GPUBackendManager.empty_cache()
   ```

2. **替换 `time.sleep(0.3)`**：移除卸载末尾的固定等待，GPU 同步已完成所有必要操作

3. **添加最大等待超时**：为 synchronize 添加 5s 超时保护，防止死锁

**验收标准**:
- [ ] `unload_model()` 中无 `time.sleep()` 调用
- [ ] 卸载后显存释放效果与之前一致
- [ ] 卸载延迟减少 200-500ms

**预期效果**: 减少卸载延迟 200-500ms

---

### 9. 音频合并 float32 优化

**当前问题**: `generation.py` 的 `merge_audio_segments()` 先转 float64 处理再转 float32 输出，增加内存带宽占用。

**涉及文件**:
- `bin/integrated_app/generation.py` — `merge_audio_segments()`（L126-L187）

**实施步骤**:

1. **将中间处理改为 float32**：
   ```python
   # 迁移前
   seg = seg.astype(np.float64)
   max_val = np.max(np.abs(seg))
   if max_val > 1.0:
       seg = seg / max_val

   # 迁移后
   seg = seg.astype(np.float32)
   max_val = np.max(np.abs(seg))
   if max_val > np.float32(1.0):
       seg = seg / max_val
   ```

2. **验证精度**：对同一组音频段，比较 float64 和 float32 输出的 SNR，确保 > 90dB（远超人耳可感知范围）

**验收标准**:
- [ ] 中间处理全部使用 float32
- [ ] 输出音频与 float64 版本 SNR > 90dB
- [ ] 合并 10 段音频的内存占用降低约 50%

**预期效果**: 减少内存带宽占用约 50%

---

### 10. SSE 心跳保活

**当前问题**: SSE 连接 600s 硬超时后断开，无重连引导，反向代理可能更早超时。

**涉及文件**:
- `bin/integrated_app/routes/sse.py` — `event_stream()`

**实施步骤**:

1. **添加心跳事件**：每 30 秒发送心跳：
   ```python
   last_heartbeat = time.time()
   # ... 在事件循环中 ...
   if time.time() - last_heartbeat >= 30:
       yield "event: heartbeat\ndata: {}\n\n"
       last_heartbeat = time.time()
   ```

2. **前端添加重连逻辑**：在 `static/js/` 中的 SSE 客户端代码添加：
   ```javascript
   const evtSource = new EventSource("/api/sse/events");
   evtSource.onerror = function() {
       setTimeout(() => {
           // 重新创建 EventSource
       }, 3000);
   };
   ```

3. **移除 600s 硬超时**：改为仅依赖客户端断开检测（`request.is_disconnected()`）

**验收标准**:
- [ ] 空闲 30s 后收到心跳事件
- [ ] 连接不再因超时断开
- [ ] 前端断开后自动重连

**预期效果**: 避免长时间空闲后需要手动刷新

---

### 11. 实现请求取消机制

**当前问题**: SSE 有 `cancelled` 事件类型，但生成路由中缺少实际的取消逻辑，用户无法中断长时间生成。

**涉及文件**:
- `bin/integrated_app/routes/generate.py` — 生成端点
- `bin/integrated_app/progress.py` — `ProgressManager`
- `bin/integrated_app/routes/model.py` — 可能的取消端点

**实施步骤**:

1. **添加取消端点**：
   ```python
   # routes/generate.py
   @router.post("/api/generate/cancel")
   async def cancel_generation():
       from ..model_manager import _progress_mgr
       if _progress_mgr:
           _progress_mgr.cancel()
           return {"status": "cancelling"}
       return {"status": "no_active_generation"}
   ```

2. **在生成函数中添加取消检查点**：在每段文本生成前检查取消标志：
   ```python
   # 在 streaming 生成循环中
   for i, segment in enumerate(segments):
       if _progress_mgr and _progress_mgr.is_cancelled():
           logger.info("生成已被用户取消")
           break
       audio = generate_fn(segment)
       # ...
   ```

3. **前端添加取消按钮**：在生成进度条旁添加"取消"按钮，调用 `/api/generate/cancel`

**验收标准**:
- [ ] 点击取消后 1s 内生成停止
- [ ] 已生成的音频段可保留
- [ ] 取消后模型状态正常（不残留锁）
- [ ] SSE 推送 `cancelled` 事件

**预期效果**: 用户可中断长时间生成，提升交互体验

---

### 12. Jinja2 auto_reload 环境控制

**当前问题**: `app_server.py:129` 设置 `templates.env.auto_reload = True`，生产环境会频繁 stat 模板文件。

**涉及文件**:
- `bin/integrated_app/app_server.py` — L129

**实施步骤**:

1. **根据环境变量控制**：
   ```python
   debug_mode = os.environ.get("TTS_DEBUG", "0") == "1"
   templates.env.auto_reload = debug_mode
   ```

2. **在 `start.bat` 中不设置 `TTS_DEBUG`**（生产默认关闭），开发时手动设置

**验收标准**:
- [ ] 默认 `auto_reload = False`
- [ ] 设置 `TTS_DEBUG=1` 后 `auto_reload = True`
- [ ] 生产环境无模板文件 stat 调用

**预期效果**: 生产环境减少文件系统 stat 调用

---

### 13. 实现引擎注册表

**当前问题**: `EngineRegistry` Protocol 已定义但未被实现，引擎名称硬编码在 `switch_engine()` 中（`if engine_name not in ("voxcpm2", "indextts2")`）。

**涉及文件**:
- `bin/integrated_app/engine_interface.py` — `EngineRegistry` Protocol（L153-L166）
- `bin/integrated_app/model_manager.py` — `switch_engine()`（L588-L700）
- `bin/integrated_app/model_registry.py` — `ENGINE_DISPLAY_NAMES`, `ENGINE_VRAM_REQUIREMENTS`
- `bin/integrated_app/engines/__init__.py`

**实施步骤**:

1. **实现 `InMemoryEngineRegistry`**：
   ```python
   # engine_interface.py 或新文件 engines/registry.py
   class InMemoryEngineRegistry:
       def __init__(self):
           self._engines: dict[str, type] = {}
           self._metadata: dict[str, dict] = {}

       def register(self, name: str, engine_class: type,
                     display_name: str = "", vram_requirement: float = 6.0) -> None:
           self._engines[name] = engine_class
           self._metadata[name] = {
               "display_name": display_name or name,
               "vram_requirement": vram_requirement,
           }

       def get(self, name: str) -> type | None:
           return self._engines.get(name)

       def list_engines(self) -> list[str]:
           return list(self._engines.keys())

       def get_display_name(self, name: str) -> str:
           return self._metadata.get(name, {}).get("display_name", name)

       def get_vram_requirement(self, name: str) -> float:
           return self._metadata.get(name, {}).get("vram_requirement", 6.0)
   ```

2. **在 `engines/__init__.py` 中自动注册**：
   ```python
   from .registry import engine_registry
   from .voxcpm2_engine import VoxCPM2Engine
   from .indextts2_engine import IndexTTS2Engine

   engine_registry.register("voxcpm2", VoxCPM2Engine,
                             display_name="VoxCPM2", vram_requirement=6.5)
   engine_registry.register("indextts2", IndexTTS2Engine,
                             display_name="IndexTTS 2.0", vram_requirement=6.0)
   ```

3. **重构 `switch_engine()`**：从注册表获取引擎类和元数据，替代硬编码：
   ```python
   engine_class = engine_registry.get(engine_name)
   if engine_class is None:
       raise EngineSwitchError(f"未注册的引擎: {engine_name}")
   needed_gb = engine_registry.get_vram_requirement(engine_name)
   ```

4. **迁移 `ENGINE_DISPLAY_NAMES` 和 `ENGINE_VRAM_REQUIREMENTS`**：从 `model_registry.py` 移到引擎注册表的元数据中

**验收标准**:
- [ ] `InMemoryEngineRegistry` 实现完整
- [ ] `switch_engine()` 不再硬编码引擎名称
- [ ] 新引擎只需实现 Protocol + 调用 `register()` 即可接入
- [ ] `ENGINE_DISPLAY_NAMES` 和 `ENGINE_VRAM_REQUIREMENTS` 从注册表获取

**预期效果**: 新引擎零核心代码修改，消除硬编码

---

### 14. 引擎热待机模式

**当前问题**: 切换引擎时必须先卸载当前引擎，无法利用大显存 GPU 同时保持两个引擎就绪。

**涉及文件**:
- `bin/integrated_app/model_manager.py` — `switch_engine()`, `unload_model()`
- `bin/integrated_app/model_registry.py` — `ModelRegistry`

**实施步骤**:

1. **添加热待机检测**：
   ```python
   def _can_hot_standby(target_engine: str) -> bool:
       """检查是否有足够显存同时加载两个引擎"""
       from .gpu_backend import GPUBackendManager, GPUBackend
       backend = GPUBackendManager.detect_backend()
       if backend == GPUBackend.CPU:
           return False
       mem_info = GPUBackendManager.get_memory_info()
       free_gb = mem_info[3] / (1024 ** 3)
       current_vram = ENGINE_VRAM_REQUIREMENTS.get(registry.current_engine, 0)
       target_vram = ENGINE_VRAM_REQUIREMENTS.get(target_engine, 0)
       return free_gb >= target_vram * 0.8  # 留 20% 余量
   ```

2. **修改 `switch_engine()`**：当热待机可行时，跳过卸载步骤：
   ```python
   if _can_hot_standby(engine_name):
       logger.info("[引擎切换] 显存充足，使用热待机模式")
       # 直接加载新引擎，不卸载旧引擎
   else:
       logger.info("[引擎切换] 显存不足，使用传统切换模式")
       unload_model()
   ```

3. **添加 `ModelRegistry.active_engine` 属性**：区分"已加载"和"活跃"状态

4. **添加显存监控**：热待机模式下持续监控显存，不足时自动卸载非活跃引擎

**验收标准**:
- [ ] 显存充足时引擎切换延迟 < 1s（vs 原来 30-60s）
- [ ] 显存不足时自动回退到传统切换模式
- [ ] 热待机模式下显存占用不超过 90%
- [ ] 非活跃引擎的推理请求被正确拒绝

**预期效果**: 引擎切换从 30-60s 降至 <1s（大显存 GPU 场景）

---

### 15. IndexTTS2Engine 显式实现 Protocol

**当前问题**: `IndexTTS2Engine` 接口兼容 `TTSEngine` Protocol，但没有显式声明实现，类型检查器无法在编译时发现接口不匹配。

**涉及文件**:
- `bin/integrated_app/engines/indextts2_engine.py`

**实施步骤**:

1. **添加缺失方法**：为 `IndexTTS2Engine` 添加 `is_ready()`, `load()`, `unload()` 方法（部分可能已存在但命名不同）

2. **显式声明实现**：
   ```python
   class IndexTTS2Engine:
       """IndexTTS 2.0 TTS engine implementation."""

       def is_ready(self) -> bool:
           return self._model is not None

       def load(self) -> None:
           # 现有加载逻辑
           ...

       def unload(self) -> None:
           # 现有卸载逻辑
           ...
   ```

3. **添加运行时检查**：在引擎注册时验证 Protocol 兼容性：
   ```python
   def register(self, name: str, engine_class: type) -> None:
       if not isinstance(engine_class, TTSEngine):
           raise TypeError(f"{engine_class} does not implement TTSEngine Protocol")
       self._engines[name] = engine_class
   ```

**验收标准**:
- [ ] `IndexTTS2Engine` 显式满足 `TTSEngine` Protocol
- [ ] `isinstance(IndexTTS2Engine(), TTSEngine)` 返回 `True`
- [ ] mypy/pyright 类型检查通过

**预期效果**: 编译时类型检查可发现接口不匹配

---

### 16. tts_error_handler 支持 async

**当前问题**: `@tts_error_handler` 装饰器仅包装同步函数，而 FastAPI 路由多为 async。

**涉及文件**:
- `bin/integrated_app/exceptions.py` — `tts_error_handler()`（L44-L53）

**实施步骤**:

1. **扩展装饰器支持 async**：
   ```python
   import asyncio
   import inspect

   def tts_error_handler(func):
       @functools.wraps(func)
       def sync_wrapper(*args, **kwargs):
           try:
               return func(*args, **kwargs)
           except TTSError:
               raise
           except Exception as e:
               raise GenerationError(f"未知错误: {type(e).__name__}: {e}") from e

       @functools.wraps(func)
       async def async_wrapper(*args, **kwargs):
           try:
               return await func(*args, **kwargs)
           except TTSError:
               raise
           except Exception as e:
               raise GenerationError(f"未知错误: {type(e).__name__}: {e}") from e

       if asyncio.iscoroutinefunction(func):
           return async_wrapper
       return sync_wrapper
   ```

2. **在 async 路由上应用装饰器**：搜索所有 async 路由函数，添加 `@tts_error_handler`

**验收标准**:
- [ ] `@tts_error_handler` 同时支持 sync 和 async 函数
- [ ] async 路由中的非 TTSError 异常被包装为 GenerationError
- [ ] 现有同步装饰器行为不变

**预期效果**: async 路由也能获得统一错误处理

---

### 17. 异常处理不吞异常

**当前问题**: `system.py` 中部分 `except` 块使用 `pass` 吞掉异常，导致静默失败。

**涉及文件**:
- `bin/integrated_app/routes/system.py`

**实施步骤**:

1. **搜索所有 `except.*pass` 模式**：在 `system.py` 中查找

2. **替换为 `logger.debug()`**：
   ```python
   # 迁移前
   except Exception:
       pass

   # 迁移后
   except Exception as e:
       logger.debug(f"Non-critical error in {func.__name__}: {e}")
   ```

3. **评估是否应升级为 warning**：对可能影响功能的异常，使用 `logger.warning()`

**验收标准**:
- [ ] 无 `except.*pass` 模式（ruff 规则 E722 配合）
- [ ] 所有异常至少有 debug 级别日志

**预期效果**: 提高问题排查效率

---

### 18. 后台线程 request_id

**当前问题**: 后台线程（模型加载、预热等）的日志没有 request_id，无法区分来源。

**涉及文件**:
- `bin/integrated_app/middleware/request_id.py`
- `bin/integrated_app/model_manager.py` — 后台线程函数

**实施步骤**:

1. **添加后台线程 request_id 设置**：
   ```python
   # 在每个后台线程入口
   from .middleware.request_id import set_request_id

   def _load_in_background():
       set_request_id(f"bg-{threading.current_thread().name}")
       # ... 原有逻辑 ...
   ```

2. **修改 `RequestIDLogFilter`**：支持从线程局部存储读取 request_id

**验收标准**:
- [ ] 后台线程日志包含 `request_id` 字段（如 `bg-model-startup-load`）
- [ ] 请求线程日志不受影响

**预期效果**: 后台任务日志可区分来源

---

### 19. API 文档补充

**当前问题**: API 文档依赖 FastAPI 自动生成，缺少独立的 API 使用指南和请求/响应示例。

**涉及文件**:
- `bin/integrated_app/routes/*.py` — 各路由端点

**实施步骤**:

1. **为主要端点添加 `summary` 和 `description`**：在路由装饰器中补充
2. **添加 `response_model`**：为关键端点定义 Pydantic 响应模型
3. **添加 `examples`**：在请求体模型中添加示例数据

**验收标准**:
- [ ] `/docs` 页面所有端点有中文描述
- [ ] 主要端点有请求/响应示例
- [ ] 响应模型定义完整

**预期效果**: 新开发者/API 用户可快速上手

---

### 20. 文档时效性标注

**当前问题**: `docs/` 下的技术审计报告可能过时。

**涉及文件**:
- `docs/*.md`

**实施步骤**:

1. **为每个文档添加最后更新日期**：在文档头部添加 `> 最后更新: YYYY-MM-DD`
2. **在 CI 中添加文档链接检查**：使用 `markdown-link-check` 验证内部链接

**验收标准**:
- [ ] 所有文档有最后更新日期
- [ ] CI 检查文档内部链接有效性

**预期效果**: 避免误导性文档

---

### 21. 测试覆盖率提升

**当前问题**: 测试覆盖率仅 40%，核心路由和引擎逻辑缺少测试。

**涉及文件**:
- `tests/` 目录

**实施步骤**:

1. **优先补充以下测试**：

   a. **引擎切换回滚测试** (`tests/test_engine_switch.py`)：
   ```python
   def test_switch_engine_rollback_on_load_failure():
       """切换失败时应回滚到之前的引擎状态"""
   def test_switch_engine_rejects_unknown_engine():
       """不支持的引擎名称应抛出 EngineSwitchError"""
   def test_switch_engine_vram_check():
       """显存不足时应抛出 InsufficientVRAMError"""
   ```

   b. **SSE 事件流测试** (`tests/test_sse.py`)：
   ```python
   def test_sse_emits_progress_event():
   def test_sse_emits_status_event():
   def test_sse_disconnect_detection():
   def test_sse_timeout():
   ```

   c. **缓存淘汰测试** (`tests/test_cache.py`)：
   ```python
   def test_lru_eviction_order():
   def test_adaptive_capacity_gpu_high():
   def test_adaptive_capacity_gpu_low():
   def test_cache_stats():
   ```

   d. **并发请求测试** (`tests/test_concurrency.py`)：
   ```python
   def test_concurrent_generate_requests():
   def test_model_lock_during_switch():
   ```

2. **更新 `pyproject.toml`**：将 `fail_under` 从 40 提升到 60

**验收标准**:
- [ ] 覆盖率 ≥ 60%
- [ ] 上述 4 类测试文件创建完成
- [ ] CI 中 `fail_under = 60` 通过

**预期效果**: 减少回归风险，提高代码质量信心

---

### 22. 集成测试纳入 CI

**当前问题**: `bin/test_integration.py` 和 `bin/test_system_enhancements.py` 在 bin 目录而非 tests/，未纳入 CI。

**涉及文件**:
- `bin/test_integration.py`
- `bin/test_system_enhancements.py`
- `.github/workflows/ci.yml`

**实施步骤**:

1. **迁移测试文件**：将 `bin/test_*.py` 移到 `tests/` 目录
2. **添加 pytest marker**：
   ```python
   import pytest
   pytestmark = pytest.mark.integration
   ```
3. **更新 CI 配置**：
   ```yaml
   - name: Run integration tests
     if: github.event_name == 'push' && github.ref == 'refs/heads/main'
     run: pytest tests/ -m integration --timeout=300
   ```
4. **在 `pyproject.toml` 中注册 marker**：
   ```toml
   [tool.pytest.ini_options]
   markers = ["integration: integration tests requiring GPU"]
   ```

**验收标准**:
- [ ] 集成测试在 `tests/` 目录
- [ ] CI main 分支推送时运行集成测试
- [ ] PR 时仅运行单元测试（跳过集成测试）

**预期效果**: 端到端功能验证

---

## 🟢 低优先级（按需实施）

---

### 23. 性能基准测试

**实施步骤**:

1. **创建 `tests/benchmarks/` 目录**
2. **定义基准场景**：
   - 短文本生成（< 50 字）
   - 中等文本生成（200 字）
   - 长文本流式生成（1000+ 字，10+ 段）
   - 引擎切换延迟
   - 缓存命中/未命中延迟
3. **记录 P50/P95/P99 延迟**：使用 `pytest-benchmark`
4. **CI 中可选运行**：添加 `pytest -m benchmark` 命令

**验收标准**:
- [ ] 5 个基准场景定义完成
- [ ] 可通过 `pytest -m benchmark` 运行
- [ ] 输出 JSON 格式基准数据

**预期效果**: 性能回归可量化检测

---

### 24. 跨平台部署脚本

**实施步骤**:

1. **创建 `install.sh`**：等效于 `install.bat` 的 Bash 脚本
2. **创建 `start.sh`**：等效于 `start.bat` 的 Bash 脚本
3. **使用 Python 脚本统一**：将核心逻辑提取到 `scripts/setup.py`，bat/sh 只做薄包装

**验收标准**:
- [ ] `install.sh` 在 Ubuntu 22.04 上可运行
- [ ] `start.sh` 可启动服务

**预期效果**: 支持 Linux/macOS 部署

---

### 25. Docker 容器化

**实施步骤**:

1. **创建多阶段 Dockerfile**：
   ```dockerfile
   FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04 AS base
   # 安装 Python 3.10 + 系统依赖
   # 安装 Python 依赖

   FROM base AS app
   COPY . /app
   WORKDIR /app
   EXPOSE 7869
   CMD ["python", "-m", "integrated_app.cli"]
   ```

2. **创建 `docker-compose.yml`**：
   ```yaml
   services:
     tts:
       build: .
       ports: ["7869:7869"]
       deploy:
         resources:
           reservations:
             devices:
               - driver: nvidia
                 count: 1
                 capabilities: [gpu]
   ```

3. **添加 `.dockerignore`**

**验收标准**:
- [ ] `docker compose up` 可启动服务
- [ ] GPU 直通正常工作
- [ ] 模型文件通过 volume 挂载

**预期效果**: 一键容器化部署

---

### 26. 模型自动下载提示

**实施步骤**:

1. **在 `check_models_available()` 中增强**：检测到模型缺失时，返回下载命令提示
2. **在启动页面添加下载按钮**：`download_guide.html` 中添加一键下载按钮
3. **后台下载**：添加 `/api/models/download` 端点，触发后台下载脚本

**验收标准**:
- [ ] 首次启动时自动提示模型缺失
- [ ] 提供一键下载选项

**预期效果**: 降低新用户上手门槛

---

### 27. 引擎名称枚举化

**当前问题**: `"voxcpm2"` 和 `"indextts2"` 在多处硬编码。

**涉及文件**:
- `bin/integrated_app/model_manager.py` — `switch_engine()`（L616）
- `bin/integrated_app/model_registry.py` — `ENGINE_DISPLAY_NAMES`, `ENGINE_VRAM_REQUIREMENTS`
- `bin/integrated_app/config.py` — `load_voxcpm2()`/`load_indextts2()` 函数名

**实施步骤**:

1. **创建引擎名称枚举**：
   ```python
   # model_registry.py 或新文件 engines/names.py
   from enum import Enum

   class EngineName(str, Enum):
       VOXCPM2 = "voxcpm2"
       INDEXTTS2 = "indextts2"
   ```

2. **替换所有硬编码字符串**：
   ```python
   # 迁移前
   if engine_name not in ("voxcpm2", "indextts2"):
   # 迁移后
   if engine_name not in EngineName._value2member_map_:
   ```

3. **配置文件驱动引擎列表**：在 `config.yaml` 中定义可用引擎

**验收标准**:
- [ ] 项目中无引擎名称硬编码字符串（除枚举定义外）
- [ ] `switch_engine()` 使用枚举验证
- [ ] 新增引擎只需扩展枚举

**预期效果**: 消除硬编码，提高扩展性

---

### 28. i18n 键命名空间

**当前问题**: 500+ 扁平翻译键，新功能添加容易键名冲突。

**涉及文件**:
- `bin/integrated_app/i18n.py`（或外部化后的 `locales/*.json`）

**实施步骤**:

1. **定义命名空间前缀规范**：
   ```
   indextts2.clone.desc
   indextts2.clone.btn_start
   voxcpm.design.title
   settings.lora.title
   common.loading
   common.error
   ```

2. **创建迁移脚本**：`scripts/migrate_i18n_keys.py` 自动添加前缀

3. **更新 `t()` 函数**：支持点分路径查找：
   ```python
   def t(key: str, lang: str = None) -> str:
       translations = _load_translations(lang or current_lang)
       parts = key.split(".")
       result = translations
       for part in parts:
           result = result.get(part, {})
       return result if isinstance(result, str) else key
   ```

4. **更新所有模板中的 `t()` 调用**

**验收标准**:
- [ ] 所有翻译键使用命名空间前缀
- [ ] 无键名冲突
- [ ] `t("indextts2.clone.desc")` 返回正确翻译

**预期效果**: 避免键名冲突，便于按模块加载

---

### 29. 路由自动发现

**当前问题**: `app_server.py` 中 9 个 router 手动 import + include。

**涉及文件**:
- `bin/integrated_app/app_server.py` — L166-L177

**实施步骤**:

1. **实现自动发现**：
   ```python
   import importlib
   import pkgutil
   from . import routes

   def _auto_discover_routers():
       routers = []
       for importer, modname, ispkg in pkgutil.iter_modules(routes.__path__):
           mod = importlib.import_module(f".routes.{modname}", package="integrated_app")
           if hasattr(mod, "router"):
               routers.append(mod.router)
           # 处理子包（如 routes/system/）
           if ispkg:
               submod = importlib.import_module(f".routes.{modname}", package="integrated_app")
               if hasattr(submod, "router"):
                   routers.append(submod.router)
       return routers
   ```

2. **替换手动注册**：
   ```python
   # 迁移前
   from .routes import audio, generate, model, pages, persona, sse, system, tabs
   app.include_router(audio.router)
   # ...

   # 迁移后
   for router in _auto_discover_routers():
       app.include_router(router)
   ```

3. **保留显式注册选项**：通过环境变量 `TTS_AUTO_ROUTES=0` 可回退到手动模式

**验收标准**:
- [ ] 新路由文件只需创建并定义 `router`，无需修改 `app_server.py`
- [ ] 所有现有端点正常工作
- [ ] 可通过环境变量禁用自动发现

**预期效果**: 减少手动注册，新路由零配置接入

---

## 附录：实施依赖关系

```
#27 引擎名称枚举化 ──→ #13 实现引擎注册表 ──→ #14 引擎热待机模式
                                              ──→ #15 IndexTTS2Engine 显式实现 Protocol

#3 i18n 翻译数据外部化 ──→ #28 i18n 键命名空间

#5 SSE 轮询优化 ──→ #10 SSE 心跳保活

#1 消除全局变量 ──→ #13 实现引擎注册表

#21 测试覆盖率提升 ──→ #22 集成测试纳入 CI ──→ #23 性能基准测试

#4 routes/system.py 拆分 ──→ #29 路由自动发现
```

## 附录：风险矩阵

| 改进项 | 影响范围 | 破坏性风险 | 测试难度 |
|--------|---------|-----------|---------|
| #1 消除全局变量 | 全局 | 中 | 低 |
| #2 config.py 延迟初始化 | 全局 | 中 | 中 |
| #5 SSE 轮询优化 | 前端+后端 | 低 | 中 |
| #11 请求取消机制 | 生成流程 | 中 | 高 |
| #13 引擎注册表 | 核心架构 | 中 | 中 |
| #14 引擎热待机 | 核心架构 | 高 | 高 |
| #25 Docker 容器化 | 部署 | 低 | 低 |
