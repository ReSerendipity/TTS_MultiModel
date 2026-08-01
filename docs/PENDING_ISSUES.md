# TTS_MultiModel 待解决问题清单

> 本文档汇总项目当前已知的所有 **未解决问题、风险点、技术债与待改进项**。
>
> **最后更新**：2026-08-01
> **关联分支**：master
> **最近一次整合工作**：删除 GPT-SoVITS 引擎，保留 VoxCPM2 / IndexTTS2 / dots.tts 三引擎架构（ADR-0001）

---

## 0. 阅读说明

- **优先级图例**：
  - 🔴 **[P0]** 阻塞型 —— 不解决将导致关键路径失败或运行时报错
  - 🟠 **[P1]** 高优 —— 影响核心功能、生产稳定性或 CI 通过率
  - 🟡 **[P2]** 中优 —— 影响开发体验、非核心路径或长期可维护性
  - 🟢 **[P3]** 低优 —— 改进项、Nice-to-have 或文档完备性
- 每条问题提供：**现状描述 / 影响 / 触发条件 / 建议方向 / 相关文件**
- "已规划但未实施" 与 "新发现" 两类明确标注

---

## 1. 编译与部署层

### 🔴 [P0] `tn` stub 包是 out-of-tree 注入（部署风险）

**现状**：`need read.txt` 第 60-63 行记录：在 `site-packages/tn/` 手工注入两个文件
- `tn/chinese/normalizer.py`：`Normalizer.normalize(text)` 仅 strip 空白、不做数字/日期归一化
- `tn/english/normalizer.py`：同上

**影响**：
- 这些文件 **不在 git 跟踪中** —— 任何一次 `pip install --force-reinstall`、换机器、克隆新环境都会丢失
- 丢失后 `import dots_tts` 直接 ModuleNotFoundError
- 部署文档（README / install.sh / install.bat）**没有**说明此步骤

**触发条件**：
- 重装 Python 环境
- 在新机器上部署
- 升级 `pip` 后某些包可能被自动重装覆盖

**建议方向**：
- 方案 A：把 `tn` stub 迁回仓库 `bin/integrated_app/vendor/tn/`，通过 `pyproject.toml [tool.setuptools.packages.find]` 包含
- 方案 B：在 `install.bat` / `install.sh` 增加步骤 "向 site-packages 复制 tn 降级包"
- 方案 C：上游 dots.tts 添加 try/except，pynini 缺失时自动降级（联系维护者）

**相关文件**：`bin/integrated_app/vendor/tn/`

---

### 🔴 [P0] `opencc-python-reimplemented` 替代品同样 out-of-tree

**现状**：`need read.txt` 第 76 行记录：用 `opencc-python-reimplemented`（纯 Python）替换 opencc 源码编译。但替代品是手动 `pip install` 到 site-packages，**未列入 `requirements.txt`**。

**影响**：
- 与 tn stub 同：换环境即丢失
- ~~GPT-SoVITS 繁简转换静默 fallback~~（已解决：GPT-SoVITS 引擎已删除）

**建议方向**：
- 在 `pyproject.toml` 的 `dependencies` 显式声明 `opencc-python-reimplemented>=X.Y`
- 或写 `install.bat` 脚本里强制安装

**相关文件**：`pyproject.toml`

---

### ✅ [已解决] `pyopenjtalk` 整套跳过，日语 TTS 不可用

**状态**：已解决 — GPT-SoVITS 引擎已删除（ADR-0001），此问题不再适用。

---

### 🟡 [P2] 编译失败 fallback 文档缺失

**现状**：5 个编译失败包（pynini、WeTextProcessing、jieba_fast、opencc、pyopenjtalk系列）的**完整环境适配步骤**仅在 `need read.txt`（私人对话总结），没有进入项目正式文档。

**影响**：
- 新开发者无法复现完整环境
- 升级 Python/pip 时容易踩同样的坑

**建议方向**：在 `docs/` 下写 `docs/INSTALLATION_FALLBACKS.md`，结构化记录每个 fallback 的触发条件与解决方案。

---

## 2. 版本兼容性

### ✅ [已解决] `pyproject.toml` 版本策略与原文档决策不一致

**状态**：已解决 — GPT-SoVITS 引擎已删除（ADR-0001），版本约束不再需要兼容 GPT-SoVITS。当前版本策略以满足 dots.tts 为准。

---

### 🟠 [P1] `dotstts_engine.load()` 没有 try/except 兜底

**现状**：`need read.txt` 第 110 行规划的回滚路径 "在 `dotstts_engine.py` 的 `load()` 中加 `try/except` 包装 `DotsTtsRuntime.from_pretrained`"，**没有实施**。

