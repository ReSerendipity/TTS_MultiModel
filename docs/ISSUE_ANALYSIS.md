# TTS_MultiModel 项目问题分析报告

## 1. 本地化问题 ✅ 已修复

**问题描述**: 时长控制页面 (`indextts2_duration.html`) 有以下英文文本未翻译：
- `upload_duration_ref`
- `duration_fixed_desc`
- `duration_control_mode`

**修复**: 已在 `zh.json` 添加 4 个翻译键：
- `upload_duration_ref`: "上传参考音频文件（WAV、MP3、FLAC、OGG 格式）"
- `duration_fixed_desc`: "通过调整时长倍速精确控制生成音频的长度"
- `duration_control_mode`: "时长控制模式"
- `custom_speed`: "自定义倍速"

## 2. 模型差异化问题（字数提醒）✅ 已修复

**问题描述**: 
- IndexTTS2 时长控制页显示 `0/500`（硬编码 500）
- VoxCPM2 声音设计页显示 `23/200 将分为 1 段`（使用 `gen_split_max_chars`）

**根本原因**: `routes/tabs.py` 中 `gen_split_max_chars` 硬编码为 `GEN_SPLIT_MAX_CHARS`（200），未使用设置页的可配置值。

**修复**: 
- 修改 `routes/tabs.py` 的 `_common_context()` 函数，从 `AdvancedParamsConfig` 读取可配置的 `split_max_chars`
- 所有 Tab 的字符计数器现在都使用统一的可配置值

## 3. 高级参数可用性问题

**问题描述**: 高级生成参数的专业术语（如"目标响度 LUFS"、"重试时长比率阈值"）对普通用户理解门槛过高。

**建议**: 在参数旁边添加简洁的解释文字（tooltip 或帮助图标），例如：
- 每段最大字符数 → "控制文本分段粒度，值越大单次生成文本越长"
- 重试时长比率阈值 → "输出时长超过预估时长的多少倍时自动重试"
- 目标响度 (LUFS) → "音频标准化音量，值越小声音越轻"
- 空闲超时时间 → "模型空闲超过此时间后自动卸载以释放显存"

## 4. 按键功能问题

**问题描述**: 用户反馈"前期反馈的按键功能异常问题仍未得到解决"。

**需要用户确认**: 具体是哪个按键功能异常？请提供以下信息：
- 哪个页面的哪个按钮？
- 期望的行为是什么？
- 实际的行为是什么？
- 是否有浏览器控制台的报错信息？

## 5. 参数配置完善问题

**问题描述**: 高级参数设置页面需补充之前 MD 文件 2.3 版本中默认生成但被删除的四个参数选项。

**需要用户确认**: 请提供之前的 MD 文件（2.3 版本），以便确认具体是哪四个参数被删除。

## 6. 模型参数一致性问题

**问题描述**: 两个不同模型的每段最大字符数限制存在差异。

**验证结果**:
- **VoxCPM2**: 使用 `AdvancedParamsConfig.split_max_chars`，范围 50-1000，默认 200
- **IndexTTS2**: 前端显示 `GenerationConfig.max_chars_per_segment`，范围 50-500，默认 200
- **底层**: 两个模型都使用同一个 `split_text_for_tts()` 函数，实际参数是 `AdvancedParamsConfig.split_max_chars`

**结论**: 
1. 两个模型**底层使用相同的参数**，不存在差异
2. 前端显示的范围差异是**Pydantic 配置重复定义**导致的混乱
3. 如果用户在设置页设置 1000，VoxCPM2 可以正常工作，IndexTTS2 前端的字符计数器显示可能会有误导

**修复**: 
- 修改 `routes/tabs.py` 使用统一的可配置值
- 删除 `GenerationConfig.max_chars_per_segment`（与 `AdvancedParamsConfig.split_max_chars` 重复）
- 统一使用 `AdvancedParamsConfig.split_max_chars` 作为唯一配置源

## 下一步行动

1. ✅ 本地化问题 - 已修复
2. ✅ 模型差异化问题 - 已修复
3. 高级参数可用性 - 等待用户确认是否需要添加参数说明
4. 按键功能问题 - 需要用户提供具体问题信息
5. 参数配置完善 - 需要用户提供之前的 MD 文件
6. ✅ 模型参数一致性 - 已修复（统一配置源）

请提供问题 4 和 5 的详细信息，以便继续修复。
