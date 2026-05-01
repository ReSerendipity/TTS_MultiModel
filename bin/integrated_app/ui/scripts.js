// ===== SVG 图标系统（Lucide Icons 风格）=====
var TTS_ICONS = {
    'home': '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    'mic': '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/>',
    'copy': '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    'star': '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    'scroll': '<path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v3h4"/><path d="M19 3H9v7h12V5a2 2 0 0 0-2-2Z"/>',
    'history': '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    'library': '<path d="m22 7-8.5 5v7L22 14V7Z"/><path d="m2 7 8.5 5v7L2 14V7Z"/><path d="m12 2 8.5 5-8.5 5L3.5 7 12 2Z"/>',
    'settings': '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    'play': '<polygon points="6 3 20 12 6 21 6 3"/>',
    'download': '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
    'upload': '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/>',
    'check-circle': '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    'x-circle': '<circle cx="12" cy="12" r="10"/><line x1="15" x2="9" y1="9" y2="15"/><line x1="9" x2="15" y1="9" y2="15"/>',
    'alert-triangle': '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>',
    'info': '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    'loader': '<path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/>',
    'zap': '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    'cpu': '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
    'wand-2': '<path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72Z"/><path d="m14 7 3 3"/><path d="M5 6v4"/><path d="M19 14v4"/><path d="M10 2v2"/><path d="M7 8H3"/><path d="M21 16h-4"/><path d="M11 3H9"/>',
    'volume-2': '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>',
    'pen-line': '<path d="M12 20h9"/><path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.855z"/>',
    'dna': '<path d="M2 15c6.667-6 13.333 0 20-6"/><path d="M9 22c1.798-1.998 2.518-3.995 2.807-5.993"/><path d="M15 2c-1.798 1.998-2.518 3.995-2.807 5.993"/><path d="m17 6-2.5-2.5"/><path d="m14 8-1-1"/><path d="m7 18 2.5 2.5"/><path d="m3.5 14.5.5.5"/><path d="m20 9 .5.5"/><path d="m6.5 12.5 1 1"/><path d="m16.5 10.5 1 1"/><path d="M2 9c6.667 6 13.333 0 20 6"/>',
    'clock': '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'chevron-right': '<path d="m9 18 6-6-6-6"/>',
    'save': '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
    'refresh-cw': '<polyline points="1 4 1 10 7 10"/><polyline points="23 20 23 14 17 14"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4-4.64 4.36A9 9 0 0 1 3.51 15"/>',
    'search': '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    'trash-2': '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>',
    'external-link': '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/>'
};

function renderIcon(name, size, color) {
    size = size || 20;
    color = color || 'currentColor';
    var paths = TTS_ICONS[name];
    if (!paths) return '';
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:middle;">' + paths + '</svg>';
}

// ===== 空状态渲染函数 =====
function renderEmptyState(type, title, description, actionText, actionCallback) {
    var iconMap = {
        'history': 'clock',
        'persona': 'library',
        'search': 'search',
        'default': 'info'
    };
    var iconName = iconMap[type] || iconMap['default'];
    var html = '<div class="empty-state">' +
        '<div class="empty-state-icon">' + renderIcon(iconName, 48, 'var(--text-muted)') + '</div>' +
        '<h3 class="empty-state-title">' + title + '</h3>' +
        '<p class="empty-state-desc">' + description + '</p>';
    if (actionText) {
        html += '<button class="empty-state-action" onclick="' + (actionCallback || '') + '">' + actionText + '</button>';
    }
    html += '</div>';
    return html;
}