**影响**：
- 一旦 dots.tts 在当前 transformers/numpy/pydantic 上崩溃，会直接抛出未捕获异常
- 用户看到的是 500 Internal Server Error，而不是友好的 "依赖不兼容，请尝试 venv 模式"

**建议方向**：
```python
# bin/integrated_app/engines/dotstts_engine.py
def load(self, model_root: Path, **kwargs):
    try:
        self._runtime = DotsTtsRuntime.from_pretrained(...)
    except (RuntimeError, AttributeError, TypeError) as e:
        raise ModelLoadError(
            "dots.tts 依赖兼容性错误。"
            "建议在 venv 中安装 dots.tts 及其依赖。"
            f"原始错误: {e}"
        ) from e
```

**相关文件**：`bin/integrated_app/engines/dotstts_engine.py`

---

### 🟡 [P2] `inflect` 不安装但未文档化

**现状**：`need read.txt` 第 108 行明确 "inflect 直接丢弃（中文场景不需要）"。但**没有**在 `docs/` 中说明此决策，未来开发者会困惑 "为什么 inflect 没装？是不是 bug？"

**建议方向**：在 `docs/OPTIMIZATION_IMPLEMENTATION_GUIDE.md` 或新建 `docs/DEPENDENCIES_DECISIONS.md` 中加一段说明。

---

## 3. 测试与覆盖率

### 🔴 [P0] CI `--cov-fail-under=50` 必然失败（覆盖门槛远超现状）

**现状**：
- `AGENTS.md` 第 53 行记录 CI 命令带 `--cov-fail-under=50`
- 当前覆盖率仅 **22.91%**（dotstts 47%）
- 因此 CI 在 coverage gate 处必然挂掉

**影响**：
- 任何 PR 都会被 CI 拒绝（即便代码完全正确）
- 集成工作的提交（4 个 commit）若推到远端会触发红 X
- 阻塞下游开发的硬门禁

**建议方向（任选其一）**：
- A. **降低门槛**：将 `--cov-fail-under` 调到 `20`（基于当前 22.91% 留余量）
- B. **增加覆盖**：补齐 0% 模块的测试（见 P1）
- C. **分层门禁**：覆盖门槛作为 warning 不作为 failure，配合 `--cov-fail-under=0`

**相关文件**：`AGENTS.md:53`、`.github/workflows/ci.yml`

---

### 🟠 [P1] 关键模块 0% 覆盖率（技术债）

**现状**：从对话历史报告得知，以下模块覆盖率 0%：
- `bin/integrated_app/service_layer.py`
- `bin/integrated_app/signal_handlers.py`
- `bin/integrated_app/task_queue.py`
- `bin/integrated_app/training/*`（训练子模块全部）
- `bin/integrated_app/text_frontend.py`（16%）

**影响**：
- 这些模块重构时无回归保护
- 训练子模块未测试意味着 LoRA 训练流程可能 silent fail

**建议方向**：
- 优先覆盖 `service_layer.py` 与 `signal_handlers.py`（影响请求生命周期）
- `training/*` 可以用 `pytest -m "integration"` 标记隔离，集成测试环境单独跑

**相关文件**：`bin/integrated_app/service_layer.py` 等

---

### 🟡 [P2] 真实模型权重加载端到端测试未做

**现状**：CI 离线 CPU 环境不能加载 14GB 模型权重，所有引擎测试覆盖的是"非加载路径"（错误处理、元数据、generate_streaming 模拟）。

**影响**：
- 实际生成路径的兼容性（小版本号差异、CUDA 路径分支、显卡驱动）完全靠人工 smoke test
- 上线新显卡 / 新 transformers 版本时无自动化兜底

**建议方向**：
- 短期：写 `tests/integration/test_engine_load_gpu.py`，标 `pytest.mark.integration`
- 触发条件：开发者本机手动跑 `pytest -m integration`
- 长期：CI matrix 增加 "self-hosted GPU runner" 任务

---

### 🟡 [P2] Playwright 真实浏览器 UI 测试未做

**现状**：本轮 "任务 6：浏览器 UI 端到端验证" 用 `urllib.request` 跑 HTTP 层通过，**未做**：
- 实际页面渲染截图
- 折叠面板 JS 交互（点击 `toggleCollapse` 是否展开）
- 真实 `<audio>` 元素播放

**影响**：
- Tab UI 改版后无视觉回归保护
- 折叠面板交互失效时（CSS `collapse-body` 选择器变更等）CI 不会报错

**建议方向**：在 `tests/e2e/` 下增加 `test_tab_collapse_interaction.py`，需要浏览器环境时跳过。

---

## 4. 引擎集成层

### 🟡 [P2] 引擎切换期间 VRAM 释放彻底性未验证

**现状**：集成 dots.tts 后，`model_registry` 中多个引擎注册。切换时需要 `unload` → `load`，但 VRAM 释放是否完整**未做严格回归测试**。

