# TTS MultiModel 复刻件与实际应用一致性验证报告（全面版）

- 实际应用: `http://127.0.0.1:7869/`
- HTML复刻件: `http://127.0.0.1:8765/tts_multimodel_replica.html`
- 验证时间: 2026-07-20 10:14:22

## 侧边栏折叠状态对比

| 阶段 | 指标 | 实际应用 | 复刻件 | 一致 |
|------|------|----------|--------|------|
| initial | 宽度 | `240` | `240` | 是 |
| initial | 高度 | `1080` | `1080` | 是 |
| initial | 侧边栏类 | `['sidebar']` | `['sidebar']` | 是 |
| initial | body类 | `[]` | `[]` | 是 |
| initial | 桌面按钮 display | `flex` | `flex` | 是 |
| initial | 桌面按钮 visibility | `visible` | `visible` | 是 |
| initial | 边缘按钮 display | `none` | `none` | 是 |
| initial | 边缘按钮 visibility | `visible` | `visible` | 是 |
| initial | 按钮 title | `收起侧边栏` | `收起侧边栏` | 是 |
| initial | aria-expanded | `None` | `None` | 是 |
| initial | 切换图标 SVG | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect><path d="M8 9l-3 3 3 3"></path><line x1="8" x2="8" y1="5" y2="19"></line>` | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect> <path d="M8 9l-3 3 3 3"></path> <line x1="8" x2="8" y1="5" y2="19"></line>` | 否 |
| initial | 遮罩类 | `['sidebar-overlay']` | `['sidebar-overlay']` | 是 |
| initial | 遮罩 display | `none` | `none` | 是 |
| initial | 遮罩 opacity | `0` | `0` | 是 |
| initial | 首项 tabindex | `0` | `None` | 否 |
| initial | 首项 aria-hidden | `None` | `None` | 是 |
| initial | toggleSidebarCollapse 函数 | `True` | `True` | 是 |
| initial | toggleSidebar 函数 | `True` | `True` | 是 |
| after_collapse_click | 宽度 | `60` | `60` | 是 |
| after_collapse_click | 高度 | `1080` | `1080` | 是 |
| after_collapse_click | 侧边栏类 | `['sidebar', 'collapsed']` | `['sidebar', 'collapsed']` | 是 |
| after_collapse_click | body类 | `['sidebar-is-collapsed']` | `['sidebar-is-collapsed']` | 是 |
| after_collapse_click | 桌面按钮 display | `none` | `none` | 是 |
| after_collapse_click | 桌面按钮 visibility | `visible` | `visible` | 是 |
| after_collapse_click | 边缘按钮 display | `flex` | `flex` | 是 |
| after_collapse_click | 边缘按钮 visibility | `visible` | `visible` | 是 |
| after_collapse_click | 按钮 title | `展开侧边栏` | `展开侧边栏` | 是 |
| after_collapse_click | aria-expanded | `false` | `false` | 是 |
| after_collapse_click | 切换图标 SVG | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect><path d="M16 9l3 3-3 3"></path><line x1="8" x2="8" y1="5" y2="19"></line>` | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect><path d="M16 9l3 3-3 3"></path><line x1="8" x2="8" y1="5" y2="19"></line>` | 是 |
| after_collapse_click | 遮罩类 | `['sidebar-overlay']` | `['sidebar-overlay']` | 是 |
| after_collapse_click | 遮罩 display | `none` | `none` | 是 |
| after_collapse_click | 遮罩 opacity | `0` | `0` | 是 |
| after_collapse_click | 首项 tabindex | `-1` | `-1` | 是 |
| after_collapse_click | 首项 aria-hidden | `true` | `true` | 是 |
| after_collapse_click | toggleSidebarCollapse 函数 | `True` | `True` | 是 |
| after_collapse_click | toggleSidebar 函数 | `True` | `True` | 是 |
| after_expand_click | 宽度 | `240` | `240` | 是 |
| after_expand_click | 高度 | `1080` | `1080` | 是 |
| after_expand_click | 侧边栏类 | `['sidebar']` | `['sidebar']` | 是 |
| after_expand_click | body类 | `[]` | `[]` | 是 |
| after_expand_click | 桌面按钮 display | `flex` | `flex` | 是 |
| after_expand_click | 桌面按钮 visibility | `visible` | `visible` | 是 |
| after_expand_click | 边缘按钮 display | `none` | `none` | 是 |
| after_expand_click | 边缘按钮 visibility | `visible` | `visible` | 是 |
| after_expand_click | 按钮 title | `收起侧边栏` | `收起侧边栏` | 是 |
| after_expand_click | aria-expanded | `true` | `true` | 是 |
| after_expand_click | 切换图标 SVG | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect><path d="M8 9l-3 3 3 3"></path><line x1="8" x2="8" y1="5" y2="19"></line>` | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect><path d="M8 9l-3 3 3 3"></path><line x1="8" x2="8" y1="5" y2="19"></line>` | 是 |
| after_expand_click | 遮罩类 | `['sidebar-overlay']` | `['sidebar-overlay']` | 是 |
| after_expand_click | 遮罩 display | `none` | `none` | 是 |
| after_expand_click | 遮罩 opacity | `0` | `0` | 是 |
| after_expand_click | 首项 tabindex | `0` | `0` | 是 |
| after_expand_click | 首项 aria-hidden | `None` | `None` | 是 |
| after_expand_click | toggleSidebarCollapse 函数 | `True` | `True` | 是 |
| after_expand_click | toggleSidebar 函数 | `True` | `True` | 是 |

