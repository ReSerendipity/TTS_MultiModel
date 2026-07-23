# TTS MultiModel 复刻件与实际应用一致性验证报告

- 实际应用: `http://127.0.0.1:7869/`
- HTML复刻件: `http://127.0.0.1:8765/tts_multimodel_replica.html`

## 侧边栏折叠状态对比

| 阶段 | 指标 | 实际应用 | 复刻件 | 一致 |
|------|------|----------|--------|------|
| initial | 宽度 | `240` | `240` | 是 |
| initial | 侧边栏类 | `['sidebar']` | `['sidebar']` | 是 |
| initial | body类 | `[]` | `[]` | 是 |
| initial | 桌面按钮 display | `flex` | `flex` | 是 |
| initial | 边缘按钮 display | `none` | `none` | 是 |
| initial | 按钮 title | `收起侧边栏` | `收起侧边栏` | 是 |
| initial | 切换图标 SVG | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect><path d="M8 9l-3 3 3 3"></path><line x1="8" x2="8" y1="5" y2="19"></line>` | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect><path d="M8 9l-3 3 3 3"></path><line x1="8" x2="8" y1="5" y2="19"></line>` | 是 |
| initial | toggleSidebarCollapse 函数 | `True` | `True` | 是 |
| after_collapse_click | 宽度 | `60` | `60` | 是 |
| after_collapse_click | 侧边栏类 | `['sidebar', 'collapsed']` | `['sidebar', 'collapsed']` | 是 |
| after_collapse_click | body类 | `['sidebar-is-collapsed']` | `['sidebar-is-collapsed']` | 是 |
| after_collapse_click | 桌面按钮 display | `none` | `none` | 是 |
| after_collapse_click | 边缘按钮 display | `flex` | `flex` | 是 |
| after_collapse_click | 按钮 title | `展开侧边栏` | `展开侧边栏` | 是 |
| after_collapse_click | 切换图标 SVG | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect><path d="M16 9l3 3-3 3"></path><line x1="8" x2="8" y1="5" y2="19"></line>` | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect><path d="M16 9l3 3-3 3"></path><line x1="8" x2="8" y1="5" y2="19"></line>` | 是 |
| after_collapse_click | toggleSidebarCollapse 函数 | `True` | `True` | 是 |
| after_expand_click | 宽度 | `240` | `240` | 是 |
| after_expand_click | 侧边栏类 | `['sidebar']` | `['sidebar']` | 是 |
| after_expand_click | body类 | `[]` | `[]` | 是 |
| after_expand_click | 桌面按钮 display | `flex` | `flex` | 是 |
| after_expand_click | 边缘按钮 display | `none` | `none` | 是 |
| after_expand_click | 按钮 title | `收起侧边栏` | `收起侧边栏` | 是 |
| after_expand_click | 切换图标 SVG | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect><path d="M8 9l-3 3 3 3"></path><line x1="8" x2="8" y1="5" y2="19"></line>` | `<rect x="3" y="5" width="18" height="14" rx="2" ry="2"></rect><path d="M8 9l-3 3 3 3"></path><line x1="8" x2="8" y1="5" y2="19"></line>` | 是 |
| after_expand_click | toggleSidebarCollapse 函数 | `True` | `True` | 是 |

## 控制台错误

### 实际应用
- [console] Failed to load resource: the server responded with a status of 502 ()

### 复刻件
- 无

## 页面截图路径

- voice_design: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_voice_design.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_voice_design.png`
- voice_clone: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_voice_clone.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_voice_clone.png`
- ultimate_clone: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_ultimate_clone.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_ultimate_clone.png`
- script: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_script.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_script.png`
- prompt_continue: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_prompt_continue.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_prompt_continue.png`
- lora: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_lora.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_lora.png`
- lora_training: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_lora_training.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_lora_training.png`
- indextts2_clone: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_indextts2_clone.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_indextts2_clone.png`
- indextts2_emotion: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_indextts2_emotion.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_indextts2_emotion.png`
- indextts2_duration: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_indextts2_duration.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_indextts2_duration.png`
- settings: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_settings.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_settings.png`
- history: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_history.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_history.png`
- persona: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_persona.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_persona.png`
- help: actual=`c:\Users\HONOR\TTS_MultiModel\verification_output\actual\tab_help.png`, replica=`c:\Users\HONOR\TTS_MultiModel\verification_output\replica\tab_help.png`
