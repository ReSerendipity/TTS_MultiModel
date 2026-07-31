# TTS MultiModel 示例代码

本目录包含 TTS MultiModel 多引擎语音合成平台的 API 使用示例和最佳实践代码。

---

## 目录

- [前置条件](#前置条件)
- [快速开始](#快速开始)
- [示例说明](#示例说明)
- [参考音频要求](#参考音频要求)
- [训练数据格式](#训练数据格式)
- [常见问题](#常见问题)

---

## 前置条件

在运行示例之前，请确保完成以下准备工作：

### 1. 启动服务端

```bash
# Windows 系统（推荐，使用内置 Python 环境）
start.bat

# 或者使用系统 Python
python bin/clean_launch.py

# Linux/Mac 系统
./start.sh
```

服务启动后默认访问地址: `http://127.0.0.1:7869`

### 2. 安装 Python 依赖

```bash
pip install httpx

# 可选：如需处理音频文件
pip install soundfile numpy
```

---

## 快速开始

```bash
# API 基础功能示例（健康检查、GPU查询、语音设计、历史记录）
python examples/api_example.py

# 批量语音合成示例
python examples/batch_example.py

# 零样本语音克隆示例（需要参考音频）
python examples/clone_example.py
```

---

## 示例说明

| 脚本文件 | 功能描述 | 难度 | 预计耗时 |
|---------|---------|------|---------|
| `api_example.py` | REST API 基础功能演示：健康检查、GPU 信息查询、模型加载、语音设计、历史记录查询 | ⭐ 入门 | 30-60s |
| `batch_example.py` | 批量文本转语音：演示如何批量处理多条文本，支持进度显示和统计 | ⭐⭐ 初级 | 取决于文本数量 |
| `clone_example.py` | 零样本语音克隆：使用参考音频克隆说话人音色，生成个性化语音 | ⭐⭐⭐ 中级 | 30-90s |

---

### api_example.py 详细说明

**功能范围:**
- 服务健康状态检查
- GPU 硬件信息与实时使用率查询
- 模型动态加载/卸载
- 语音设计（文本描述生成语音）
- 生成历史记录分页查询

**关键 API 端点:**
| 方法 | 端点 | 说明 |
|-----|------|------|
| GET | `/api/system/health` | 健康检查 |
| GET | `/api/system/gpu` | GPU 状态 |
| POST | `/api/model/load` | 加载模型 |
| GET | `/api/model/status` | 模型状态 |
| POST | `/api/generate/voxcpm2/design` | 语音设计 |
| GET | `/api/history` | 历史记录 |

---

### batch_example.py 详细说明

**功能范围:**
- 批量文本列表处理
- 串行生成避免显存溢出
- 实时进度显示
- 生成结果统计（成功率、耗时）
- 自动创建输出目录

**最佳实践:**
- 建议单批次处理 10-50 条文本
- 长文本建议先进行分句处理
- 生成失败的条目会被跳过，不影响整体流程
- 输出文件按序号命名，便于后续批量处理

---

### clone_example.py 详细说明

**功能范围:**
- 服务端连接检查
- VoxCPM2 模型加载
- 参考音频验证
- 零样本语音克隆
- 音频文件保存

**核心参数说明:**
| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| `text` | string | - | 要合成的目标文本 |
| `reference_audio` | file | - | 参考音频文件（WAV） |
| `cfg_value` | float | 2.0 | CFG 引导强度，越高越接近参考音色 |
| `inference_timesteps` | int | 10 | 推理步数，越多质量越高但越慢 |
| `normalize` | bool | true | 是否对参考音频进行响度归一化 |
| `denoise` | bool | true | 是否对参考音频进行降噪 |

---

## 参考音频要求

语音克隆功能对参考音频有一定要求，高质量的参考音频是获得好效果的关键。

### 推荐规格

| 参数 | 推荐值 | 最低要求 |
|-----|-------|---------|
| 格式 | WAV (16-bit PCM) | WAV/MP3 |
| 时长 | 10-20 秒 | 5-30 秒 |
| 采样率 | 24kHz/44.1kHz/48kHz | 16kHz |
| 声道 | 单声道 | 单声道/立体声 |

### 音频质量要求

✅ **推荐:**
- 环境安静，无背景噪音
- 说话人情绪平稳，语速适中
- 发音清晰，无吞音、咬字不清
- 无明显呼吸声、唇齿音
- 只有目标说话人一人声音

❌ **避免:**
- 有背景音乐、环境噪音
- 多人对话或交叉说话
- 强烈的情绪（大喊、哭泣）
- 回声、混响效果
- 音频压缩失真

### 准备建议

1. 使用专业麦克风在安静环境录音
2. 录音距离嘴部 15-20 厘米
3. 录制正常朗读的文本内容
4. 避免使用电话、对讲机等低质量设备录音
5. 可使用 Audacity 等工具进行简单降噪处理

---

## 训练数据格式

`train_data_example.jsonl` 文件展示了 LoRA 微调训练数据集的格式要求。

### 文件格式

JSONL (JSON Lines) 格式：每行一个 JSON 对象，表示一条训练样本。

### 字段说明

```json
{
  "audio": "path/to/audio.wav",
  "text": "音频对应的文本转写内容",
  "duration": 3.5,
  "dataset_id": 1
}
```

| 字段 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `audio` | string | ✅ | 音频文件路径（绝对路径或相对工作目录的相对路径） |
| `text` | string | ✅ | 音频的文本转写，需与音频内容一致 |
| `duration` | float | ❌ | 音频时长（秒），提供后可跳过加载阶段，加速数据筛选 |
| `dataset_id` | int | ❌ | 数据集 ID，用于混合多数据集训练 |

### 示例条目

```jsonl
{"audio": "examples/example.wav", "text": "This is an example audio transcript for training."}
{"audio": "/absolute/path/to/audio1.wav", "text": "You can use absolute paths for audio files."}
{"audio": "relative/path/to/audio2.wav", "text": "Or relative paths from the working directory."}
{"audio": "data/audio3.wav", "text": "Each line is a JSON object with audio path and text.", "duration": 3.5}
{"audio": "data/audio4.wav", "text": "Optional: add duration field to skip audio loading during filtering.", "duration": 2.8}
{"audio": "data/audio5.wav", "text": "Optional: add dataset_id for multi-dataset training.", "dataset_id": 1}
```

### 训练数据建议

- 音频总时长建议 5-30 分钟
- 文本转写需准确，错误的转写会影响训练效果
- 音频覆盖不同的语速、语调、情绪可提升泛化能力
- 建议音频格式统一为 24kHz 单声道 WAV

---

## 常见问题

### Q1: 运行示例时提示 "无法连接到服务端"

**A:** 请确认：
1. 服务端已成功启动（运行 `start.bat`）
2. 端口 7869 没有被其他程序占用
3. 防火墙没有阻止本地连接
4. `BASE_URL` 配置与服务端地址一致

### Q2: 模型加载失败或超时

**A:** 请检查：
1. GPU 显存是否足够（VoxCPM2 建议 8GB+ VRAM）
2. 模型文件是否已下载到 `pretrained_models/` 目录
3. 首次加载需要读取模型，可能需要 10-60 秒
4. 查看服务端控制台日志获取详细错误信息

### Q3: 语音克隆效果不好

**A:** 可以尝试：
1. 更换更高质量的参考音频（参考上方要求）
2. 调整 `cfg_value` 参数（2.0-4.0 之间尝试）
3. 适当增加 `inference_timesteps`（如 15-20）
4. 确保 `normalize` 和 `denoise` 参数开启
5. 参考音频时长控制在 10-20 秒效果最佳

### Q4: 生成速度很慢

**A:** 影响速度的因素：
- GPU 性能：RTX 4090 比 RTX 3060 快 3-5 倍
- 推理步数：步数越多越慢，建议 10 步
- 文本长度：长文本会自动分句，时间成正比
- 首次生成：模型预热后会更快

---

## 更多资源

- 项目主文档: [README.md](../README.md)
- 架构说明: [docs/PROJECT_ARCHITECTURE.md](../docs/PROJECT_ARCHITECTURE.md)
- API 文档: [docs/OPENAI_COMPATIBLE_API.md](../docs/OPENAI_COMPATIBLE_API.md)
- 模型下载指南: [docs/MODEL_DOWNLOAD_GUIDE.md](../docs/MODEL_DOWNLOAD_GUIDE.md)
- IndexTTS2 集成指南: [docs/INDEXTTS2_INTEGRATION_GUIDE.md](../docs/INDEXTTS2_INTEGRATION_GUIDE.md)
