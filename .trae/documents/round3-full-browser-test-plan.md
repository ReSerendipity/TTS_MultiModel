# TTS MultiModel Voice Studio — 第三轮全面浏览器测试计划

## 概要

基于前两轮测试发现的 9 个 BUG（已全部修复）和用户反馈的图标重复/缺失问题（已修复），本轮将进行全面的浏览器回归测试，覆盖所有可点击元素，确保项目正式推出后不会发生意外。

---

## 当前状态分析

### 已修复的问题（需验证）
1. **BUG-01**: i18n 失效 — `pages.py` URL 参数优先级已修正
2. **BUG-02**: 设置 API JSON 错误 — `system.py` 已添加 try-catch，`voxcpm2.html` 已添加 res.ok 检查
3. **BUG-03**: 音频播放器 null src — `<audio>` 元素已移出 HTMX target div
4. **BUG-06**: Health 轮询过频 — 间隔已从 5s 改为 10s
5. **BUG-07**: SSE 无自动重连 — 已添加 3s 延迟重连
6. **BUG-08**: 缺少空文本验证 — 3 个模板已添加前端验证
7. **BUG-09**: 输出结果区域重复渲染 — `generate.py` 已移除 card 结构
8. **图标重复**: `audio_player.html` 已移除 card/card-header 包装
9. **nav-icon 缺失**: `base.html` 已添加内联 SVG 麦克风图标

### 新发现的 BUG（本轮需修复）
10. **语言切换按钮永远无法切换到英文**: `toggleLang()` 中 `currentLang === 'zh'` 无法匹配服务端设置的 `'zh-CN'`

---

## 实施步骤

### 步骤 1：修复语言切换 BUG

**文件**: `c:\Users\FREE\.trae-cn\TTS_MultiModel\bin\integrated_app\templates\base.html` 第 2651 行

**问题**: `document.documentElement.getAttribute('lang')` 返回 `'zh-CN'`，但代码比较 `=== 'zh'`（精确匹配），永远为 false，导致 `newLang` 始终被设为 `'zh'`

**修复**: 将
```javascript
var newLang = currentLang === 'zh' ? 'en' : 'zh';
```
改为
```javascript
var newLang = currentLang.startsWith('zh') ? 'en' : 'zh';
```

### 步骤 2：解锁浏览器并打开页面

- `browser_unlock` 解锁浏览器
- `browser_navigate` 到 `http://127.0.0.1:7869/`
- `browser_wait_for` 等待 2 秒页面渲染
- `browser_snapshot` 获取初始状态
- `browser_console_messages` 检查初始错误

### 步骤 3：语言切换测试（验证 BUG-10 修复 + BUG-01 修复）

1. 确认当前为中文界面
2. JS 点击 `document.getElementById('lang-toggle-btn').click()` 切换到英文
3. 等待页面刷新，snapshot 确认英文界面
4. 检查 `<html lang="en">` 属性
5. 再次点击切换回中文
6. snapshot 确认中文恢复
7. 检查控制台无错误

### 步骤 4：主题切换测试

1. 确认当前主题（暗色）
2. JS 点击 `document.getElementById('theme-toggle-btn').click()` 切换到亮色
3. snapshot 确认亮色主题
4. 再次点击切回暗色
5. snapshot 确认

### 步骤 5：侧边栏折叠/展开测试

1. 点击汉堡按钮折叠侧边栏
2. snapshot 确认折叠状态（只显示图标）
3. 点击展开按钮恢复
4. snapshot 确认展开状态

### 步骤 6：帮助弹窗测试

1. 点击帮助按钮打开弹窗
2. snapshot 确认帮助内容
3. 点击关闭按钮
4. 再次打开，点击遮罩层关闭

### 步骤 7：9 个 Tab 导航测试

使用 JS 点击（因侧边栏按钮有负坐标问题）：
```javascript
document.querySelector('.sidebar-item[data-tab="<tab_name>"]').click();
```

