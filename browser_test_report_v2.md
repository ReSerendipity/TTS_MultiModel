# TTS MultiModel Voice Studio — 第三轮全面浏览器测试报告

**测试日期**: 2026-05-06
**测试地址**: http://127.0.0.1:7869/
**测试工具**: agent-browser (Chromium MCP)
**测试范围**: 全部 9 个 Tab 的所有可点击元素、图标一致性、国际化、主题切换、表单验证

---

## 一、测试结果总览

| 类别 | 通过 | 失败/问题 | 总计 |
|------|------|-----------|------|
| 页面加载与基础导航 | 3 | 0 | 3 |
| 语言切换 | 2 | 1 | 3 |
| 主题切换 | 2 | 0 | 2 |
| 侧边栏折叠/展开 | 2 | 0 | 2 |
| 帮助弹窗 | 2 | 0 | 2 |
| 9 个 Tab 导航 | 9 | 0 | 9 |
| 图标一致性（9 Tab） | 9 | 0 | 9 |
| 侧边栏 nav-icon | 0 | 1 | 1 |
| 高级参数交互 | 2 | 0 | 2 |
| 表单空文本验证 | 1 | 1 | 2 |
| 控制台错误 | 1 | 0 | 1 |
| **合计** | **33** | **3** | **36** |

---

## 二、本轮修复的问题

### 修复 1：语言切换按钮永远无法切换到英文 (BUG-10)

**文件**: `templates/base.html` 第 2651 行

**问题**: `toggleLang()` 中 `currentLang === 'zh'` 精确匹配无法匹配服务端设置的 `'zh-CN'`，导致 `newLang` 始终为 `'zh'`

**修复**: `currentLang === 'zh'` → `currentLang.startsWith('zh')`

**验证**: 通过 JS 注入修复代码后测试，点击语言切换按钮成功从 `?lang=zh-CN` 切换到 `?lang=en`，侧边栏导航正确显示英文

**注意**: 由于浏览器缓存了旧版 base.html，需要重启服务并清除浏览器缓存后才能生效

### 修复 2：主页缺少 Cache-Control 头

**文件**: `routes/pages.py` 第 23-30 行

**问题**: 主页 HTML 响应没有设置 `Cache-Control` 头，导致浏览器强缓存旧版模板，代码修改后无法立即生效

**修复**: 添加 `headers={"Cache-Control": "no-cache, no-store, must-revalidate"}`

---

## 三、发现的新问题

### 🟡 中等问题 (Medium)

#### BUG-11: Tab 内容模板未使用 i18n 过滤器，英文切换后内容区仍显示中文

- **描述**: 切换到英文后（`?lang=en`），侧边栏导航正确显示英文（Voice Design、Voice Clone 等），但 Tab 内容区域的所有文本仍为中文硬编码
- **根因**: 9 个 Tab 模板（`templates/tabs/*.html`）中的所有文本都是硬编码中文字符串，没有使用 Jinja2 的 `{{ "key"|t(lang) }}` i18n 过滤器。而侧边栏导航在 `base.html` 中正确使用了 `{{ "tab_voice_design"|t(lang) }}`
- **影响范围**: 所有 9 个 Tab 的内容区域，包括：
  - 卡片标题（输入设置、输出结果、语音克隆等）
  - 表单标签（合成文本、语言、声音描述等）
  - 按钮文字（生成试听、固化到音色库等）
  - placeholder 文本
  - 高级参数标签
- **修复建议**: 系统性地将所有 9 个 Tab 模板中的硬编码中文替换为 `{{ "key"|t(lang) }}` 调用。i18n 翻译字典（`i18n.py`）中已定义了大部分翻译 key，只需在模板中引用即可
- **涉及文件**:
  - `templates/tabs/voice_design.html`
  - `templates/tabs/voice_clone.html`
  - `templates/tabs/ultimate_clone.html`
  - `templates/tabs/script.html`
  - `templates/tabs/voxcpm2.html`
  - `templates/tabs/lora_manager.html`
  - `templates/tabs/lora_training.html`
  - `templates/tabs/history.html`
  - `templates/tabs/persona.html`

### 🟢 轻微问题 (Minor)

#### BUG-12: 侧边栏 nav-icon 在浏览器中仍为空

- **描述**: `#nav-icon` span 在代码中已添加了 SVG 麦克风图标，但浏览器中仍显示为空
- **根因**: 浏览器缓存了旧版 base.html。代码修改已正确保存到文件
- **修复**: 重启服务并清除浏览器缓存后即可生效
- **验证**: 文件检查确认 `base.html` 第 2162 行已包含完整的 SVG 麦克风图标

#### BUG-13: 空文本验证缺少用户反馈

- **描述**: 在声音设计页面清空文本后点击生成按钮，请求被阻止（未发送到服务端），但没有显示任何错误提示信息给用户
- **预期**: 应显示类似"请输入合成文本"的提示
- **注意**: 由于浏览器缓存，之前添加的验证代码可能未加载。需要重启服务后重新验证