## 侧边栏折叠动画帧

- expanded: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\actual_anim_00_expanded.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\replica_anim_00_expanded.png`
- collapse_50ms: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\actual_anim_01_collapse_50ms.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\replica_anim_01_collapse_50ms.png`
- collapse_100ms: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\actual_anim_02_collapse_100ms.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\replica_anim_02_collapse_100ms.png`
- collapse_150ms: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\actual_anim_03_collapse_150ms.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\replica_anim_03_collapse_150ms.png`
- collapse_250ms: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\actual_anim_04_collapse_250ms.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\replica_anim_04_collapse_250ms.png`
- expand_50ms: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\actual_anim_5_expand_50ms.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\replica_anim_5_expand_50ms.png`
- expand_100ms: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\actual_anim_6_expand_100ms.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\replica_anim_6_expand_100ms.png`
- expand_250ms: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\actual_anim_7_expand_250ms.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\replica_anim_7_expand_250ms.png`
- expand_350ms: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\actual_anim_8_expand_350ms.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\replica_anim_8_expand_350ms.png`

## 响应式布局对比

| 宽度 | 实际 sidebar宽 | 复刻 sidebar宽 | 实际 main margin-left | 复刻 main margin-left | 实际 桌面按钮 | 复刻 桌面按钮 | 实际 移动端按钮 | 复刻 移动端按钮 |
|------|----------------|----------------|------------------------|------------------------|---------------|---------------|-----------------|-----------------|
| 1920 | 240 | 240 | 0px | 0px | flex | flex | none | none |
| 1600 | 240 | 240 | 0px | 0px | flex | flex | none | none |
| 1440 | 240 | 240 | 0px | 0px | flex | flex | none | none |
| 1280 | 240 | 240 | 0px | 0px | flex | flex | none | none |
| 1200 | 240 | 240 | 0px | 0px | flex | none | flex | flex |
| 1100 | 240 | 240 | 0px | 0px | flex | none | flex | flex |
| 1024 | 240 | 240 | 0px | 0px | flex | none | flex | flex |
| 900 | 240 | 240 | 0px | 0px | flex | none | flex | flex |
| 768 | 280 | 240 | 0px | 0px | flex | none | flex | flex |
| 480 | 480 | 240 | 0px | 0px | flex | none | flex | flex |

## 计算样式对比（voice_design 页面）

| 选择器 | 一致 | 实际 | 复刻 |
|--------|------|------|------|
| .sidebar | 否 | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgb(255, 255, 255)', 'fontSize': '14px', 'fontFamily': 'Inter', 'fontWeight': '400', 'lineHeight': '23.8px', 'padding': '0px', 'margin': '0px', 'borderRadius': '0px', 'width': 240, 'height': 1080}` | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgb(255, 255, 255)', 'fontSize': '14px', 'fontFamily': 'Inter', 'fontWeight': '400', 'lineHeight': '21px', 'padding': '0px', 'margin': '0px', 'borderRadius': '0px', 'width': 240, 'height': 1080}` |
| .sidebar-item.active | 否 | `None` | `{'color': 'rgb(93, 74, 124)', 'backgroundColor': 'rgba(93, 74, 124, 0.08)', 'fontSize': '13px', 'fontFamily': 'Inter', 'fontWeight': '600', 'lineHeight': 'normal', 'padding': '10px 12px', 'margin': '2px 4px', 'borderRadius': '12px', 'width': 215, 'height': 38}` |
| .top-bar | 否 | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgb(255, 255, 255)', 'fontSize': '14px', 'fontFamily': 'Inter', 'fontWeight': '400', 'lineHeight': '23.8px', 'padding': '0px 20px', 'margin': '0px', 'borderRadius': '0px', 'width': 1680, 'height': 42}` | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgb(255, 255, 255)', 'fontSize': '14px', 'fontFamily': 'Inter', 'fontWeight': '400', 'lineHeight': '21px', 'padding': '0px 20px', 'margin': '0px', 'borderRadius': '0px', 'width': 1680, 'height': 48}` |
| .top-bar-title | 否 | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgba(0, 0, 0, 0)', 'fontSize': '13px', 'fontFamily': 'Inter', 'fontWeight': '600', 'lineHeight': '22.1px', 'padding': '0px', 'margin': '0px', 'borderRadius': '0px', 'width': 52, 'height': 22}` | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgba(0, 0, 0, 0)', 'fontSize': '14px', 'fontFamily': 'Inter', 'fontWeight': '600', 'lineHeight': '21px', 'padding': '0px', 'margin': '0px', 'borderRadius': '0px', 'width': 56, 'height': 21}` |
| .main-content | 否 | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgba(0, 0, 0, 0)', 'fontSize': '14px', 'fontFamily': 'Inter', 'fontWeight': '400', 'lineHeight': '23.8px', 'padding': '0px', 'margin': '0px', 'borderRadius': '0px', 'width': 1680, 'height': 1080}` | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgba(0, 0, 0, 0)', 'fontSize': '14px', 'fontFamily': 'Inter', 'fontWeight': '400', 'lineHeight': '21px', 'padding': '0px', 'margin': '0px', 'borderRadius': '0px', 'width': 1680, 'height': 1080}` |
| .page-title | 否 | `None` | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgba(0, 0, 0, 0)', 'fontSize': '20px', 'fontFamily': 'Inter', 'fontWeight': '700', 'lineHeight': '30px', 'padding': '0px', 'margin': '0px 0px 16px', 'borderRadius': '0px', 'width': 0, 'height': 0}` |
| .card | 否 | `{'color': 'rgb(26, 29, 35)', 'backgroundColor': 'rgb(255, 255, 255)', 'fontSize': '13px', 'fontFamily': 'Inter', 'fontWeight': '400', 'lineHeight': '22.1px', 'padding': '12px', 'margin': '0px 0px 12px', 'borderRadius': '12px', 'width': 887, 'height': 763}` | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgb(255, 255, 255)', 'fontSize': '14px', 'fontFamily': 'Inter', 'fontWeight': '400', 'lineHeight': '21px', 'padding': '0px', 'margin': '0px 0px 12px', 'borderRadius': '8px', 'width': 889, 'height': 678}` |
| .btn-primary | 是 | `None` | `None` |
| .mini-monitor | 否 | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgb(243, 244, 246)', 'fontSize': '14px', 'fontFamily': 'Inter', 'fontWeight': '400', 'lineHeight': '23.8px', 'padding': '4px 8px', 'margin': '0px 0px 0px 834.625px', 'borderRadius': '12px', 'width': 306, 'height': 30}` | `{'color': 'rgb(17, 24, 39)', 'backgroundColor': 'rgb(243, 244, 246)', 'fontSize': '14px', 'fontFamily': 'Inter', 'fontWeight': '400', 'lineHeight': '21px', 'padding': '7px 16px', 'margin': '0px 0px 0px 765.594px', 'borderRadius': '16px', 'width': 316, 'height': 36}` |