**影响**：
- 连续切换可能 VRAM 累积膨胀
- 触发"显存占用超过 90% 熔断"硬约束（项目硬约束 #2）

**建议方向**：
- 在 `tests/test_engine_switch.py` 增加 "VRAM 切换稳定性" 用例，配合 `pytest.mark.gpu`
- 用 `torch.cuda.memory_allocated()` 在切换前后断言

**相关文件**：`bin/integrated_app/model_manager.py`、`tests/test_engine_switch.py`

---

### 🟡 [P2] SSE 事件流在长文本生成时断连风险

**现状**：长文本（>500 字符）的 generate 会经过多次 SSE 事件推送。客户端（SSE EventSource）默认有 6 连接上限，且反向代理（nginx/cloudflare）有 60s/100s timeout。

**影响**：
- 网络层断连后用户看到的是 "卡死"，需要刷新
- 重连后丢失中间进度

**建议方向**：
- 在 `routes/sse.py` 加 `retry: 1000` 心跳
- 前端 EventSource 增加断线重连
- 文档化反向代理 timeout 调整建议

**相关文件**：`bin/integrated_app/routes/sse.py`

---

### 🟢 [P3] 移动端 / 小屏幕响应式未覆盖

**现状**：折叠面板使用 `class="form-row" + "form-col"` 网格布局，未做移动端断点适配。

**影响**：手机访问 WebUI 时折叠面板内字段挤在一行。

**建议方向**：在 `static/css/main.css` 增加 `@media (max-width: 600px) { .form-row { flex-direction: column; } }`。

---

### 🟢 [P3] `examples/` 缺 dotstts 使用脚本

**现状**：`examples/` 仅有 3 个 .py + 1 个 .jsonl，没有针对新引擎的：
- 直接调用 `TTSEngine.generate_voice_clone()` 的脚本
- 批量推理脚本（多 persona）

**建议方向**：
- `examples/dotstts_clone_quick.py`
- `examples/batch_clone_all_personas.py`（遍历 personas/ 跑克隆）

---

### 🟢 [P3] 多引擎并发加载的设计权衡

**现状**：项目硬约束 #4 规定 "单 Worker 串行"。两条现状：
- 模型注册中心支持 `current_engine` 单槽
- 但注册中心底层数据结构支持多引擎共存

**影响**：
- 当前无并发需求，但要保留未来扩展（如文件级 LoRA 切换）的设计余地

**建议方向**：在 `docs/PROJECT_ARCHITECTURE.md` 写一段 "为什么单 Worker，未来如何打开"。

---

## 5. UI / UX 层

### ✅ [已解决] GPT-SoVITS 折叠面板字段冗余度

**状态**：已解决 — GPT-SoVITS 引擎已删除（ADR-0001），相关模板文件同步移除。

---

### 🟢 [P3] 折叠面板默认展开/折叠状态

**现状**：`voice_clone.html` 等所有折叠面板初始是折叠的。新手用户可能不知道有这个面板。

**建议方向**：
- 主表单每行右侧加 "高级设置" badge，提示存在折叠内容
- 或第一次访问时默认展开，教育完成后下次记住

---

### ✅ [已解决] `ja.json` / `ko.json` i18n 缺失

**状态**：已解决 — GPT-SoVITS 相关 i18n 键已随引擎删除一并移除。dots.tts 的 ja/ko 键已补全（commit `b87faac`）。

---

## 6. 文档与监控

### 🟡 [P2] `need read.txt` 与实际代码决策差异需正式归档

**现状**：`need read.txt` 标记为 "私人对话总结"，但里面关于版本策略、回滚路径的核心决策已经在仓库代码中被反转。

**影响**：
- 未来回顾对话时无从判断哪个是真实状态
- 项目权威文档缺乏这条决策链

**建议方向**：
- 把 `need read.txt` 内容提炼为 `docs/INTEGRATION_DECISIONS.md`（正式文档）
- `need read.txt` 可保留作为开发过程参考

---

### 🟢 [P3] 模型权重下载完整性校验

**现状**：dots.tts 4.9GB 权重通过 `download_*.py` / `download_*.bat` 脚本下载，但**没有** SHA256 校验或 `expect.md5` 文件。

**影响**：
- 下载中断或部分损坏时静默运行，可能产生低质量音频
- 跨网络环境重新同步权重时不可靠

**建议方向**：在 `scripts/` 增加 `weights_checksums.txt` 与 `verify_weights.py`。

---

### 🟢 [P3] 训练模块文档化

**现状**：`bin/integrated_app/training/` 子模块完整实现了 LoRA 训练，但在 README 中**没有**对应的使用说明。

