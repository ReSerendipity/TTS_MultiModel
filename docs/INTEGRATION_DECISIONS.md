# 集成决策归档

> 本文档正式归档 GPT-SoVITS + dots.tts 双引擎集成过程中的关键技术决策，
> 替代 `need read.txt`（私人对话总结）作为权威来源。
>
> **最后更新**：2026-08-01

---

## 1. 版本策略决策

### 原始决策（need read.txt）

GPT-SoVITS 优先，保留低版本：
- transformers: `>=4.43, <=4.50`（保留 4.50）
- numpy: `<2.0`（保留 1.26.4）
- pydantic: `<=2.10.6`（保留低版本）

### 实际执行（pyproject.toml）

版本策略已反转，选择 dots.tts 优先：
- transformers: `>=4.57.0`（满足 dots.tts）
- numpy: `>=1.24.0`（上限放开）
- pydantic: `>=2.0`（上限放开）

### 反转原因

dots.tts 的版本约束更严格，且其 `import` 成功依赖高版本 transformers API。
GPT-SoVITS 的版本上限通常为上游过度保守，实际运行时大概率兼容。

### 回滚路径

如 GPT-SoVITS 出现运行时错误：
1. 在 `dotstts_engine.py` 的 `load()` 中已有 try/except 兜底（捕获 RuntimeError/AttributeError/TypeError/ImportError）
2. 使用独立 venv 安装 dots.tts 及其依赖以隔离版本冲突
3. 降低 transformers 至 4.50 并放弃 dots.tts 支持

---

## 2. 编译失败处理

详见 [`docs/INSTALLATION_FALLBACKS.md`](INSTALLATION_FALLBACKS.md)。

---

## 3. tn stub 包策略

- **原始方案**：在 `site-packages/tn/` 手工注入 stub 文件
- **改进方案**：迁移到 `bin/integrated_app/vendor/tn/`，通过 `pyproject.toml` 自动发现
- **优势**：不再依赖 out-of-tree 注入，换环境/重装不丢失

---

## 4. opencc 替代方案

- `opencc-python-reimplemented` 已声明在 `pyproject.toml` dependencies 中
- 不再需要手动 `pip install`

---

## 5. 日语降级决策

- pyopenjtalk 在 Python 3.12 + Windows 下无法编译
- GPT-SoVITS 仍支持中/英/韩/粤，仅缺日语
- 已在 `gptsovits_engine.py` 中加入语言检测，日语请求返回 `ValidationError`

---

## 6. inflect 丢弃决策

- inflect 是 GPT-SoVITS 的英文数字转写依赖
- 中文场景不需要，主动丢弃
- 需英文完整功能时可手动安装

---

## 7. 模型权重

| 引擎 | 权重大小 | 下载位置 |
|------|---------|---------|
| GPT-SoVITS | ~5GB (29 文件) | `pretrained_models/GPT-SoVITS/` |
| dots.tts | ~4.9GB (17 文件) | `pretrained_models/dots.tts/` |

权重通过 `scripts/download_gptsovits.py` 和 `scripts/download_dotstts.py` 下载。
目前无 SHA256 校验（见 PENDING_ISSUES P3-7）。

---

## 8. 相关文档

| 文档 | 描述 |
|------|------|
| [`need read.txt`](../need%20read.txt) | 原始私人对话总结（保留作为开发过程参考） |
| [`docs/INSTALLATION_FALLBACKS.md`](INSTALLATION_FALLBACKS.md) | 编译失败 fallback 完整文档 |
| [`docs/GPTSOVITS_DOTSTTS_INTEGRATION_GUIDE.md`](GPTSOVITS_DOTSTTS_INTEGRATION_GUIDE.md) | 集成步骤指南 |
| [`docs/PENDING_ISSUES.md`](PENDING_ISSUES.md) | 待解决问题清单 |
