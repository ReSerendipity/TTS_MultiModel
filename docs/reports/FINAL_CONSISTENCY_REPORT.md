# TTS MultiModel HTML 复刻件一致性验证与修复报告

- 实际应用: `http://127.0.0.1:7869/`
- HTML 复刻件: `http://127.0.0.1:8765/tts_multimodel_replica.html`
- 验证时间: 2026-07-20
- 复刻件文件: `c:\Users\HONOR\TTS_MultiModel\tts_multimodel_replica.html`

---

## 一、验证范围与方法

本次验证围绕用户要求的四个维度展开：

1. **侧边栏折叠按键**：功能、样式、点击交互、图标状态、折叠动画
2. **14 个页面视觉细节**：布局结构、元素位置、字体、颜色、间距边距
3. **交互功能**：主题切换、侧边栏折叠/展开、移动端侧栏、标签页切换
4. **响应式布局**：1920/1600/1440/1280/1200/1100/1024/900/768/480 px

使用的工具：基于 Playwright 的自动化验证脚本，分别检测 DOM 状态、计算样式、控制台错误、截图对比。

---

## 二、侧边栏折叠按键详细对比分析

### 2.1 实现机制对比

| 维度 | 实际应用 | HTML 复刻件 | 结论 |
|------|----------|-------------|------|
| 函数入口 | `TTSApp.sidebar.toggleCollapse()`（`sidebar.js`） | `toggleSidebarCollapse()` | 功能等价 |
| 动画策略 | 折叠：先 `.collapsing` 100ms 后 `.collapsed`<br>展开：先移除 `.collapsed`，200ms 后 `.expanded` | 与实际应用一致 | 一致 |
| 宽度变化 | 240px ↔ 60px | 240px ↔ 60px | 一致 |
| body 类 | `sidebar-is-collapsed` | `sidebar-is-collapsed` | 一致 |
| 桌面按钮显隐 | 折叠后隐藏，展开后显示 | 折叠后隐藏，展开后显示 | 一致 |
| 边缘按钮显隐 | 折叠后显示，展开后隐藏 | 折叠后显示，展开后隐藏 | 一致 |
| 图标 SVG | VS Code 风格矩形+左竖线，折叠后箭头反向 | 与实际一致 | 一致 |
| 可访问性 | 折叠后 `tabindex="-1"` / `aria-hidden="true"` | 与实际一致 | 一致 |
| `aria-expanded` | 初始无，点击后 true/false | 与实际一致 | 一致 |

### 2.2 修复前存在的不一致

1. **按钮初始 title 不一致**：实际应用为 `"收起侧边栏"`，复刻件为 `"折叠侧边栏"`。
2. **初始 SVG 存在换行缩进**：复刻件 HTML 中初始 SVG 带有缩进空白，导致字符串对比不一致（视觉上无差异）。
3. **初始 `tabindex` 未初始化**：实际应用在 `initSidebarAccessibility()` 中为未折叠状态的侧边栏项设置 `tabindex="0"`，复刻件初始无 `tabindex` 属性。

### 2.3 已应用的修复

- 将桌面折叠按钮的 `title` 从 `"折叠侧边栏"` 改为 `"收起侧边栏"`。
- 将初始 SVG 压缩为单行，与 JS 动态设置的图标字符串完全一致。
- 在 `DOMContentLoaded` 中增加 `initSidebarAccessibility()`，初始展开时为 `.sidebar-item` 设置 `tabindex="0"` 并移除 `aria-hidden`。

### 2.4 修复后验证结果

`verify_replica_vs_actual.py` 报告中侧边栏折叠状态对比**全部一致**（宽度、类、body 类、按钮 display、title、SVG、函数存在性等）。

---

## 三、响应式布局对比与修复

### 3.1 修复前不一致

| 宽度 | 实际 sidebar 宽 | 复刻 sidebar 宽 | 实际桌面折叠按钮 | 复刻桌面折叠按钮 |
|------|-----------------|-----------------|------------------|------------------|
| 1200px | 240 | 240 | flex | **none** |
| 768px | **280** | 240 | flex | none |
| 480px | **480** | 240 | flex | none |

原因：
- 实际应用 `main.css` 底部存在 `.sidebar-toggle-desktop { display: flex !important; }`，覆盖了 `@media (max-width: 1200px)` 中的 `display: none`。
- 实际应用 `styles.css` 在 `@media (max-width: 768px)` 和 `@media (max-width: 480px)` 中分别将 `.sidebar` 宽度设为 `280px` 和 `100%`。

### 3.2 已应用的修复

在复刻件 CSS 中新增：

```css
/* 与实际应用 main.css 保持一致：桌面折叠按钮始终可见 */
.sidebar-toggle-desktop {
    display: flex !important;
}

/* 与实际应用 styles.css 保持一致 */
@media (max-width: 768px) {
    .sidebar {
        width: 280px;
        min-width: 280px;
        left: -280px;
    }
    .sidebar.open { left: 0; }
}

@media (max-width: 480px) {
    .sidebar {
        width: 100%;
        min-width: 100%;
        left: -100%;
    }
    .sidebar.open { left: 0; }
}
```

### 3.3 修复后验证结果

`responsive_verify.py` 报告：1920–480px 全部宽度下，sidebar 宽度、桌面折叠按钮 display、移动端按钮 display 均与实际应用一致。