## 交互功能测试

### 实际应用

- **theme-toggle-btn**: 失败 - {'element': 'theme-toggle-btn', 'ok': False, 'reason': 'Page.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("#theme-toggle-btn")\n    - locator resolved to <button title="切换主题" id="theme-toggle-btn" onclick="toggleTheme()" aria-label="Toggle theme" class="sidebar-toggle-btn">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    3 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n    - waiting for element to be visible, enabled and stable\n    - element is visible, enabled and stable\n    - scrolling into view if needed\n'}
- **sidebar-toggle-btn**: 失败 - {'element': 'sidebar-toggle-btn', 'ok': False, 'reason': 'Page.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("#sidebar-toggle-btn")\n    - locator resolved to <button title="展开侧边栏" aria-expanded="false" id="sidebar-toggle-btn" aria-label="Toggle sidebar" class="sidebar-toggle-desktop" onclick="TTSApp.sidebar.toggleCollapse()">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is not visible\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is not visible\n    - retrying click action\n      - waiting 100ms\n    4 × waiting for element to be visible, enabled and stable\n      - element is not visible\n    - retrying click action\n      - waiting 500ms\n'}
- **tab-voice_design**: 失败 - {'element': 'tab-voice_design', 'ok': False, 'reason': 'Locator.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("button.sidebar-item[data-tab=\\"voice_design\\"], .sidebar-item[data-tab=\\"voice_design\\"]")\n    - locator resolved to <button title="声音设计" tabindex="-1" aria-hidden="true" hx-swap="innerHTML" class="sidebar-item" data-model="voxcpm2" data-tab="voice_design" hx-target="#tab-content" hx-indicator="#tab-loading" hx-trigger="click throttle:300ms" hx-get="/tab/voice_design?lang=zh-CN" onclick="TTSApp.sidebar.activateTab(this)">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    3 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n'}
- **tab-voice_clone**: 失败 - {'element': 'tab-voice_clone', 'ok': False, 'reason': 'Locator.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("button.sidebar-item[data-tab=\\"voice_clone\\"], .sidebar-item[data-tab=\\"voice_clone\\"]")\n    - locator resolved to <button title="语音克隆" tabindex="-1" aria-hidden="true" hx-swap="innerHTML" class="sidebar-item" data-model="voxcpm2" data-tab="voice_clone" hx-target="#tab-content" hx-indicator="#tab-loading" hx-trigger="click throttle:300ms" hx-get="/tab/voice_clone?lang=zh-CN" onclick="TTSApp.sidebar.activateTab(this)">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    3 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n'}
- **tab-ultimate_clone**: 失败 - {'element': 'tab-ultimate_clone', 'ok': False, 'reason': 'Locator.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("button.sidebar-item[data-tab=\\"ultimate_clone\\"], .sidebar-item[data-tab=\\"ultimate_clone\\"]")\n    - locator resolved to <button title="极致克隆" tabindex="-1" aria-hidden="true" hx-swap="innerHTML" class="sidebar-item" data-model="voxcpm2" hx-target="#tab-content" data-tab="ultimate_clone" hx-indicator="#tab-loading" hx-trigger="click throttle:300ms" hx-get="/tab/ultimate_clone?lang=zh-CN" onclick="TTSApp.sidebar.activateTab(this)">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    3 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n'}
- **tab-script**: 失败 - {'element': 'tab-script', 'ok': False, 'reason': 'Locator.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("button.sidebar-item[data-tab=\\"script\\"], .sidebar-item[data-tab=\\"script\\"]")\n    - locator resolved to <button title="剧本工坊" tabindex="-1" data-tab="script" aria-hidden="true" hx-swap="innerHTML" class="sidebar-item" data-model="voxcpm2" hx-target="#tab-content" hx-indicator="#tab-loading" hx-get="/tab/script?lang=zh-CN" hx-trigger="click throttle:300ms" onclick="TTSApp.sidebar.activateTab(this)">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    3 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n'}
- **tab-prompt_continue**: 失败 - {'element': 'tab-prompt_continue', 'ok': False, 'reason': 'Locator.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("button.sidebar-item[data-tab=\\"prompt_continue\\"], .sidebar-item[data-tab=\\"prompt_continue\\"]")\n    - locator resolved to <button role="tab" tabindex="-1" title="Prompt 延续" aria-hidden="true" hx-swap="innerHTML" class="sidebar-item" data-model="voxcpm2" aria-selected="false" hx-target="#tab-content" data-tab="prompt_continue" hx-indicator="#tab-loading" aria-controls="tab-content" hx-trigger="click throttle:300ms" hx-get="/tab/prompt_continue?lang=zh-CN" onclick="TTSApp.sidebar.activateTab(this)">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    3 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n    - waiting for element to be visible, enabled and stable\n'}