依次测试：voice_design → voice_clone → ultimate_clone → script → voxcpm2 → lora → lora_training → history → persona

每个 Tab 切换后 snapshot 确认内容正确加载，检查导航高亮状态。

### 步骤 8：声音设计 Tab 详细测试

- 检查"输入设置"和"输出结果"卡片图标（无重复）
- 文本输入 + 字符计数器
- 语言下拉框选择
- "描述创建"子 Tab：预设标签点击
- "已保存音色"子 Tab：音色下拉框、刷新列表
- "固化到音色库"按钮

### 步骤 9：语音克隆 Tab 详细测试

- 检查图标无重复
- "已保存音色"/"上传参考"子 Tab 切换
- 高级参数展开：CFG 滑块、推理步数滑块、复选框
- 控制指令输入
- "开始克隆语音"按钮

### 步骤 10：极致克隆 Tab 详细测试

- 检查图标无重复
- 子 Tab 切换
- 高级参数：CFG/步数滑块、降噪/正规化下拉框、随机种子复选框
- 控制指令输入
- "极致克隆生成"按钮

### 步骤 11：剧本工坊 Tab 详细测试

- 检查图标无重复
- 剧本编辑器输入
- 控制指令输入
- "生成多人对话"按钮

### 步骤 12：设置 Tab 详细测试

- 四卡片布局：引擎信息、LoRA 管理、GPU VRAM、缓存统计
- LoRA 下拉框选择
- 加载/卸载/切换按钮
- 检查控制台无 JSON 解析错误

### 步骤 13：LoRA 管理 Tab 详细测试

- 刷新列表按钮
- LoRA 模型选择
- 加载/卸载按钮
- 启用 LoRA 复选框

### 步骤 14：LoRA 训练 Tab 详细测试

- 各输入框默认值检查
- Enable LM/DiT/Proj 复选框
- 训练日志面板

### 步骤 15：历史记录 Tab 详细测试

- 时间筛选标签（全部/今天/本周/本月）
- 搜索框输入 + 清空
- 刷新记录按钮
- 批量操作按钮

### 步骤 16：音色库 Tab 详细测试

- 列表/卡片视图切换
- 搜索 + 清空
- 刷新列表
- 试听/删除按钮（如有数据）

### 步骤 17：表单验证测试

- 声音设计：空文本点击生成
- 语音克隆：空文本点击克隆
- 极致克隆：空文本点击生成
- 剧本工坊：空剧本点击生成
- 每步检查是否有前端验证提示

### 步骤 18：国际化完整性测试

- 切换到英文，逐个检查 9 个 Tab 的 UI 文本
- 检查是否有未翻译的中文残留
- 切换回中文，确认恢复

### 步骤 19：图标一致性最终检查

- 逐个 Tab 检查卡片头部图标（每个卡片只有一个紫色图标）
- 检查侧边栏 nav-icon（麦克风 SVG）
- 检查侧边栏导航项图标
- 检查侧边栏底部按钮图标

### 步骤 20：最终检查与报告

- 回到声音设计 Tab
- 获取完整控制台日志
- 截图保存最终状态
- 检查网络请求
- 生成测试报告

---

## 验证方式

- 每个操作后通过 `browser_snapshot` 验证页面状态
- 关键步骤后通过 `browser_console_messages` 检查 JS 错误
- 通过 `browser_take_screenshot` 保存关键状态截图
- 最终生成 Markdown 格式测试报告到 `c:\Users\FREE\.trae-cn\TTS_MultiModel\browser_test_report_v2.md`

## 假设与决策

- 假设服务端已启动且可访问 http://127.0.0.1:7869/
- 假设 TTS 模型已加载（生成操作可能依赖模型状态）
- 侧边栏按钮使用 JS 点击而非直接 browser_click（因负坐标问题）
- 不测试实际的音频生成结果（依赖模型和 GPU），只测试 UI 交互流程