**建议方向**：写 `docs/TRAINING_GUIDE.md`：
- 数据准备格式（HFVoxCPMDataset）
- `accelerator.py` 配置示例
- 训练 → 导出 → 引擎加载流程图

---

### ✅ [已解决] 模型权重路径与 `config.yaml` 漂移检测

**状态**：已解决 — GPT-SoVITS 引擎已删除（ADR-0001），`config.yaml` 中 `models.gptsovits.root` 配置段同步移除。

**建议方向**：增加 `scripts/check_models_paths.py`，启动前校验所有引用路径存在。

---

## 7. 安全与合规

### 🟡 [P2] CSRF + API Auth 双层防护的可配置粒度

**现状**：
- CSRF middleware 默认启用（Double-Submit Cookie）
- API Auth middleware 通过 `config.yaml api_auth.enabled` 可选启用 Bearer Token
- 但两者同时启用时（如 auth=True + CSRF=on），文档未说明交互行为

**建议方向**：在 `docs/SECURITY.md` 加一段 "CSRF 与 API Auth 协同工作"。

---

### 🟢 [P3] 上传参考音频的元数据清理

**现状**：用户上传的 `ref_audio.wav` 直接保存到 `output_dir`，文件名未做重命名。

**影响**：
- 路径穿越攻击窗口（已有 middleware 防护但可加固）
- 长文件名 / 特殊字符文件系统兼容问题

**建议方向**：上传后用 `uuid.uuid4().hex + .wav` 规范化。

---

## 8. 已知性能瓶颈（非阻塞）

### 🟢 [P3] FTS5 中文分词的覆盖

**现状**：OPTIMIZATION 实施的 history_db FTS5 用 `unicode61` 分词器。中文不分词，按字符拆分。

**影响**：搜索 "你好世界" 会匹配 "你" 和 "好" 任意出现，不是连续匹配。

**建议方向**：改用 `unicode61 remove_diacritics 2` + `tokenchars='\-'`，或 jieba 分词后插入 FTS。

---

### 🟢 [P3] audio_processing 流式 float32 在长 mix 上的边界

**现状**：音频内存优化将 .wav 整文件读取改为 float32 流式。在 10 分钟以上的长 mix 时，浮点累积误差可能引入 ~0.01 响度偏差。

**建议方向**：增加 `numpy.linalg.norm(diff)` 自动断言阈值，CI 中监测精度漂移。

---

## 附录 A · 优先级分布统计

| 优先级 | 数量 | 说明 |
|--------|------|------|
| 🔴 P0 | 2 | 必须解决，否则部署/CI 失败（2 项已随 GPT-SoVITS 删除解决） |
| 🟠 P1 | 3 | 建议下一个迭代冲刺解决 |
| 🟡 P2 | 8 | 持续改进，逐步覆盖 |
| 🟢 P3 | 8 | 长期 backlog（3 项已随 GPT-SoVITS 删除解决） |

**总和**：21 条待解决问题（5 项已随 GPT-SoVITS 引擎删除一并解决）。

---

## 附录 B · 相关文档交叉引用

| 文档 | 描述 |
|------|------|
| [`need read.txt`](../need read.txt) | 私人对话总结，记录 5 大编译失败 + 4 个版本冲突的来龙去脉 |
| [`AGENTS.md`](../AGENTS.md) | 项目代理工作规范 |
| [`docs/ISSUE_ANALYSIS.md`](ISSUE_ANALYSIS.md) | 已修复问题归档（4 个本地化/差异化问题） |
| [`docs/PROJECT_ARCHITECTURE.md`](PROJECT_ARCHITECTURE.md) | 项目架构全景 |
| [`docs/SPEC_optimization.md`](SPEC_optimization.md) | 性能优化规格 |
| [`docs/INDEXTTS2_INTEGRATION_GUIDE.md`](INDEXTTS2_INTEGRATION_GUIDE.md) | IndexTTS2 集成参考 |
| [`docs/GPTSOVITS_DOTSTTS_INTEGRATION_GUIDE.md`](GPTSOVITS_DOTSTTS_INTEGRATION_GUIDE.md) | 本轮 GPT-SoVITS+dots.tts 集成步骤 |
| [`docs/OPTIMIZATION_IMPLEMENTATION_GUIDE.md`](OPTIMIZATION_IMPLEMENTATION_GUIDE.md) | OPTIMIZATION 三项性能优化实施 |

---

## 附录 C · 解决记录模板（新发现问题时追加）

```markdown
### [P?] 简短标题

**现状**：...（一句话描述）

**影响**：...（具体表现）

**触发条件**：...（哪些场景会暴露）

**建议方向**：...（可选方案 A / B / C）

**相关文件**：...（代码位置）
```

---

> **维护说明**：每解决一条问题，建议在提交信息中引用编号（如 `fixes #P0-1`），并在本文件勾掉对应条目。