### 复刻件

- **theme-toggle-btn**: 失败 - {'element': 'theme-toggle-btn', 'ok': False, 'reason': 'Page.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("#theme-toggle-btn")\n    - locator resolved to <button title="切换主题" id="theme-toggle-btn" onclick="toggleTheme()" class="sidebar-toggle-btn">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    3 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n    - waiting for element to be visible, enabled and stable\n    - element is visible, enabled and stable\n    - scrolling into view if needed\n'}
- **sidebar-toggle-btn**: 失败 - {'element': 'sidebar-toggle-btn', 'ok': False, 'reason': 'Page.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("#sidebar-toggle-btn")\n    - locator resolved to <button title="收起侧边栏" id="sidebar-toggle-btn" class="sidebar-toggle-desktop" onclick="toggleSidebarCollapse()">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is not visible\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is not visible\n    - retrying click action\n      - waiting 100ms\n    4 × waiting for element to be visible, enabled and stable\n      - element is not visible\n    - retrying click action\n      - waiting 500ms\n'}
- **tab-voice_design**: 失败 - {'element': 'tab-voice_design', 'ok': False, 'reason': 'Locator.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("button.sidebar-item[data-tab=\\"voice_design\\"], .sidebar-item[data-tab=\\"voice_design\\"]")\n    - locator resolved to <button data-tab="voice_design" class="sidebar-item active" onclick="switchTab(\'voice_design\')">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    4 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n'}
- **tab-voice_clone**: 失败 - {'element': 'tab-voice_clone', 'ok': False, 'reason': 'Locator.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("button.sidebar-item[data-tab=\\"voice_clone\\"], .sidebar-item[data-tab=\\"voice_clone\\"]")\n    - locator resolved to <button class="sidebar-item" data-tab="voice_clone" onclick="switchTab(\'voice_clone\')">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    4 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n'}
- **tab-ultimate_clone**: 失败 - {'element': 'tab-ultimate_clone', 'ok': False, 'reason': 'Locator.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("button.sidebar-item[data-tab=\\"ultimate_clone\\"], .sidebar-item[data-tab=\\"ultimate_clone\\"]")\n    - locator resolved to <button class="sidebar-item" data-tab="ultimate_clone" onclick="switchTab(\'ultimate_clone\')">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    4 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n'}
- **tab-script**: 失败 - {'element': 'tab-script', 'ok': False, 'reason': 'Locator.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("button.sidebar-item[data-tab=\\"script\\"], .sidebar-item[data-tab=\\"script\\"]")\n    - locator resolved to <button data-tab="script" class="sidebar-item" onclick="switchTab(\'script\')">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    4 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n'}
- **tab-prompt_continue**: 失败 - {'element': 'tab-prompt_continue', 'ok': False, 'reason': 'Locator.click: Timeout 2000ms exceeded.\nCall log:\n  - waiting for locator("button.sidebar-item[data-tab=\\"prompt_continue\\"], .sidebar-item[data-tab=\\"prompt_continue\\"]")\n    - locator resolved to <button class="sidebar-item" data-tab="prompt_continue" onclick="switchTab(\'prompt_continue\')">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    4 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 500ms\n'}

