# 许可证合规与安全报告

> 章节：第十六章 | 版本: 1.0 | 日期: 2026-07-24 | 状态: 评估中
>
> 数据来源：18 个竞品仓库分析，8 个仓库涉及许可证与安全合规

---

## 目录

- [1. 许可证速查表](#1-许可证速查表)
- [2. 依赖隔离策略](#2-依赖隔离策略)
- [3. 离线优先策略](#3-离线优先策略)
- [4. 显存预检与熔断机制](#4-显存预检与熔断机制)
- [5. AGPL/CC-NC 许可证风险评估](#5-agplcc-nc-许可证风险评估)
- [6. Chatterbox 许可证确认](#6-chatterbox-许可证确认)
- [7. Edge-TTS LGPLv3 合规](#7-edge-tts-lgplv3-合规)
- [8. 水印集成](#8-水印集成)

---

## 1. 许可证速查表

### 1.1 参考仓库许可证一览

| 仓库 | 许可证 | 商用合规 | 合规要求 |
|------|--------|----------|----------|
| VoxCPM | Apache 2.0 | 可直接商用 | 保留版权声明和许可声明 |
| Fish Speech | Apache 2.0 | 可直接商用 | 保留版权声明和许可声明 |
| CosyVoice | Apache 2.0 | 代码可商用 | 模型需遵守 ModelScope 条款 |
| GPT-SoVITS | MIT | 可直接商用 | 保留版权声明 |
| Chatterbox | MIT（代码）/ 专有（模型） | 代码可商用 | 模型需确认商用条款 |
| VoiceBox | MIT | 可直接商用 | 保留版权声明 |
| StyleTTS2 | MIT | 可直接商用 | 保留版权声明 |
| OpenVoice | MIT | 可直接商用 | 保留版权声明 |
| Piper | Apache 2.0 | 可直接商用 | 保留版权声明和许可声明 |
| Bark | MIT | 可直接商用 | 保留版权声明 |
| Bert-VITS2 | MIT | 可直接商用 | 保留版权声明 |
| Real-Time-Voice-Cloning | MIT | 可直接商用 | 保留版权声明 |
| Edge-TTS | LGPLv3 | 有条件商用 | **必须动态链接**，禁止静态链接 |
| ChatTTS | AGPLv3+ / CC BY-NC 4.0 | **不可商用** | AGPL 传染性 + CC BY-NC 非商用限制 |
| Coqui-TTS | MPL-2.0 | 有条件商用 | 修改的文件需开源，新增文件不受限 |
| Tortoise-TTS | Apache 2.0 | 可直接商用 | 保留版权声明和许可声明 |
| EmotiVoice | MIT | 可直接商用 | 保留版权声明 |
| VALL-E | MIT | 可直接商用 | 保留版权声明 |

### 1.2 许可证风险分级

| 风险等级 | 许可证类型 | 仓库 | 建议 |
|----------|-----------|------|------|
| **绿色** | Apache 2.0 / MIT | VoxCPM, Fish Speech, GPT-SoVITS, OpenVoice 等 | 可直接集成和商用 |
| **黄色** | MPL-2.0 / LGPLv3 | Coqui-TTS, Edge-TTS | 有条件集成，需遵守链接/开源要求 |
| **橙色** | 专有模型许可 | Chatterbox（模型） | 仅借鉴代码模式，模型需单独确认 |
| **红色** | AGPL / CC-NC | ChatTTS | **禁止商用集成**，仅限内部评估 |

### 1.3 本项目许可证

TTS_MultiModel 项目基于 **Apache License 2.0** 开源，Copyright (c) 2026 ReSerendipity。

集成第三方组件时需注意：
- 所有 Apache 2.0/MIT 组件需在 NOTICE 文件中保留归属声明
- LGPLv3 组件必须保持动态链接
- AGPL/CC-NC 组件不得用于生产部署

---

## 2. 依赖隔离策略

### 2.1 问题描述

多引擎共存时，PyTorch、transformers、numpy、gradio 等核心依赖的版本约束互不兼容，是项目集成的最大技术障碍之一。

**已知的版本冲突**：

| 依赖 | VoxCPM2 要求 | GPT-SoVITS 要求 | Chatterbox 要求 | 冲突程度 |
|------|-------------|----------------|----------------|----------|
| PyTorch | >= 2.5.0 | >= 2.5.0 | == 2.6.0 | 中 — Chatterbox 严格 pin |
| transformers | >= 4.40 | — | — | 低 |
| numpy | < 2.0 | < 2.0 | — | 低 |
| gradio | — | < 5 | — | 中 — GPT-SoVITS 严格约束 |
| peft | — | < 0.18.0 | — | 中 — GPT-SoVITS 严格约束 |
| torchmetrics | — | <= 1.5 | — | 中 — GPT-SoVITS 严格约束 |

### 2.2 解决方案：进程级隔离

**推荐方案**：进程级隔离（Process-Level Isolation），每个引擎运行在独立子进程中，通过 gRPC/ZeroMQ 通信。

```
┌─────────────────────────────────────────────────────┐
│                   主进程 (FastAPI)                     │
│  ┌──────────────┐  ┌──────────────┐                  │
│  │ EngineRouter │  │ ModelRegistry│                  │
│  └──────┬───────┘  └──────────────┘                  │
│         │                                              │
│    gRPC / ZeroMQ                                       │
│         │                                              │
│  ┌──────┴──────────────────────────────────────┐      │
│  │                                              │      │
│  ▼                                              ▼      │
│ ┌─────────────────┐  ┌─────────────────┐  ┌─────────┐│
│ │ 引擎子进程 A     │  │ 引擎子进程 B     │  │ 引擎 C  ││
│ │ (venv_A)        │  │ (venv_B)        │  │ (venv_C)││
│ │ VoxCPM2         │  │ GPT-SoVITS      │  │ ChatTTS ││
│ │ torch==2.5.0    │  │ torch==2.5.0    │  │torch=2.6││
│ │ transformers    │  │ gradio<5        │  │...      ││
│ └─────────────────┘  └─────────────────┘  └─────────┘│
└─────────────────────────────────────────────────────┘
```

### 2.3 实施方案

#### 阶段一：虚拟环境隔离（P0，立即实施）

每个引擎使用独立 venv，主进程通过 subprocess 调用：

```python
# 隔离引擎目录结构
engines/
├── voxcpm2/          # 主进程内加载（共享 venv）
├── gpt_sovits/       # 独立 venv
│   ├── venv/
│   ├── engine_server.py   # gRPC 服务端
│   └── requirements.txt
├── indextts2/        # 主进程内加载（共享 venv）
└── edge_tts/         # 无需 venv（纯 Python）
```

#### 阶段二：gRPC 通信层（P1，1-4 周）

定义统一的引擎通信协议：

```protobuf
// engine.proto
service TTSEngine {
    rpc LoadModel(LoadModelRequest) returns (LoadModelResponse);
    rpc Generate(GenerateRequest) returns (stream AudioChunk);
    rpc UnloadModel(UnloadModelRequest) returns (UnloadModelResponse);
    rpc GetStatus(StatusRequest) returns (StatusResponse);
}
```

#### 阶段三：Docker 容器隔离（P2，1-3 月）

每个引擎独立容器，通过 REST API 通信：

```yaml
# docker-compose.yml
services:
  voxcpm2:
    build: ./engines/voxcpm2/
    runtime: nvidia
    ports: ["50051:50051"]

  gpt_sovits:
    build: ./engines/gpt_sovits/
    runtime: nvidia
    ports: ["50052:50051"]
```

### 2.4 优先级与进度

| 优先级 | 任务 | 状态 |
|--------|------|------|
| P0 | 识别所有引擎的版本约束 | 进行中 |
| P0 | VoxCPM2/IndexTTS2 共享 venv（已兼容） | 已完成 |
| P1 | GPT-SoVITS 独立 venv + subprocess | 待实施 |
| P1 | gRPC 通信协议定义 | 待实施 |
| P2 | Docker 容器化隔离 | 待实施 |

---

## 3. 离线优先策略

### 3.1 设计目标

在离线/内网环境中，TTS 系统必须完全可用，禁止在推理过程中自动下载模型或访问外部网络。

### 3.2 必需环境变量

| 环境变量 | 值 | 作用 |
|----------|-----|------|
| `TRANSFORMERS_OFFLINE` | `1` | 阻止 HuggingFace transformers 自动下载模型/tokenizer |
| `HF_HUB_OFFLINE` | `1` | 阻止 huggingface_hub 访问 HuggingFace Hub |
| `MODELSCOPE_OFFLINE` | `1` | 阻止 ModelScope SDK 自动下载模型 |

### 3.3 当前实现

在 `bin/integrated_app/config.py` 的 `_set_env()` 函数中，已实现自动设置：

```python
def _set_env():
    """Set default offline environment variables."""
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["MODELSCOPE_OFFLINE"] = "1"
```

`_setup_environment()` 函数还支持通过 `config.yaml` 的 `environment` 节点追加自定义环境变量：

```yaml
# config.yaml
environment:
  TRANSFORMERS_OFFLINE: "1"
  HF_HUB_OFFLINE: "1"
  MODELSCOPE_OFFLINE: "1"
  CUDA_VISIBLE_DEVICES: "0"
```

### 3.4 验证步骤

离线策略需通过以下验证：

- [ ] **启动验证**：断开网络后启动应用，确认无外部网络请求
- [ ] **模型加载验证**：加载已下载的模型，确认无自动下载行为
- [ ] **推理验证**：执行完整推理流程，确认无网络依赖
- [ ] **环境变量验证**：检查 `os.environ` 中三个变量已正确设置
- [ ] **日志审计**：检查启动日志无 HuggingFace/ModelScope 连接尝试
- [ ] **模型缺失验证**：模型文件不存在时，应给出明确的本地提示而非尝试下载

### 3.5 模型缺失处理

当模型文件不存在时，系统应：

1. 记录明确的错误日志，说明缺失的模型路径
2. 返回用户友好的错误消息，引导用户使用本地下载脚本
3. **禁止**自动尝试从网络下载
4. 参考 `docs/MODEL_DOWNLOAD_GUIDE.md` 提供手动下载指引

---

## 4. 显存预检与熔断机制

### 4.1 设计目标

防止 GPU 显存溢出（OOM）导致系统崩溃，在模型加载和推理阶段实施严格的显存安全检查。

### 4.2 显存预检（VRAM Precheck）

**规则**：模型加载前，可用显存需为模型预计大小的 **1.5 倍**以上。

**实现位置**：`bin/integrated_app/monitor.py` 的 `HealthMonitor.check_vram_preload()` 方法。

```python
# monitor.py
class HealthMonitor:
    VRAM_PRELOAD_SAFETY_FACTOR = 1.5

    def check_vram_preload(self, model_size_gb: float) -> bool:
        """模型加载预检：可用显存需为模型大小的 1.5 倍以上。"""
        # CPU 模式跳过预检
        # 计算 needed_gb = model_size_gb * 1.5
        # 若 free_gb < needed_gb，抛出 InsufficientVRAMError
```

**预检流程**：

```
模型加载请求
    │
    ▼
check_vram_preload(model_size_gb)
    │
    ├── CPU 模式 → 跳过预检，返回 True
    │
    ├── free_gb >= model_size_gb * 1.5 → 通过，返回 True
    │
    └── free_gb < model_size_gb * 1.5 → 抛出 InsufficientVRAMError
```

### 4.3 显存熔断（VRAM Circuit Breaker）

**规则**：显存占用超过 **90%** 时，立即终止推理并清理缓存。

**实现位置**：`bin/integrated_app/monitor.py` 的 `HealthMonitor.check_vram_circuit_breaker()` 方法。

```python
# monitor.py
class HealthMonitor:
    VRAM_CIRCUIT_BREAKER_PCT = 90.0

    def check_vram_circuit_breaker(self) -> bool:
        """显存熔断检查：占用超过 90% 时触发熔断。"""
        usage_pct = self.get_vram_usage_percent()
        if usage_pct > self.VRAM_CIRCUIT_BREAKER_PCT:
            # 递增熔断计数器
            # 清理 GPU 缓存 (free_gpu_memory)
            # 抛出 InsufficientVRAMError
```

**熔断流程**：

```
推理请求
    │
    ▼
check_vram_circuit_breaker()
    │
    ├── usage_pct <= 90% → 安全，返回 True，继续推理
    │
    └── usage_pct > 90% → 触发熔断
            │
            ├── 递增 _circuit_breaker_trips 计数器
            ├── 调用 free_gpu_memory() 清理缓存
            └── 抛出 InsufficientVRAMError
```

### 4.4 与生成管线的集成

显存安全检查已集成到生成管线的关键节点：

| 检查点 | 调用方法 | 触发条件 |
|--------|----------|----------|
| 模型加载前 | `check_vram_preload()` | 每次模型加载 |
| 推理启动前 | `check_vram_circuit_breaker()` | 每次生成请求 |
| 推理过程中 | `check_vram_circuit_breaker()` | 周期性检查 |
| 引擎切换时 | `check_vram_preload()` + `check_vram_circuit_breaker()` | 切换前双重检查 |

### 4.5 监控指标

`HealthMonitor` 提供以下监控指标：

| 指标 | 访问方式 | 说明 |
|------|----------|------|
| 当前显存占用 | `get_vram_usage_percent()` | GPU 显存占用百分比 |
| 显存趋势 | `get_vram_trend()` | 显存使用趋势（increasing/stable） |
| 泄漏检测 | `check_memory_leak()` | 检测潜在显存泄漏（200MB 阈值） |
| 熔断触发次数 | `_circuit_breaker_trips` | 累计熔断触发计数 |
| 健康报告 | `get_health_report()` | 综合健康状态报告 |

---

## 5. AGPL/CC-NC 许可证风险评估

### 5.1 ChatTTS 许可证分析

ChatTTS 采用**双重许可证**：

| 组件 | 许可证 | 关键条款 |
|------|--------|----------|
| 代码 | AGPLv3+ | 任何使用、修改、分发必须以 AGPLv3+ 开源全部源代码 |
| 模型权重 | CC BY-NC 4.0 | 禁止商业使用 |

### 5.2 AGPLv3+ 传染性风险

AGPLv3+ 是最严格的开源许可证之一，其传染性远强于 GPLv3：

| 场景 | 风险等级 | 说明 |
|------|----------|------|
| 网络服务使用 AGPL 组件 | **高风险** | AGPL 要求通过网络提供服务时也必须公开源代码 |
| 静态链接 AGPL 库 | **高风险** | 整个程序被视为 AGPL 衍生作品 |
| 动态链接 AGPL 库 | **高风险** | AGPL 的传染性不区分链接方式 |
| 进程隔离调用 AGPL 组件 | **中风险** | 法律上存在争议，不同司法辖区判决不同 |
| 仅参考设计模式 | **低风险** | 不复制代码，仅借鉴架构设计思路 |

**关键结论**：即使通过进程隔离调用 ChatTTS，AGPLv3+ 的传染性仍可能导致主项目需要开源。进程隔离不能完全规避 AGPL 风险。

### 5.3 CC BY-NC 4.0 非商用限制

CC BY-NC 4.0 明确禁止商业使用，包括但不限于：

- 将模型用于商业产品或服务
- 将生成的语音用于商业内容
- 在商业环境中部署

### 5.4 风险评估结论

| 评估项 | 结论 |
|--------|------|
| 商用集成 | **禁止** — AGPL 传染性 + CC BY-NC 双重限制 |
| 内部评估 | 允许 — 用于技术调研和设计参考 |
| 代码借鉴 | **高风险** — 即使少量代码片段也可能触发 AGPL |
| 设计模式参考 | **低风险** — 仅借鉴架构思路，不复制代码 |
| 韵律标签设计 | **低风险** — `[laugh]/[uv_break]` 等标签设计思路可借鉴 |

### 5.5 建议

1. **不集成** ChatTTS 作为生产引擎
2. 可借鉴其韵律标签设计（`[laugh]/[uv_break]/[oral_0-9]`），在自研引擎中实现类似功能
3. 可在隔离环境中进行内部技术评估，评估结果不得进入生产代码
4. 若未来 ChatTTS 更换为宽松许可证，再重新评估集成

---

## 6. Chatterbox 许可证确认

### 6.1 双层许可证结构

Chatterbox 采用**代码与模型分离**的许可证策略：

| 组件 | 许可证 | 商用状态 |
|------|--------|----------|
| 代码 | MIT | 可商用 — 保留版权声明即可 |
| 模型权重 | 专有许可 | **需确认** — 未明确标注商用条款 |

### 6.2 代码层：MIT 许可证

MIT 许可证是最宽松的开源许可证之一：

- 可自由使用、复制、修改、合并、发布、分发、再授权和/或销售
- 唯一要求：保留版权声明和许可声明
- 无传染性，不要求衍生作品开源

### 6.3 模型层：专有许可

Chatterbox 的模型权重使用专有许可证（Proprietary License），具体条款需向 Resemble AI 确认：

- **Chatterbox-Nano**（110M）：商用条款待确认
- **Chatterbox-Turbo**（350M）：商用条款待确认
- **Chatterbox-V3**（500M）：商用条款待确认
- **PerTh 水印技术**：内置于模型中，商用条款待确认

### 6.4 依赖隔离问题

Chatterbox 要求 `torch==2.6.0` 严格 pin，需使用 `--no-deps` 安装以避免依赖冲突：

```bash
pip install chatterbox-tts --no-deps
pip install torch==2.6.0 torchaudio==2.6.0
```

### 6.5 建议

| 行动 | 优先级 | 说明 |
|------|--------|------|
| 仅借鉴代码模式 | P1 | S3Tokenizer 集成方案、CAMPPlus 说话人编码器设计、条件缓存模式等 |
| 模型商用确认 | P1 | 联系 Resemble AI 确认模型商用条款 |
| 推迟模型集成 | P2 | 在商用条款确认前，不集成 Chatterbox 模型权重 |
| venv 隔离准备 | P2 | 为 Chatterbox 预留独立 venv，解决 torch==2.6.0 pin 问题 |

---

## 7. Edge-TTS LGPLv3 合规

### 7.1 LGPLv3 关键条款

LGPLv3（GNU Lesser General Public License v3）允许商业使用，但有关键限制：

| 使用方式 | 合规性 | 说明 |
|----------|--------|------|
| 动态链接 | 合规 | 主程序不受 LGPL 传染 |
| 静态链接 | **不合规** | 主程序被视为 LGPL 衍生作品，需开源 |
| 修改 LGPL 库本身 | 需开源 | 对 LGPL 库的修改必须以 LGPL 开源 |
| 仅使用 LGPL 库 | 合规 | 不修改库本身，主程序不受影响 |

### 7.2 Edge-TTS 集成合规要求

Edge-TTS 使用 LGPLv3 许可证，集成时必须遵守：

1. **必须使用动态链接**：通过 Python import 或 subprocess 调用，不将 edge-tts 代码编译进主程序
2. **禁止静态链接**：不得将 edge-ttx 源码直接复制到项目中
3. **保留许可声明**：在 NOTICE 或 THIRD_PARTY_NOTICES 文件中保留 edge-tts 的 LGPLv3 许可声明
4. **修改需开源**：若对 edge-tts 本身进行修改，修改部分必须以 LGPLv3 开源
5. **提供库源码**：用户有权获取 edge-tts 的源代码（已通过 GitHub 满足）

### 7.3 合规验证清单

- [ ] Edge-TTS 通过 `pip install edge-tts` 安装（动态链接）
- [ ] 未将 edge-tts 源码复制到项目目录
- [ ] NOTICE 文件中包含 edge-tts 的 LGPLv3 许可声明
- [ ] 未修改 edge-tts 源码（如需修改，需以 LGPLv3 开源修改部分）
- [ ] 用户可获取 edge-tts 源码（通过 PyPI 或 GitHub）
- [ ] 引用方式为 `import edge_tts` 或 subprocess 调用
- [ ] 项目打包时 edge-tts 作为独立依赖（非嵌入）

### 7.4 集成方案

```python
# 合规的集成方式 — 动态链接
import edge_tts

async def edge_tts_generate(text: str, voice: str) -> bytes:
    """通过 Edge-TTS 生成语音（动态链接合规）。"""
    communicate = edge_tts.Communicate(text, voice)
    audio_bytes = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    return audio_bytes
```

```python
# 不合规的方式 — 禁止
# from edge_tts_internal import Communicate  # 复制源码到项目中（静态链接）
```

### 7.5 建议

Edge-TTS 作为 CPU 兜底引擎，集成价值高且合规成本可控。建议：

1. 通过 pip 依赖管理，确保动态链接
2. 在项目 NOTICE 文件中添加 LGPLv3 声明
3. 不修改 edge-tts 源码，仅通过公开 API 调用
4. 在 `config.yaml` 中配置为可选降级引擎

---

## 8. 水印集成

### 8.1 设计目标

为 TTS 生成的音频嵌入不可感知的水印，用于版权保护和来源追溯。

### 8.2 技术参考：OpenVoice wavmark

OpenVoice 项目集成了 **wavmark** 水印技术，为生成音频嵌入 16-bit 信息水印：

| 参数 | 数值 |
|------|------|
| 水印容量 | 16 bits（可编码 65,536 种标识） |
| 鲁棒性 | 抗 MP3 压缩、重采样、噪声添加 |
| 不可感知性 | 水印嵌入后 PESQ/MOS 下降 < 0.05 |
| 解码方式 | 盲检测（无需原始音频） |

### 8.3 Chatterbox PerTh 水印

Chatterbox 使用 Resemble AI 的 **PerTh**（Perceptual Thresholding）神经网络水印：

- 基于深度学习的水印嵌入与检测
- 更强的鲁棒性（对抗神经网络攻击）
- 可追溯生成来源

### 8.4 水印编码方案

建议使用以下编码结构（16 bits）：

```
┌────────┬──────────┬────────────┐
│ 引擎 ID │ 用户哈希  │ 时间戳哈希  │
│ 4 bits │ 6 bits   │ 6 bits     │
└────────┴──────────┴────────────┘
```

| 字段 | 位数 | 说明 |
|------|------|------|
| 引擎 ID | 4 bits | 标识生成引擎（VoxCPM2=1, IndexTTS2=2, GPT-SoVITS=3...） |
| 用户哈希 | 6 bits | 用户标识哈希摘要（可追溯到用户） |
| 时间戳哈希 | 6 bits | 生成时间戳哈希（可追溯到生成时间） |

### 8.5 集成方案

```python
# 水印嵌入（生成管线后处理）
import wavmark

def embed_watermark(audio: np.ndarray, engine_id: int, user_hash: int, time_hash: int) -> np.ndarray:
    """为生成音频嵌入不可感知水印。"""
    watermark_bits = (engine_id << 12) | (user_hash << 6) | time_hash
    watermarked, _ = wavmark.encode(audio, watermark_bits, sr=24000)
    return watermarked

def verify_watermark(audio: np.ndarray) -> dict | None:
    """从音频中提取并验证水印。"""
    payload, _ = wavmark.decode(audio, sr=24000)
    if payload is None:
        return None
    engine_id = (payload >> 12) & 0xF
    user_hash = (payload >> 6) & 0x3F
    time_hash = payload & 0x3F
    return {"engine_id": engine_id, "user_hash": user_hash, "time_hash": time_hash}
```

### 8.6 配置集成

```yaml
# config.yaml
watermark:
  enabled: false          # 默认关闭（P3 功能）
  method: "wavmark"       # wavmark | perth
  engine_id: 1            # 当前引擎 ID
  bits: 16                # 水印位数
```

### 8.7 优先级与进度

| 优先级 | 任务 | 状态 |
|--------|------|------|
| P3 | wavmark 依赖评估 | 待启动 |
| P3 | 水印嵌入集成（生成后处理） | 待启动 |
| P3 | 水印验证工具 | 待启动 |
| P3 | config.yaml 水印配置项 | 待启动 |

**说明**：水印功能为 P3 优先级，延后实施。当前重点在引擎集成和依赖隔离（P0-P1）。水印功能不依赖其他待开发功能，可在任意阶段独立加入。

---

## 附录 A：许可证术语说明

| 术语 | 说明 |
|------|------|
| **Copyleft** | 要求衍生作品以相同许可证分发的条款（如 AGPL、GPL） |
| **传染性** | Copyleft 许可证对组合作品的影响范围 |
| **动态链接** | 运行时加载库，主程序与库保持独立 |
| **静态链接** | 编译时将库代码合并到主程序中 |
| **CC BY-NC** | 知识共享署名-非商用许可证，禁止商业使用 |
| **MPL-2.0** | Mozilla 公共许可证，文件级 copyleft（修改的文件需开源，新增文件不受限） |

## 附录 B：合规检查清单

项目发布前需确认以下合规检查项：

- [ ] 所有第三方组件许可证已识别并记录
- [ ] NOTICE 文件包含所有 Apache 2.0/MIT 组件的归属声明
- [ ] LGPLv3 组件（Edge-TTS）使用动态链接
- [ ] AGPL/CC-NC 组件（ChatTTS）未进入生产代码
- [ ] 专有许可组件（Chatterbox 模型）商用条款已确认
- [ ] 离线环境变量已正确设置
- [ ] 显存预检和熔断机制已通过测试
- [ ] 无自动下载模型的代码路径
- [ ] 所有引擎的依赖版本约束已记录