// ===== I18n 国际化支持 =====
        (function() {
            var translations = {
                en: {
                    nav_status: 'Dual Engines Ready · Waiting for Input',
                    nav_multi_engine: 'Multi-Engine Support',
                    history_empty_text: 'No generation records',
                    history_empty_hint: 'After synthesizing audio, history records will automatically appear here',
                    history_first_btn: '🎨 Start First Synthesis',
                    persona_empty_text: 'No custom voices',
                    persona_empty_hint: 'After saving a voice in "Voice Design" or "Voice Clone", it will be displayed here',
                    persona_first_btn: '🎨 Create First Voice',
                    filter_label: 'Filter:',
                    time_filter: 'Time:',
                    select_all: 'Select All',
                    batch_export: '📦 Batch Export',
                    batch_delete: '🗑️ Batch Delete',
                    all: 'All',
                    today: 'Today',
                    week: 'This Week',
                    month: 'This Month',
                    female: 'Female',
                    male: 'Male',
                    sweet: 'Sweet',
                    mature: 'Mature',
                    deep: 'Deep',
                    list: '☰ List',
                    card: '⊞ Card',
                    footer_brand: '🎙️ AI Voice Studio Pro',
                    footer_desc: 'Integrating Qwen3TTS and VoxCPM2 dual engines, providing professional-grade speech synthesis, voice design and multi-person script editing capabilities.',
                    footer_features: 'Core Features',
                    footer_tech: 'Technology Stack',
                    footer_links: 'Links',
                    footer_blog: 'Official Blog',
                    footer_bottom: 'Powered by <strong>Qwen3TTS</strong> · VoxCPM2 · CUDA Graph Accelerated Core'
                },
                zh: {
                    nav_status: '双引擎就绪 · 等待输入',
                    nav_multi_engine: '多引擎支持',
                    history_empty_text: '暂无生成记录',
                    history_empty_hint: '合成音频后，历史记录将自动显示在这里',
                    history_first_btn: '🎨 开始首次合成',
                    persona_empty_text: '暂无自定义音色',
                    persona_empty_hint: '在"声音设计"或"语音克隆"中保存音色后，将显示在这里',
                    persona_first_btn: '🎨 创建首个音色',
                    filter_label: '筛选:',
                    time_filter: '时间:',
                    select_all: '全选',
                    batch_export: '📦 批量导出',
                    batch_delete: '🗑️ 批量删除',
                    all: '全部',
                    today: '今天',
                    week: '本周',
                    month: '本月',
                    female: '女声',
                    male: '男声',
                    sweet: '甜美',
                    mature: '成熟',
                    deep: '低沉',
                    list: '☰ 列表',
                    card: '⊞ 卡片',
                    footer_brand: '🎙️ AI 语音工坊 Pro',
                    footer_desc: '集成 Qwen3TTS 与 VoxCPM2 双引擎，提供专业级语音合成、声音设计与多人剧本编辑能力。',
                    footer_features: '核心功能',
                    footer_tech: '技术栈',
                    footer_links: '链接',
                    footer_blog: '官方博客',
                    footer_bottom: 'Powered by <strong>Qwen3TTS</strong> · VoxCPM2 · CUDA Graph 加速内核'
                }
            };
            translations['zh-CN'] = translations.zh;
            translations['zh-Hans'] = translations.zh;
            
            var currentLang = 'zh';
            
            window.setUILanguage = function(lang) {
                currentLang = lang;
                var dict = translations[lang] || translations.zh;
                document.querySelectorAll('[data-i18n]').forEach(function(el) {
                    var key = el.getAttribute('data-i18n');
                    if (dict[key]) {
                        el.textContent = dict[key];
                    }
                });
            };
            
            setTimeout(function() { window.setUILanguage(currentLang); }, 100);
            setTimeout(function() { window.setUILanguage(currentLang); }, 500);
        })();
        
        // ===== 音频面板空状态提示 =====
        (function() {
            function addEmptyStates() {
                var groups = document.querySelectorAll('.gr-group');
                groups.forEach(function(group) {
                    var text = group.textContent || '';
                    if (text.includes('结果音频') || text.includes('合成音频') || text.includes('克隆结果')) {
                        var hasAudio = group.querySelector('audio') !== null;
                        if (!hasAudio && !group.querySelector('.output-empty-state')) {
                            var emptyDiv = document.createElement('div');
                            emptyDiv.className = 'output-empty-state';
                            emptyDiv.innerHTML = '<div style="text-align:center;">' +
                                '<div style="font-size:13px;color:rgba(255,255,255,0.9);line-height:1.6;">' +
                                '<div style="margin-bottom:6px;font-weight:600;">开始你的声音之旅：</div>' +
                                '<div style="display:flex;align-items:center;gap:6px;justify-content:center;margin-bottom:3px;">' +
                                '<span style="background:rgba(255,255,255,0.15);border-radius:50%;width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;">①</span>' +
                                '<span style="font-size:12px;">输入文本</span></div>' +
                                '<div style="display:flex;align-items:center;gap:6px;justify-content:center;margin-bottom:3px;">' +
                                '<span style="background:rgba(255,255,255,0.15);border-radius:50%;width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;">②</span>' +
                                '<span style="font-size:12px;">描述风格</span></div>' +
                                '<div style="display:flex;align-items:center;gap:6px;justify-content:center;">' +
                                '<span style="background:rgba(255,255,255,0.15);border-radius:50%;width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;">③</span>' +
                                '<span style="font-size:12px;">点击生成</span></div>' +
                                '</div></div>';
                            group.appendChild(emptyDiv);
                        }
                        if (hasAudio) {
                            var existing = group.querySelector('.output-empty-state');
                            if (existing) existing.remove();
                        }
                    }
                });
            }
            
            setTimeout(addEmptyStates, 300);
            setTimeout(addEmptyStates, 800);
        })();

        /* ===== Toast 通知系统 ===== */
        (function() {
            if (!document.querySelector('.toast-container')) {
                var container = document.createElement('div');
                container.className = 'toast-container';
                document.body.appendChild(container);
            }
        })();

        window.showToast = function(message, type, duration) {
            type = type || 'info';
            duration = duration || (type === 'success' ? 3000 : 0);
            var iconMap = { success: 'check-circle', error: 'x-circle', warning: 'alert-triangle', info: 'info' };
            var iconName = iconMap[type] || 'info';
            var toast = document.createElement('div');
            toast.className = 'tts-toast tts-toast-' + type;
            toast.innerHTML = '<span class="tts-toast-icon">' + renderIcon(iconName, 18, '#fff') + '</span>' +
                '<span class="tts-toast-message">' + message + '</span>' +
                (type === 'error' ? '<button class="tts-toast-close" onclick="this.parentElement.remove()">&times;</button>' : '');
            document.body.appendChild(toast);
            if (duration > 0) {
                setTimeout(function() {
                    toast.classList.add('hiding');
                    setTimeout(function() { toast.remove(); }, 300);
                }, duration);
            }
        };

        /* ===== 网络状态监听 ===== */
        window.addEventListener('offline', function() {
            if (window.showToast) window.showToast('\u7F51\u7EDC\u8FDE\u63A5\u5DF2\u65AD\u5F00', 'error', 0);
        });
        window.addEventListener('online', function() {
            if (window.showToast) window.showToast('\u7F51\u7EDC\u8FDE\u63A5\u5DF2\u6062\u590D', 'success', 3000);
        });

        /* ===== 字数计数器 ===== */
        window.initCharCounters = function() {
            var textareas = document.querySelectorAll('.gradio-container textarea');
            textareas.forEach(function(ta) {
                if (ta.dataset.charCounterInit) return;
                ta.dataset.charCounterInit = '1';
                var counter = document.createElement('div');
                counter.className = 'char-counter';
                ta.parentElement.style.position = 'relative';
                ta.parentElement.appendChild(counter);
                var updateCounter = function() {
                    var len = ta.value.length;
                    var maxPerSeg = 200;
                    var segs = Math.ceil(Math.max(len, 1) / maxPerSeg);
                    if (len === 0) {
                        counter.textContent = '\u6BCF200\u5B57\u81EA\u52A8\u5206\u6BB5\u5408\u6210';
                        counter.className = 'char-counter';
                    } else if (len <= maxPerSeg) {
                        counter.textContent = len + ' \u5B57 | 1 \u6BB5\u5408\u6210';
                        counter.className = 'char-counter';
                    } else {
                        counter.textContent = '\u5DF2\u8F93\u5165 ' + len + ' \u5B57\uFF08\u5C06\u5206 ' + segs + ' \u6BB5\u5408\u6210\uFF09';
                        counter.className = 'char-counter' + (len > maxPerSeg * 5 ? ' error' : len > maxPerSeg * 3 ? ' warn' : '');
                    }
                };
                ta.addEventListener('input', updateCounter);
                updateCounter();
            });
        };
        setTimeout(window.initCharCounters, 500);
        setTimeout(window.initCharCounters, 2000);

        /* ===== 输入框抖动 - 空输入提示 ===== */
        window.shakeEmptyInputs = function() {
            var generateBtns = document.querySelectorAll('.primary-btn');
            generateBtns.forEach(function(btn) {
                if (btn.dataset.shakeInit) return;
                btn.dataset.shakeInit = '1';
                btn.addEventListener('click', function() {
                    var tab = btn.closest('.tab-item, [id*="Tab"]');
                    if (!tab) return;
                    var textareas = tab.querySelectorAll('textarea');
                    textareas.forEach(function(ta) {
                        if (!ta.value || ta.value.trim() === '') {
                            ta.classList.remove('input-shake');
                            void ta.offsetWidth;
                            ta.classList.add('input-shake');
                            setTimeout(function() { ta.classList.remove('input-shake'); }, 500);
                        }
                    });
                });
            });
        };
        setTimeout(window.shakeEmptyInputs, 1000);

        /* ===== 标签页未保存警告 ===== */
        (function() {
            var tabChanges = new Map();
            var trackedTextareas = new Set();

            function trackTextarea(ta) {
                if (trackedTextareas.has(ta)) return;
                trackedTextareas.add(ta);
                var tabId = 'default';
                var parent = ta.closest('.tab-item');
                if (parent) {
                    var btn = parent.querySelector('[role="tab"], button[aria-selected]');
                    if (btn) tabId = btn.textContent || btn.getAttribute('data-id') || 'unknown';
                }
                ta.addEventListener('input', function() {
                    tabChanges.set(tabId, true);
                });
                ta._tabId = tabId;
            }

            function watchTabs() {
                document.querySelectorAll('.gradio-container textarea').forEach(trackTextarea);
            }

            setTimeout(watchTabs, 1000);
            (function watchTabsLimited() {
        setTimeout(function() {
            watchTabs();
            if (document.querySelector('.enhanced-tabs')) watchTabsLimited();
        }, 5000);
    })();

            var tabNav = document.querySelector('.enhanced-tabs > .tab-nav');
            if (tabNav) {
                tabNav.addEventListener('click', function(e) {
                    var btn = e.target.closest('button');
                    if (!btn) return;
                    var currentActive = document.querySelector('.enhanced-tabs > .tab-nav button.selected');
                    if (currentActive) {
                        var prevTabId = currentActive.textContent || 'unknown';
                        if (tabChanges.get(prevTabId)) {
                            if (!confirm('\u5F53\u524D\u6807\u7B7E\u6709\u672A\u4FDD\u5B58\u7684\u5185\u5BB9\uFF0C\u786E\u5B9A\u8981\u5207\u6362\u5417\uFF1F')) {
                                e.preventDefault();
                                e.stopPropagation();
                            } else {
                                tabChanges.set(prevTabId, false);
                            }
                        }
                    }
                });
            }
        })();

        /* ===== Skeleton 骨架屏辅助 ===== */
        window.showSkeleton = function(container, count) {
            count = count || 3;
            var el = typeof container === 'string' ? document.querySelector(container) : container;
            if (!el) return;
            el.innerHTML = '';
            for (var i = 0; i < count; i++) {
                var line = document.createElement('div');
                line.className = 'skeleton-line' + (i % 3 === 2 ? ' short' : '');
                el.appendChild(line);
            }
        };

        /* ===== DOM就绪后初始化增强 ===== */
        document.addEventListener('DOMContentLoaded', function() {
            // 渲染导航图标
            document.querySelectorAll('.nav-icon').forEach(function(el) {
                el.innerHTML = renderIcon('volume-2', 22);
            });
            // 渲染卡片标题图标
            document.querySelectorAll('[data-icon]').forEach(function(el) {
                el.innerHTML = renderIcon(el.getAttribute('data-icon'), 20);
            });
            if (window.showToast) {
                window.showToast('\u7CFB\u7EDF\u5C31\u7EEA\uFF0C\u6B22\u8FCE\u4F7F\u7528 Qwen3-TTS Pro', 'success', 4000);
            }
            // Force-show all audio player controls (Gradio hides them in dark mode)
            forceShowAudioControls();
            // Create custom audio controls overlay to bypass Shadow DOM
            setTimeout(function() {
                createCustomAudioControls();
            }, 500);
            // Also watch for dynamically added audio players
            var observer = new MutationObserver(function(mutations) {
                var shouldUpdate = false;
                mutations.forEach(function(m) {
                    m.addedNodes.forEach(function(node) {
                        if (node.nodeType === 1) {
                            if (node.querySelector && (
                                node.querySelector('.controls') ||
                                node.querySelector('[class*="svelte-72dh9g"]') ||
                                node.querySelector('[class*="waveform"]') ||
                                node.tagName === 'AUDIO' ||
                                node.className.indexOf('audio') >= 0
                            )) {
                                shouldUpdate = true;
                            }
                        }
                    });
                });
                if (shouldUpdate) {
                    forceShowAudioControls();
                    setTimeout(function() {
                        createCustomAudioControls();
                    }, 300);
                }
            });
            observer.observe(document.body, {childList: true, subtree: true});
        });

        // Create custom audio control overlay to bypass Gradio's Shadow DOM limitations
        function createCustomAudioControls() {
            // Remove any existing custom controls first
            document.querySelectorAll('.custom-audio-controls-overlay').forEach(function(el) {
                el.remove();
            });

            // Strategy 1: Find all form containers that might hold audio players
            var allForms = document.querySelectorAll('.form, .block, [class*="gradio-audio"], [class*="audio"]');
            
            // Strategy 2: Also search inside Shadow DOMs
            var shadowHosts = document.querySelectorAll('*');
            
            // Combined approach: find all potential audio player containers
            var audioContainers = [];
            
            allForms.forEach(function(form) {
                // Check for direct canvas/audio elements
                if (form.querySelector('canvas, audio, .waveform')) {
                    audioContainers.push(form);
                    return;
                }
                
                // Check text content for audio indicators (like "0:01")
                var text = form.textContent || '';
                if (text.indexOf('0:') >= 0 || text.indexOf('waveform') >= 0 || text.indexOf('audio') >= 0) {
                    audioContainers.push(form);
                    return;
                }
                
                // Check for svelte audio classes
                if (form.className && (
                    form.className.indexOf('svelte-') >= 0 && 
                    (form.className.indexOf('audio') >= 0 || form.className.indexOf('wave') >= 0)
                )) {
                    audioContainers.push(form);
                }
            });
            
            // Search Shadow DOMs for audio elements
            shadowHosts.forEach(function(host) {
                if (host.shadowRoot) {
                    var shadowCanvas = host.shadowRoot.querySelector('canvas');
                    var shadowAudio = host.shadowRoot.querySelector('audio');
                    if (shadowCanvas || shadowAudio) {
                        // Find the closest form/block container in the light DOM
                        var lightContainer = host.closest('.form, .block, [class*="audio"]');
                        if (lightContainer && audioContainers.indexOf(lightContainer) === -1) {
                            audioContainers.push(lightContainer);
                        } else if (!lightContainer && audioContainers.indexOf(host) === -1) {
                            // If no light DOM container, use the shadow host itself
                            audioContainers.push(host);
                        }
                    }
                }
            });
            
            audioContainers.forEach(function(container) {
                // Skip if already has custom controls
                if (container.querySelector('.custom-audio-controls-overlay')) {
                    return;
                }

                // Determine the best insertion point
                var insertPoint = container;
                
                // Try to find a more specific container (the audio form specifically)
                var audioSpecificContainer = container.querySelector('.form, .block, [class*="audio"]');
                if (audioSpecificContainer) {
                    insertPoint = audioSpecificContainer;
                }
                
                // Check for actual audio content
                var hasAudio = false;
                
                // Check light DOM
                if (insertPoint.querySelector('canvas, audio, .waveform')) {
                    hasAudio = true;
                }
                
                // Check Shadow DOM
                if (!hasAudio) {
                    var allShadowHosts = insertPoint.querySelectorAll('*');
                    allShadowHosts.forEach(function(host) {
                        if (host.shadowRoot && (host.shadowRoot.querySelector('canvas, audio, .waveform'))) {
                            hasAudio = true;
                        }
                    });
                }
                
                // Check text content
                if (!hasAudio) {
                    var text = (insertPoint.textContent || '') + (container.textContent || '');
                    hasAudio = text.indexOf('0:') >= 0;
                }
                
                if (!hasAudio) return;

                // Find the actual audio element for playback control
                var actualAudio = insertPoint.querySelector('audio');
                if (!actualAudio) {
                    // Search in shadow DOMs
                    var shadowHostsInContainer = insertPoint.querySelectorAll('*');
                    shadowHostsInContainer.forEach(function(host) {
                        if (host.shadowRoot && !actualAudio) {
                            actualAudio = host.shadowRoot.querySelector('audio');
                        }
                    });
                }
                if (!actualAudio) {
                    // Also check container's shadow DOM
                    if (container.shadowRoot) {
                        actualAudio = container.shadowRoot.querySelector('audio');
                    }
                }

                // Create custom controls overlay
                var overlay = document.createElement('div');
                overlay.className = 'custom-audio-controls-overlay';
                overlay.style.cssText = 'position:relative !important; z-index:9999 !important; display:flex !important; align-items:center !important; justify-content:center !important; gap:8px !important; padding:12px !important; margin:8px 0 !important; background:rgba(255,255,255,0.1) !important; border-radius:12px !important; border:1px solid rgba(255,255,255,0.2) !important; visibility:visible !important; opacity:1 !important; pointer-events:auto !important; flex-shrink:0 !important;';
                
                // Play/Pause button
                var playBtn = document.createElement('button');
                playBtn.type = 'button';
                playBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 20 12 6 21 6 3"/></svg>';
                playBtn.style.cssText = 'display:inline-flex !important; align-items:center !important; justify-content:center !important; width:48px !important; height:48px !important; border-radius:50% !important; background:linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; border:2px solid rgba(255,255,255,0.3) !important; cursor:pointer !important; box-shadow:0 4px 15px rgba(102,126,234,0.5) !important; transition:all 0.2s ease !important; visibility:visible !important; opacity:1 !important; pointer-events:auto !important; color:white !important; flex-shrink:0 !important; padding:0 !important;';
                playBtn.onmouseover = function() { this.style.transform = 'scale(1.1)'; this.style.boxShadow = '0 6px 20px rgba(102,126,234,0.7)'; };
                playBtn.onmouseout = function() { this.style.transform = 'scale(1)'; this.style.boxShadow = '0 4px 15px rgba(102,126,234,0.5)'; };
                
                if (actualAudio) {
                    playBtn.onclick = function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        if (actualAudio.paused) {
                            actualAudio.play().catch(function(e) {
                                console.log('Play prevented by browser:', e);
                            });
                            this.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
                        } else {
                            actualAudio.pause();
                            this.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 20 12 6 21 6 3"/></svg>';
                        }
                    };
                } else {
                    playBtn.style.opacity = '0.5';
                    playBtn.style.cursor = 'not-allowed';
                }

                // Stop button
                var stopBtn = document.createElement('button');
                stopBtn.type = 'button';
                stopBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/></svg>';
                stopBtn.style.cssText = 'display:inline-flex !important; align-items:center !important; justify-content:center !important; width:40px !important; height:40px !important; border-radius:50% !important; background:rgba(255,255,255,0.15) !important; border:2px solid rgba(255,255,255,0.25) !important; cursor:pointer !important; transition:all 0.2s ease !important; visibility:visible !important; opacity:1 !important; pointer-events:auto !important; color:white !important; flex-shrink:0 !important; padding:0 !important;';
                stopBtn.onmouseover = function() { this.style.background = 'rgba(255,255,255,0.3)'; };
                stopBtn.onmouseout = function() { this.style.background = 'rgba(255,255,255,0.15)'; };
                stopBtn.onclick = function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (actualAudio) {
                        actualAudio.pause();
                        actualAudio.currentTime = 0;
                    }
                    // Reset play button icon
                    if (playBtn) {
                        playBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 20 12 6 21 6 3"/></svg>';
                    }
                };

                // Volume control
                var volumeContainer = document.createElement('div');
                volumeContainer.style.cssText = 'display:flex !important; align-items:center !important; gap:8px !important; visibility:visible !important; opacity:1 !important; flex-shrink:0 !important;';
                
                var volumeIcon = document.createElement('span');
                volumeIcon.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>';
                volumeIcon.style.cssText = 'visibility:visible !important; opacity:1 !important; color:white !important;';
                
                var volumeSlider = document.createElement('input');
                volumeSlider.type = 'range';
                volumeSlider.min = '0';
                volumeSlider.max = '1';
                volumeSlider.step = '0.01';
                volumeSlider.value = actualAudio ? actualAudio.volume : 1;
                volumeSlider.style.cssText = 'width:100px !important; height:6px !important; border-radius:3px !important; background:rgba(255,255,255,0.25) !important; outline:none !important; cursor:pointer !important; visibility:visible !important; opacity:1 !important;';
                if (actualAudio) {
                    volumeSlider.oninput = function() {
                        actualAudio.volume = this.value;
                    };
                }
                
                volumeContainer.appendChild(volumeIcon);
                volumeContainer.appendChild(volumeSlider);
                
                overlay.appendChild(playBtn);
                overlay.appendChild(stopBtn);
                overlay.appendChild(volumeContainer);
                
                // Insert the overlay at the end of the container (after waveform)
                insertPoint.appendChild(overlay);
            });
        }

        // Force visibility of all audio player controls (legacy function)
        function forceShowAudioControls() {
            // Target all possible audio player containers
            var selectors = [
                '.gradio-audio', '.purple-audio', '.tts-audio-player',
                '[class*="audio"]', '[class*="Audio"]',
                '[data-testid="audio"]', '[data-testid="waveform"]',
                '[data-testid="waveform-controls"]',
                '.form', '[class*="form"]'
            ];
            var allContainers = [];
            selectors.forEach(function(sel) {
                try {
                    document.querySelectorAll(sel).forEach(function(el) {
                        allContainers.push(el);
                    });
                } catch(e) {}
            });
            
            allContainers.forEach(function(container) {
                // Check if this container has audio-related content
                var hasAudioContent = container.querySelector('canvas') || 
                                     container.querySelector('audio') ||
                                     container.querySelector('[class*="waveform"]') ||
                                     container.querySelector('[class*="controls"]') ||
                                     (container.textContent && container.textContent.indexOf('0:') >= 0);
                
                if (hasAudioContent || container.className.indexOf('audio') >= 0) {
                    container.style.visibility = 'visible';
                    container.style.opacity = '1';
                    container.style.display = 'block';
                    
                    // Force all descendants visible
                    var children = container.querySelectorAll('*');
                    children.forEach(function(child) {
                        child.style.visibility = 'visible';
                        child.style.opacity = '1';
                        child.style.pointerEvents = 'auto';
                        if (child.tagName === 'BUTTON' || child.tagName === 'button') {
                            child.style.display = 'inline-flex';
                            child.style.cursor = 'pointer';
                            child.style.color = '#ffffff';
                            child.style.background = 'rgba(255,255,255,0.15)';
                            child.style.border = '1px solid rgba(255,255,255,0.2)';
                            child.style.borderRadius = '50%';
                            child.style.padding = '6px';
                            child.style.margin = '0 3px';
                            child.style.minWidth = '32px';
                            child.style.minHeight = '32px';
                            child.style.alignItems = 'center';
                            child.style.justifyContent = 'center';
                        }
                        if (child.tagName === 'svg' || child.tagName === 'SVG') {
                            child.style.color = '#ffffff';
                            child.style.fill = '#ffffff';
                            child.style.stroke = '#ffffff';
                            child.style.display = 'inline-block';
                        }
                        // Fix controls container
                        if (child.className && (
                            child.className.indexOf('controls') >= 0 ||
                            child.className.indexOf('play-pause') >= 0 ||
                            child.className.indexOf('control-wrapper') >= 0 ||
                            child.className.indexOf('svelte-72dh9g') >= 0
                        )) {
                            child.style.display = 'flex';
                            child.style.flexWrap = 'wrap';
                            child.style.justifyContent = 'center';
                            child.style.alignItems = 'center';
                            child.style.gap = '4px';
                            child.style.padding = '4px';
                        }
                    });
                }
            });
        }

        /* ===== 声音描述预设标签点击插入 ===== */
        (function() {
            var initTags = function() {
                var container = document.getElementById('voice-preset-tags');
                if (!container) return;
                if (container.dataset.tagInit) return;
                container.dataset.tagInit = '1';
                
                var tags = container.querySelectorAll('.preset-tag');
                tags.forEach(function(tag) {
                    tag.addEventListener('click', function() {
                        // 预设标签选中态
                        document.querySelectorAll('.preset-tag').forEach(function(t) { t.classList.remove('preset-tag-active'); });
                        this.classList.add('preset-tag-active');
                        var value = this.getAttribute('data-value') || this.textContent;
                        // Find the voice description textarea (声音描述)
                        var descTextarea = document.querySelector('[aria-label*="声音描述"], [placeholder*="极度撒娇的萝莉音"]');
                        if (descTextarea) {
                            if (descTextarea.value && descTextarea.value.trim()) {
                                descTextarea.value = descTextarea.value.trim() + '，' + value;
                            } else {
                                descTextarea.value = value;
                            }
                            descTextarea.dispatchEvent(new Event('input', { bubbles: true }));
                            descTextarea.focus();
                        }
                    });
                });
            };
            
            setTimeout(initTags, 800);
            setTimeout(initTags, 2000);
            var _tagObserver = new MutationObserver(function() { setTimeout(initTags, 200); }); _tagObserver.observe(document.body, { childList: true, subtree: true });;
        })();
        
        // ===== 官方精品音色卡片交互 =====
        window.selectSpeakerCard = function(key) {
            // 更新选中状态
            document.querySelectorAll('.speaker-card').forEach(function(card) {
                card.classList.remove('selected');
            });
            var target = document.querySelector('.speaker-card[data-speaker="' + key + '"]');
            if (target) target.classList.add('selected');
            
            // 更新桥接 Textbox（触发 Python 端 change 事件）
            var bridgeInput = document.querySelector('#speaker-bridge-input textarea, #speaker-bridge-input input');
            if (bridgeInput) { bridgeInput.value = key; bridgeInput.dispatchEvent(new Event('input', {bubbles: true})); }
            
            // 更新详情面板
            var info = window.SPEAKER_INFO || {};
            var s = info[key] || ["", "", "", ""];
            var detailContainer = document.getElementById('speaker-detail-container');
            if (detailContainer) {
                detailContainer.innerHTML = '<div class="speaker-detail-panel">' +
                    '<h3>🎙️ ' + s[0] + ' (' + key + ')</h3>' +
                    '<div class="detail-row"><span class="detail-label">音色类型</span><span class="detail-value">' + s[2] + '</span></div>' +
                    '<div class="detail-row"><span class="detail-label">声音特点</span><span class="detail-value">' + s[3] + '</span></div>' +
                    '<div class="detail-row"><span class="detail-label">详细说明</span><span class="detail-value">' + s[1] + '</span></div>' +
                    '</div>';
            }
        };
        
        window.filterSpeaker = function(filter) {
            document.querySelectorAll('.filter-chip').forEach(function(chip) {
                chip.classList.remove('active');
            });
            document.querySelector('.filter-chip[data-filter="' + filter + '"]')?.classList.add('active');
            
            var cards = document.querySelectorAll('.speaker-card');
            cards.forEach(function(card) {
                if (filter === 'all') { card.style.display = ''; return; }
                var name = card.getAttribute('data-speaker') || '';
                var info = window.SPEAKER_INFO || {};
                var s = info[name] || [];
                var type = (s[2] || '').toLowerCase();
                var show = false;
                if (filter === 'female') show = (type.indexOf('女') >= 0 || type.indexOf('少女') >= 0 || type.indexOf('御姐') >= 0 || type.indexOf('甜') >= 0 || type.indexOf('日系') >= 0 || type.indexOf('韩系') >= 0);
                else if (filter === 'male') show = (type.indexOf('男') >= 0 || type.indexOf('低音') >= 0);
                else if (filter === 'sweet') show = (type.indexOf('甜') >= 0 || type.indexOf('少女') >= 0 || type.indexOf('日系') >= 0 || type.indexOf('韩系') >= 0);
                else if (filter === 'mature') show = (type.indexOf('御姐') >= 0 || type.indexOf('成熟') >= 0 || type.indexOf('中年') >= 0 || type.indexOf('青年') >= 0);
                else if (filter === 'deep') show = (type.indexOf('低音') >= 0 || type.indexOf('深沉') >= 0 || type.indexOf('磁性') >= 0);
                card.style.display = show ? '' : 'none';
            });
        };
        
        window.SPEAKER_INFO = {
             "Vivian": ["薇薇安", "甜美少女音，活泼热情，适合年轻女性角色配音。擅长日常对话和情感表达。", "少女音", "年轻活泼，语速轻快"],
             "Serena": ["塞雷娜", "优雅成熟女性声线，知性大方。适合专业播报、教学讲解和商务场景。", "御姐音", "沉稳知性，语速适中"],
             "Uncle_Fu": ["傅叔叔", "中年男性沉稳声线，温和可靠。适合长辈角色、纪录片旁白和故事讲述。", "中年男音", "沉稳厚重，语速较慢"],
             "Dylan": ["迪伦", "年轻男性活力声线，阳光开朗。适合青年角色、广告配音和娱乐内容。", "青年男音", "阳光活力，语速较快"],
             "Eric": ["埃里克", "磁性低沉男声，深沉有魅力。适合悬疑叙事、有声书和电影预告。", "低音炮", "深沉磁性，语速缓慢"],
             "Ryan": ["瑞恩", "清脆少年音，干净纯粹。适合动漫角色、儿童内容和轻快解说。", "少年音", "清脆明亮，语速轻快"],
             "Aiden": ["艾登", "温暖青年男声，亲切自然。适合播客、自媒体和日常交流场景。", "暖男音", "温和亲切，语速适中"],
             "Ono_Anna": ["小野安娜", "日式甜美女声，日系二次元风格。适合动漫角色、游戏配音和轻小说。", "日系甜音", "甜美可爱，语速轻快"],
             "Sohee": ["秀熙", "韩式清甜女声，韩流风格。适合韩剧风格内容、韩语学习辅助。", "韩系甜音", "清甜温柔，语速适中"]
         };
         
         // ===== 历史记录时间筛选 =====
         window.filterHistoryTime = function(filter) {
             document.querySelectorAll('.time-filter-chip').forEach(function(chip) {
                 chip.classList.remove('active');
             });
             document.querySelector('.time-filter-chip[data-time="' + filter + '"]')?.classList.add('active');
             // 通知后端刷新
             var rows = document.querySelectorAll('.enhanced-tabs .gr-dataframe tbody tr, .gradio-dataframe table tbody tr');
             if (rows.length === 0) return;
             // 这里通过刷新按钮触发实际筛选
             var refreshBtn = document.querySelector('[data-testid="🔄 刷新记录"]');
             if (refreshBtn) refreshBtn.click();
         };
         
         // ===== 历史记录批量操作 =====
         window.toggleAllHistory = function(checked) {
             document.querySelectorAll('.history-row-checkbox').forEach(function(cb) {
                 cb.checked = checked;
             });
         };
         
         window.batchExportHistory = function() {
             var selected = document.querySelectorAll('.history-row-checkbox:checked');
             if (selected.length === 0) { alert('请先选择要导出的记录'); return; }
             alert('批量导出功能：将导出 ' + selected.length + ' 个文件');
         };
         
         window.batchDeleteHistory = function() {
             var selected = document.querySelectorAll('.history-row-checkbox:checked');
             if (selected.length === 0) { alert('请先选择要删除的记录'); return; }
             if (confirm('确定要删除选中的 ' + selected.length + ' 条记录吗？此操作不可恢复。')) {
                 alert('批量删除功能已触发');
             }
         };
         
         // ===== 音色库视图切换 =====
         window.switchVoiceView = function(view) {
             document.querySelectorAll('.view-toggle-btn').forEach(function(btn) {
                 btn.classList.remove('active');
             });
             document.querySelector('.view-toggle-btn[data-view="' + view + '"]')?.classList.add('active');
             
             var listView = document.getElementById('persona-list-view');
             var cardView = document.getElementById('persona-card-view');
             if (view === 'card') {
                 if (listView) listView.style.display = 'none';
                 if (cardView) { cardView.style.display = ''; cardView.innerHTML = buildPersonaCardGrid(); }
             } else {
                 if (listView) listView.style.display = '';
                 if (cardView) cardView.style.display = 'none';
             }
         };
         
         window.buildPersonaCardGrid = function() {
             // 从表格数据构建卡片视图
             var df = document.querySelector('#persona-list-view table');
             if (!df) return '<p style="color:var(--text-muted)">暂无数据</p>';
             var rows = df.querySelectorAll('tbody tr');
             if (rows.length === 0 || (rows.length === 1 && rows[0].textContent.includes('暂无'))) {
                 return '<p style="color:var(--text-muted)">暂无音色</p>';
             }
             var html = '<div class="voice-card-grid">';
             rows.forEach(function(row) {
                 var cells = row.querySelectorAll('td');
                 if (cells.length >= 4) {
                     var name = cells[0].textContent.trim();
                     var status = cells[1].textContent.trim();
                     var size = cells[2].textContent.trim();
                     var time = cells[3].textContent.trim();
                     html += '<div class="voice-card" onclick="selectPersonaCard(' + JSON.stringify(name) + ')">' +
                         '<h4 class="voice-card-name">' + name + '</h4>' +
                         '<div class="voice-card-meta">状态: ' + status + ' | 大小: ' + size + '</div>' +
                         '<div class="voice-card-meta">创建: ' + time + '</div>' +
                         '<div class="voice-card-actions">' +
                         '<span class="speaker-card-btn" onclick="event.stopPropagation(); playPersonaByName(' + JSON.stringify(name) + ')">🔊 试听</span>' +
                         '</div></div>';
                 }
             });
             html += '</div>';
             return html;
         };
         
         window.selectPersonaCard = function(name) {
             var input = document.querySelector('[aria-label="当前选中音色"], #persona-list-view input');
             if (input) { input.value = name; input.dispatchEvent(new Event('input', {bubbles: true})); }
         };
         
         window.playPersonaByName = function(name) {
             var playBtn = document.querySelector('[data-testid="▶️ 试听音色"]');
             if (playBtn) playBtn.click();
         };
         
         // ===== 光标位置插入文本 =====
         window.insertAtCursor = function(textareaId, text) {
             var ta = document.querySelector(textareaId);
             if (!ta) return;
             var start = ta.selectionStart;
             var end = ta.selectionEnd;
             var value = ta.value;
             ta.value = value.substring(0, start) + text + value.substring(end);
             ta.selectionStart = ta.selectionEnd = start + text.length;
             ta.dispatchEvent(new Event('input', {bubbles: true}));
             ta.focus();
         };
         
         // ===== 键盘快捷键 =====
        document.addEventListener('keydown', function(e) {
            // Ctrl+Enter 触发当前标签页的生成按钮
            if (e.ctrlKey && e.key === 'Enter') {
                var genBtn = document.querySelector('.generate-btn:not([disabled])');
                if (genBtn) {
                    genBtn.click();
                    e.preventDefault();
                }
            }
            // Esc 清空当前输入框
            if (e.key === 'Escape') {
                var activeEl = document.activeElement;
                if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA')) {
                    activeEl.value = '';
                    activeEl.dispatchEvent(new Event('input', {bubbles: true}));
                    e.preventDefault();
                }
            }
        });

        // ===== IntersectionObserver 滚动触发入场动画 =====
        (function() {
            if ('IntersectionObserver' in window) {
                var observer = new IntersectionObserver(function(entries) {
                    entries.forEach(function(entry) {
                        if (entry.isIntersecting) {
                            entry.target.classList.add('tts-visible');
                            observer.unobserve(entry.target);
                        }
                    });
                }, { threshold: 0.1 });
                document.querySelectorAll('.card, .speaker-card').forEach(function(el) {
                    el.classList.add('tts-animate-on-scroll');
                    observer.observe(el);
                });
            }
        })();

        // ===== 字数统计颜色变化 =====
        (function() {
            function updateCharCounterColor() {
                var charCounters = document.querySelectorAll('.char-counter');
                charCounters.forEach(function(counter) {
                    var text = counter.textContent || '';
                    var match = text.match(/(\d+)/);
                    var count = match ? parseInt(match[1]) : 0;
                    counter.classList.remove('char-warning', 'char-error');
                    if (count > 500) {
                        counter.classList.add('char-error');
                    } else if (count > 200) {
                        counter.classList.add('char-warning');
                    }
                });
            }
            setInterval(updateCharCounterColor, 500);
            setTimeout(updateCharCounterColor, 1000);
        })();

        // ===== 拖拽上传反馈 =====
        (function() {
            document.querySelectorAll('input[type="file"]').forEach(function(input) {
                var dropZone = input.closest('.gr-group') || input.parentElement;
                if (!dropZone) return;
                dropZone.addEventListener('dragover', function(e) {
                    e.preventDefault();
                    dropZone.classList.add('tts-drag-over');
                });
                dropZone.addEventListener('dragleave', function() {
                    dropZone.classList.remove('tts-drag-over');
                });
                dropZone.addEventListener('drop', function() {
                    dropZone.classList.remove('tts-drag-over');
                });
            });
        })();

        // ===== 高级设置折叠/展开 =====
        document.addEventListener('click', function(e) {
            var toggle = e.target.closest('.advanced-toggle');
            if (!toggle) return;
            var target = toggle.nextElementSibling;
            if (!target || !target.classList.contains('advanced-settings')) return;
            toggle.classList.toggle('expanded');
            target.classList.toggle('expanded');
        });

        // ===== 官方精品音色试听功能 =====
        window.previewSpeaker = function(key) {
            var info = window.SPEAKER_INFO || {};
            var s = info[key] || ["", "", "", ""];
            var name = s[0] || key;
            var sizeEl = document.querySelector('#官方精品 input[type="radio"]:checked, #官方精品 [role="radio"][aria-checked="true"]');
            var size = "1.7B";
            if (sizeEl) {
                var val = sizeEl.value || sizeEl.getAttribute('aria-label') || sizeEl.textContent;
                if (val && val.indexOf("0.6B") >= 0) size = "0.6B";
            }
            var previewText = "你好，我是" + name + "，很高兴认识你。";
            showToast("正在生成 " + name + " 的试听音频...", "info", 2000);
            // 显示可见的播放器
            var player = document.getElementById('speaker-preview-player');
            var label = document.getElementById('preview-label');
            var audioEl = document.getElementById('preview-audio');
            if (player) player.style.display = 'block';
            if (label) label.textContent = '正在生成: ' + name + ' ...';
            fetch("/api/generate", {
                method: "POST",
                headers: {"Content-Type": "application/json; charset=utf-8"},
                body: JSON.stringify({
                    mode: "custom_voice",
                    text: previewText,
                    lang: "Auto",
                    size: size,
                    speaker: key,
                    instruct: "",
                    format: "wav"
                })
            }).then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.status === "ok" && data.audio_base64) {
                    var binary = atob(data.audio_base64);
                    var bytes = new Uint8Array(binary.length);
                    for (var i = 0; i < binary.length; i++) {
                        bytes[i] = binary.charCodeAt(i);
                    }
                    var blob = new Blob([bytes], {type: "audio/wav"});
                    var url = URL.createObjectURL(blob);
                    if (audioEl) {
                        audioEl.src = url;
                        audioEl.style.display = 'block';
                        if (label) label.textContent = '试听: ' + name;
                        // 用户点击播放按钮时开始播放（保留 user gesture）
                        audioEl.onplay = function() {
                            showToast("试听播放中: " + name, "success", 3000);
                        };
                        audioEl.onended = function() {
                            URL.revokeObjectURL(url);
                            setTimeout(function() { player.style.display = 'none'; }, 500);
                        };
                    }
                } else {
                    if (player) player.style.display = 'none';
                    showToast("试听失败: " + (data.message || "未知错误"), "error", 5000);
                }
            }).catch(function(err) {
                if (player) player.style.display = 'none';
                showToast("试听请求失败: " + err.message, "error", 5000);
            });
        };

        // ===== 官方精品音色使用功能 =====
        window.useSpeaker = function(key) {
            // 更新选中状态
            document.querySelectorAll('.speaker-card').forEach(function(card) {
                card.classList.remove('selected');
            });
            var target = document.querySelector('.speaker-card[data-speaker="' + key + '"]');
            if (target) target.classList.add('selected');
            // 更新桥接 Textbox（触发 Python 端 change 事件）
            var bridgeInput = document.querySelector('#speaker-bridge-input textarea, #speaker-bridge-input input');
            if (bridgeInput) {
                bridgeInput.value = key;
                bridgeInput.dispatchEvent(new Event('input', {bubbles: true}));
            }
            // 更新详情面板
            var info = window.SPEAKER_INFO || {};
            var s = info[key] || ["", "", "", ""];
            var detailContainer = document.getElementById('speaker-detail-container');
            if (detailContainer) {
                detailContainer.innerHTML = '<div class="speaker-detail-panel">' +
                    '<h3>🎙️ ' + s[0] + ' (' + key + ')</h3>' +
                    '<div class="detail-row"><span class="detail-label">音色类型</span><span class="detail-value">' + s[2] + '</span></div>' +
                    '<div class="detail-row"><span class="detail-label">声音特点</span><span class="detail-value">' + s[3] + '</span></div>' +
                    '<div class="detail-row"><span class="detail-label">详细说明</span><span class="detail-value">' + s[1] + '</span></div>' +
                    '</div>';
            }
            showToast("已选择音色: " + (s[0] || key), "success", 2000);
        };