## 控制台错误

### 实际应用
- [console] Failed to load resource: the server responded with a status of 502 ()
- [console] Failed to load resource: the server responded with a status of 502 ()
- [console] Failed to load resource: the server responded with a status of 502 ()
- [console] Failed to load resource: the server responded with a status of 502 ()
- [console] Failed to load resource: the server responded with a status of 502 ()
- [console] Failed to load resource: the server responded with a status of 502 ()
- [console] Failed to load resource: the server responded with a status of 502 ()
- [console] Failed to load resource: the server responded with a status of 502 ()
- [console] Failed to load resource: the server responded with a status of 502 ()
- [console] Failed to load resource: the server responded with a status of 502 ()
- [console] Failed to load resource: the server responded with a status of 502 ()

### 复刻件
- 无

## 页面截图路径

- voice_design: actual=`None`, replica=`None`
- voice_clone: actual=`None`, replica=`None`
- ultimate_clone: actual=`None`, replica=`None`
- script: actual=`None`, replica=`None`
- prompt_continue: actual=`None`, replica=`None`
- lora: actual=`None`, replica=`None`
- lora_training: actual=`None`, replica=`None`
- indextts2_clone: actual=`None`, replica=`None`
- indextts2_emotion: actual=`None`, replica=`None`
- indextts2_duration: actual=`None`, replica=`None`
- settings: actual=`None`, replica=`None`
- history: actual=`None`, replica=`None`
- persona: actual=`None`, replica=`None`
- help: actual=`None`, replica=`None`