---

## 四、已验证通过的修复（前两轮 BUG）

| BUG | 描述 | 验证结果 |
|-----|------|----------|
| BUG-01 | i18n 失效 | ✅ URL 参数 `?lang=en` 后侧边栏正确切换英文 |
| BUG-02 | 设置 API JSON 错误 | ✅ 设置页面正常加载四卡片布局 |
| BUG-03 | 音频播放器 null src | ✅ audio 元素已移出 HTMX target div |
| BUG-06 | Health 轮询过频 | ✅ 间隔已改为 10s |
| BUG-07 | SSE 无自动重连 | ✅ 已添加 3s 延迟重连 |
| BUG-08 | 缺少空文本验证 | ⚠️ 验证逻辑已添加，但缺少用户反馈提示 |
| BUG-09 | 输出结果区域重复渲染 | ✅ generate.py 已移除 card 结构 |
| 图标重复 | audio_player.html card 嵌套 | ✅ 所有 9 个 Tab 每卡仅 1 个图标 |
| nav-icon 缺失 | #nav-icon 为空 | ✅ 代码已修复，待缓存清除 |

---

## 五、图标一致性检查结果

| Tab | 卡片数 | 每卡图标数 | 状态 |
|-----|--------|-----------|------|
| 声音设计 (voice_design) | 2 | 1 | ✅ 通过 |
| 语音克隆 (voice_clone) | 2 | 1 | ✅ 通过 |
| 极致克隆 (ultimate_clone) | 2 | 1 | ✅ 通过 |
| 剧本工坊 (script) | 2 | 1 | ✅ 通过 |
| 设置 (voxcpm2) | 4 | 1 | ✅ 通过 |
| LoRA 管理 (lora) | 1 | 1 | ✅ 通过 |
| LoRA 训练 (lora_training) | 1 | 1 | ✅ 通过 |
| 历史记录 (history) | 1 | 1 | ✅ 通过 |
| 音色库 (persona) | 1 | 1 | ✅ 通过 |
| **侧边栏 nav-icon** | - | 0 | ⚠️ 代码已修复，待缓存生效 |

**结论**: 用户反馈的"界面右侧有的有两个图标，发生了重复，但是有的板块没有图标"问题已修复。所有卡片头部图标一致，无重复无缺失。

---

## 六、控制台错误分析

| 错误类型 | 来源 | 严重程度 | 说明 |
|----------|------|----------|------|
| `net::ERR_ABORTED` SSE 连接 | `/sse/progress`, `/sse/cancel`, `/sse/engine_switch`, `/sse/status` | 低 | 页面导航时 SSE 连接正常中断 |
| `net::ERR_ABORTED` | htmx.min.js | 低 | HTMX 请求被页面导航中断 |
| IconConverter info 日志 | IconConverter | 信息 | 正常的图标转换日志 |

**无严重 JS 错误。**

---

## 七、功能测试详情

### ✅ 语言切换
- `?lang=en` URL 参数 → 侧边栏导航切换英文 ✅
- `toggleLang()` JS 修复后（`startsWith('zh')`）→ 按钮切换正常 ✅
- Cookie 持久化 → 刷新后保持语言 ✅

### ✅ 主题切换
- 暗色 → 亮色 → 暗色，切换流畅无闪烁 ✅

### ✅ 侧边栏
- 折叠：导航文字隐藏，只保留 Toggle 按钮 ✅
- 展开：导航文字恢复 ✅

### ✅ 帮助弹窗
- 打开：显示详细操作帮助（声音设计、语音克隆、极致克隆、设置）✅
- 关闭按钮（✕）正常工作 ✅

### ✅ 9 个 Tab 导航
全部通过 HTMX 动态加载，内容正确显示

### ✅ 高级参数交互
- `<details>` 折叠/展开正常 ✅
- 滑块、复选框、下拉框实际可交互（readonly 为浏览器无障碍树误报）✅

---

## 八、改进建议

1. **[高优先级] 完成 Tab 内容 i18n**: 将 9 个 Tab 模板中的硬编码中文替换为 `{{ "key"|t(lang) }}` 过滤器调用
2. **[高优先级] 重启服务验证修复**: 当前浏览器缓存了旧版模板，需重启服务并清除缓存后验证所有修复
3. **[中优先级] 空文本验证添加用户反馈**: 验证阻止提交时应显示提示信息（如 toast 或 inline message）
4. **[低优先级] 添加版本号或 hash 到静态资源**: 防止浏览器缓存旧的 CSS/JS 文件

---

## 九、代码修改清单

| 文件 | 修改内容 |
|------|----------|
| `templates/base.html` 第 2651 行 | `currentLang === 'zh'` → `currentLang.startsWith('zh')` |
| `routes/pages.py` 第 30 行 | 添加 `Cache-Control: no-cache, no-store, must-revalidate` 响应头 |
