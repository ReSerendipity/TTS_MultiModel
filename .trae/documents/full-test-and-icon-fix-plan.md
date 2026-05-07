# TTS MultiModel Voice Studio — 全面测试与图标问题修复计划

## 摘要

对运行在 `http://127.0.0.1:7869/` 的 TTS 应用进行全面浏览器测试，覆盖所有可点击元素，并修复用户报告的图标重复/缺失问题。

## 当前状态分析

### 图标问题根因

**核心 BUG：`audio_player.html` partial 包含完整 card 结构导致图标重复**

当语音生成成功后，HTMX 将 `audio_player.html` 的内容替换到 `#vc-result`/`#vd-result` 等目标 div 中。但 tab 模板中已有"输出结果"的 card-header（含图标），`audio_player.html` 又带了一个完整的 card（含 card-header + 图标），导致两个图标并排显示。

涉及文件：
- `bin/integrated_app/templates/partials/audio_player.html` — 包含多余的 card 结构
- `bin/integrated_app/routes/generate.py` — 返回 `_success_html`/`_partial_success_html` 时也包含 card 结构（上一轮修复不完整）

**次要问题：`#nav-icon` 空元素无内容填充**

base.html 第 2162 行 `<span id="nav-icon"></span>` 没有任何 JS 或 HTML 填充内容。

### 上一轮修复遗留

上一轮修复中将 `generate.py` 的 `_success_html`/`_error_html`/`_partial_success_html` 移除了外层 card 结构，但 `audio_player.html` partial 仍然包含完整 card 结构，且部分生成端点可能仍通过 `audio_player.html` 返回内容。

## 修复计划

### 修复 1：audio_player.html 移除多余 card 结构

**文件**: `bin/integrated_app/templates/partials/audio_player.html`
**操作**: 移除外层 `<div class="card">` 和 `<div class="card-header">`，只保留 audio 和 status-message
**原因**: 消除"输出结果"卡片头和图标的重复

### 修复 2：检查 generate.py 中所有返回 HTML 的函数

**文件**: `bin/integrated_app/routes/generate.py`
**操作**: 确认所有 `_success_html`、`_error_html`、`_partial_success_html` 以及流式生成的返回 HTML 都不包含 card 结构
**原因**: 确保一致性，防止任何路径返回重复结构

### 修复 3：检查所有 tab 模板的 HTMX 目标区域

**文件**: `bin/integrated_app/templates/tabs/` 下所有模板
**操作**: 确认 `#vd-result`、`#vc-result`、`#uc-result`、`#script-result` 等目标 div 内部不包含会被重复的内容
**原因**: 防止其他模板也有类似问题

### 修复 4：nav-icon 空元素填充

**文件**: `bin/integrated_app/templates/base.html`
**操作**: 在 `#nav-icon` 中添加一个内联 SVG 图标（语音波形）
**原因**: 侧边栏品牌区域缺少图标

## 全面测试计划

### 第一阶段：图标修复验证
1. 打开应用，检查侧边栏品牌区域图标是否正常显示
2. 切换到声音设计，执行一次生成，检查"输出结果"是否只有一个图标
3. 切换到语音克隆，执行一次生成，检查图标不重复
4. 切换到极致克隆，执行一次生成，检查图标不重复
5. 切换到剧本工坊，检查页面图标

### 第二阶段：所有可点击元素测试

#### 2.1 侧边栏导航（9 个 Tab）
- 每个导航项点击 → 验证内容加载
- Toggle sidebar 按钮 → 折叠/展开
- 切换主题按钮 → 暗色/亮色
- 切换语言按钮 → 中/英切换
- 帮助按钮

#### 2.2 声音设计 Tab
- 文本输入框
- 语言下拉框（选择不同语言）
- 描述创建/已保存音色 子 Tab 切换
- 预设标签点击
- 音色下拉框选择
- 刷新列表按钮
- 生成试听按钮
- 流式生成按钮
- 固化到音色库按钮
- 输出格式选择（wav/mp3）

#### 2.3 语音克隆 Tab
- 文本输入框
- 语言下拉框
- 已保存音色/上传参考 子 Tab 切换
- 音色下拉框选择
- 刷新列表按钮
- 高级参数展开/折叠
- CFG 滑块拖动
- 推理步数滑块拖动
- 文本正规化复选框
- 降噪处理复选框
- 开始克隆语音按钮
- 固化到音色库按钮

#### 2.4 极致克隆 Tab
- 文本输入框
- 语言下拉框
- 已保存音色/上传参考 子 Tab 切换
- 音色下拉框
- 刷新列表
- 高级参数控制展开/折叠
- CFG 滑块、推理步数滑块
- 降噪/正规化下拉框
- 使用随机种子复选框
- 控制指令输入框
- 极致克隆生成按钮

#### 2.5 剧本工坊 Tab
- 剧本编辑器输入
- 控制指令输入框
- 生成多人对话按钮

#### 2.6 设置 Tab
- LoRA 模型下拉框
- 加载/卸载/切换按钮
- 清除缓存按钮

#### 2.7 LoRA 管理 Tab
- LoRA 模型选择
- 刷新列表
- 加载/卸载 LoRA 按钮
- 启用 LoRA 复选框

#### 2.8 LoRA 训练 Tab
- 各输入框（模型路径、数据清单等）
- 各数值输入（学习率、迭代次数等）
- Enable LM/DiT/Proj 复选框
- 开始训练/停止训练按钮

#### 2.9 历史记录 Tab
- 搜索框输入
- 刷新记录/清空搜索
- 时间筛选标签（全部/今天/本周/本月）
- 每页显示数量切换
- 表头复选框（全选）
- 行复选框
- 批量导出/批量删除按钮
- 分页按钮（如有数据）

#### 2.10 音色库 Tab
- 搜索框 + 搜索按钮
- 清空搜索/刷新列表
- 列表/卡片视图切换
- 试听按钮
- 删除音色按钮
- 确认/取消模态框

### 第三阶段：边界与异常测试
- 空文本提交验证
- 语言切换后各 Tab 翻译完整性
- 侧边栏折叠状态下导航
- 控制台错误检查

## 验证方式
- 每步通过浏览器 snapshot 验证
- 关键步骤截图
- 控制台错误记录
- 最终输出测试报告