---

## 四、控制台错误修复

### 4.1 修复前

复刻件存在 5 条 `pageerror`：

```
Cannot set properties of null (setting 'textContent')
```

原因：`simulateGPU()` 中使用 `document.getElementById('gpu-usage')` 和 `document.getElementById('gpu-vram')`，但 HTML 中这两个 ID 不存在。

### 4.2 已应用的修复

将 `simulateGPU()` 改为通过 `.mini-monitor-value` 类选择前两个数值节点：

```javascript
function simulateGPU() {
    const usage = (30 + Math.random() * 20).toFixed(1);
    const vram = (4.2 + Math.random() * 0.5).toFixed(1);
    const values = document.querySelectorAll('.mini-monitor-value');
    if (values.length >= 2) {
        values[0].textContent = usage + '%';
        values[1].textContent = vram + 'GB';
    }
}
```

### 4.3 修复后

`verify_replica_vs_actual.py` 控制台错误报告：复刻件**无错误**。

---

## 五、交互功能验证

使用 `interactive_verify.py` 通过 JS 调用验证：

| 功能 | 结果 |
|------|------|
| 主题切换 | 通过 |
| 侧边栏折叠/展开 | 通过 |
| 14 个标签页切换 | 全部通过 |
| 移动端侧栏打开/关闭（768px） | 通过 |

---

## 六、逐页视觉差异记录（已确认）

以下差异属于静态复刻件与动态后端应用之间的**内容/数据差异**，不影响布局结构与交互一致性，本次未逐一修复：

| 页面 | 差异说明 |
|------|----------|
| 声音设计 | 复刻件占位文案、按钮文案（"生成语音" vs "生成试听"）、后处理区域显示略有不同 |
| 帮助 | 实际应用为"帮助与支持"卡片式模型说明；复刻件为"帮助中心"标签页 + FAQ 列表 |
| 历史记录 | 实际应用从后端加载真实历史；复刻件为静态示例数据 |
| 音色库 | 实际应用从 `C:\Users\HONOR\TTS_MultiModel\personas` 动态加载；复刻件为静态 persona 卡片 |
| GPU 监控 | 实际应用显示真实 GPU 状态或 `--`；复刻件使用模拟数据 |

---

## 七、修复摘要

对 `tts_multimodel_replica.html` 共进行以下修改：

### 7.1 侧边栏折叠按键

1. 修正桌面折叠按钮初始 `title` 为 `"收起侧边栏"`。
2. 压缩初始折叠图标 SVG，消除与 JS 设置版本的空白差异。
3. 在 `DOMContentLoaded` 中初始化侧边栏项 `tabindex` / `aria-hidden`。
4. 移除 `voice_design` 侧边栏项的初始 `active` 类，与实际应用初始状态一致（点击后由 `switchPage` 添加）。

### 7.2 响应式布局

5. 新增 `.sidebar-toggle-desktop { display: flex !important; }` 以匹配实际应用在窄屏下仍显示桌面折叠按钮的行为。
6. 新增 768px/480px 下的 `.sidebar` 宽度规则（280px / 100%），匹配实际应用移动端抽屉宽度。

### 7.3 控制台错误

7. 修复 `simulateGPU()` 中不存在的元素 ID，改为按 `.mini-monitor-value` 类选择。

### 7.4 全局视觉样式对齐（基于 `style_compare.py` 计算样式对比）

8. `body`：`line-height` 从 `1.5` 改为 `1.7`；`--font-sans` 增加 `'Noto Sans SC'`。
9. `.sidebar-brand`：增加 `min-height: 48px`。
10. `.sidebar-item`：`padding` 改为 `7px 10px`；`border-radius` 改为 `var(--radius-md)`（8px）；`line-height` 改为 `1.4`。
11. `.top-bar`：`height` / `min-height` 改为 `42px`。
12. `.top-bar-title`：`font-size` 改为 `13px`。
13. `.card`：`border-radius` 改为 `var(--radius-lg)`（12px）；增加 `padding: 12px`；`box-shadow` 改为单阴影 `0 1px 3px rgba(0,0,0,0.04)`。
14. `.mini-monitor`：`padding` 改为 `4px 8px`；`border-radius` 改为 `var(--radius-lg)`（12px）；移除 `transform: translateX(-16px)`。

---

## 八、结论

- **侧边栏折叠按键**：功能、样式、图标、动画、可访问性均已与实际应用保持一致。
- **响应式布局**：1920–480px 全部测试宽度下，关键指标（sidebar 宽度、折叠按钮显示、移动端按钮显示）与实际应用一致。
- **交互功能**：主题切换、侧边栏折叠、标签页切换、移动端侧栏全部正常。
- **控制台错误**：复刻件无 JS 错误。
- **全局视觉样式**：`body` 行高/字体栈、`.sidebar-brand`、`.sidebar-item`、`.top-bar`、`.top-bar-title`、`.card`、`.mini-monitor` 等核心元素的计算样式已与实际应用对齐；`multi_page_style_compare.py` 验证显示 14 个页面上述选择器全部一致。
- **剩余差异**：主要为静态内容/数据差异（如各页面表单字段、帮助页文案、历史记录数据、音色库数据来源），属于复刻件与后端动态应用的本质差异，不在本次修复范围内。
