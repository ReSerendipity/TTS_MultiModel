# -*- coding: utf-8 -*-
"""Gradio UI 构建：run_integrated 主函数"""

import os
import re
import time
import logging

import gradio as gr

from ..config import (
    SAVE_DIR, PERSONA_DIR, OFFICIAL_SPEAKERS, OFFICIAL_SPEAKER_INFO,
    _OFFICIAL_SPEAKERS_ORDERED, _OFFICIAL_DISPLAY_NAMES, _LANGS,
    MODEL_TYPE_ALIASES, _PERSONA_NAME_RE,
)
from ..exceptions import TTSError, InsufficientVRAMError, EngineSwitchError
from ..model_manager import (
    load_model, unload_model, switch_engine, load_voxcpm2,
    current_model, current_type, current_size, current_engine,
    voxcpm_model, voxcpm_asr,
    _check_model_ready, _gen_tracker, _progress_mgr,
    _persona_embedding_cache,
)
from ..generation import save_audio, preprocess_and_save_temp
from ..persona_manager import (
    fn_save_persona, get_persona_list, get_total_persona_count,
    get_persona_detail_table, get_persona_desc, load_persona_embedding,
    get_persona_map,
)
from ..engines.qwen3tts_engine import (
    fn_voice_design, fn_voice_clone, fn_voice_clone_with_persona,
    fn_custom_voice, fn_custom_voice_v2, fn_script_studio,
)
from ..engines.voxcpm2_engine import (
    fn_voxcpm_design, fn_voxcpm_clone, fn_voxcpm_ultimate_clone,
    fn_voxcpm_script_studio,
)
from ..utils import (
    cleanup_temp_files as _cleanup_temp_files,
    get_role_color, add_tag, generate_speaker_card_grid,
    get_generation_history, get_total_history_count,
    get_generation_history_enhanced, get_history_table_data,
)
from ..i18n import I18N

logger = logging.getLogger("tts_multimodel")

_UI_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_css():
    """从文件加载 CSS 样式"""
    css_path = os.path.join(_UI_DIR, "styles.css")
    with open(css_path, "r", encoding="utf-8") as f:
        return f.read()

def _load_js():
    """从文件加载 JavaScript"""
    js_path = os.path.join(_UI_DIR, "scripts.js")
    with open(js_path, "r", encoding="utf-8") as f:
        return f.read()

def run_integrated(ip, port):
    with gr.Blocks(
        title="TTS MultiModel 语音工坊",
        head="<style>" + _load_css() + "</style>",
        js=_load_js()
    ) as demo:
        # 语言切换（通过 URL 参数控制）
        # lang_state 已移除（未使用）
        
        # 简洁导航栏
        gr.HTML('<div class="simple-nav">'
                '<div class="nav-brand"><span class="nav-icon"></span> TTS MultiModel</div>'
                '<div class="nav-badges">'
                '<span class="nav-badge"><span class="status-dot"></span> <span data-i18n="nav_status">双引擎就绪 · 等待输入</span></span>'
                '<span class="nav-badge engine-status-badge"><span class="engine-dot"></span><span data-i18n="nav_multi_engine">多引擎支持</span></span>'
                '</div></div>')
        # 引擎切换区
        with gr.Row(elem_id="engine-selector-row", equal_height=True):
            with gr.Column(scale=3):
                engine_selector = gr.Radio(
                    choices=["Qwen3TTS 1.7B", "Qwen3TTS 0.6B", "VoxCPM2"],
                    value="Qwen3TTS 1.7B",
                    label=I18N("engine_selector"),
                    elem_id="engine-radio"
                )
                gr.HTML('<div class="engine-warning">切换需等待约20秒，请勿频繁操作</div>')
            with gr.Column(scale=1):
                engine_status_display = gr.Textbox(
                    label=I18N("engine_status"),
                    value="Qwen3TTS 1.7B | 就绪",
                    interactive=False,
                    elem_id="engine-status-textbox",
                    max_lines=1
                )
        # 系统状态栏
        status_bar = gr.Markdown(value='<span class="status-pulse"></span> **引擎就绪 · 等待输入** | ' + _gen_tracker.status_text(), elem_id="status-bar")
        output_format = gr.Radio(["wav", "mp3"], label=I18N("output_format"), value="wav", scale=0, min_width=160)
        with gr.Group(elem_classes=["progress-container"], visible=True):
            progress_bar = gr.Markdown(value="", elem_id="progress-bar")
        with gr.Tabs(elem_classes=["enhanced-tabs"]) as main_tabs:
            # Tab 1: 声音设计
            with gr.Tab(I18N("tab_voice_design"), id="声音设计"):
                with gr.Column():
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="pen-line"></span><h3 class="card-header-title">输入设置</h3></div>')
                        txt = gr.Textbox(label=I18N("synthesis_text"), value="哥哥，你回来啦，人家等了你好久好久了，要抱抱！", lines=3, placeholder="请输入需要合成的文本...", elem_classes=["tts-input-textbox"])
                        lan = gr.Dropdown(_LANGS, label=I18N("language"), value="Auto", elem_classes=["tts-input-dropdown"])
                        with gr.Tabs(elem_classes=["inner-tabs"]):
                            with gr.Tab(I18N("preset_create")):
                                ins = gr.Textbox(label=I18N("voice_description"), placeholder="如：极度撒娇的萝莉音，带有明显的鼻音和撒娇语气", lines=1)
                                gr.HTML('<div id="voice-preset-tags" class="voice-preset-tags">'
                                        '<span class="preset-tag" data-value="萝莉音">萝莉音</span>'
                                        '<span class="preset-tag" data-value="御姐音">御姐音</span>'
                                        '<span class="preset-tag" data-value="磁性男声">磁性男声</span>'
                                        '<span class="preset-tag" data-value="低音炮">低音炮</span>'
                                        '<span class="preset-tag" data-value="少年音">少年音</span>'
                                        '<span class="preset-tag" data-value="日系甜音">日系甜音</span>'
                                        '</div>')
                                btn = gr.Button(I18N("generate_btn"), variant="primary", elem_classes=["primary-btn", "generate-btn"])
                                gr.HTML('<div style="text-align:center;margin-top:-8px;margin-bottom:8px;"><span class="kbd">Ctrl+Enter</span></div>')
                                with gr.Row():
                                    p_n = gr.Textbox(label=I18N("save_name"), placeholder="输入音色名称用于固化", scale=3)
                                    s_b = gr.Button(I18N("save_persona"), elem_classes=["secondary-btn", "icon-btn"], scale=1)
                                confirm_overwrite_b = gr.Button("确认覆盖", variant="stop", visible=False, elem_classes=["btn-danger"])
                            with gr.Tab(I18N("saved_voices")):
                                persona_d = gr.Dropdown(label=I18N("select_persona"), choices=get_persona_list(include_official=True), value=I18N("no_persona"), interactive=True)
                                desc_d = gr.Markdown(value="")
                                with gr.Row():
                                    btn_ref_d = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"])
                                    btn_d = gr.Button(I18N("use_selected"), variant="primary", elem_classes=["primary-btn"])
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="volume-2"></span><h3 class="card-header-title">输出结果</h3></div>')
                        aud = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"], type="filepath", sources=None, interactive=False)
                        msg = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                btn.click(fn_voice_design, [txt, lan, ins, output_format], [aud, msg])
                s_b.click(fn_save_persona, [p_n, aud, txt], [msg, confirm_overwrite_b])
                confirm_overwrite_b.click(fn=lambda n, a, t: fn_save_persona(n, a, t, overwrite=True), inputs=[p_n, aud, txt], outputs=[msg, confirm_overwrite_b])
                def update_desc_d(name):
                    if not name or name == "(暂无音色)": return ""
                    real = name
                    if name.startswith("[官方]"):
                        m = re.search(r'\((\w+)\)$', name); real = m.group(1) if m else name.replace("[官方] ", "").split(" (")[0]
                    return get_persona_desc(real)
                persona_d.change(update_desc_d, [persona_d], [desc_d])
                btn_ref_d.click(lambda: gr.update(choices=get_persona_list(include_official=True)), None, persona_d)
                btn_d.click(fn_voice_clone_with_persona, [txt, lan, persona_d, gr.State("1.7B")], [aud, msg])
            # Tab 2: 语音克隆
            with gr.Tab(I18N("tab_voice_clone"), id="语音克隆"):
                with gr.Column():
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="dna"></span><h3 class="card-header-title">克隆设置</h3></div>')
                        size_c = gr.Radio(["1.7B", "0.6B"], label=I18N("model_size"), value="1.7B")
                        txt_c = gr.Textbox(label=I18N("synthesis_text"), value="你好，这是我的克隆声音。", lines=3, placeholder="请输入需要合成的文本...", elem_classes=["tts-input-textbox"])
                        lan_c = gr.Dropdown(_LANGS, label=I18N("language"), value="Auto", elem_classes=["tts-input-dropdown"])
                        with gr.Tabs(elem_classes=["inner-tabs"]):
                            with gr.Tab(I18N("saved_voices")):
                                persona_c = gr.Dropdown(label=I18N("select_persona"), choices=get_persona_list(include_official=True), value=I18N("no_persona"), interactive=True)
                                desc_c = gr.Markdown(value="")
                                with gr.Row():
                                    btn_ref_p = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"])
                            with gr.Tab("上传新参考"):
                                ref_a = gr.Audio(label=I18N("ref_audio"), type="filepath")
                                ref_t = gr.Textbox(label=I18N("ref_text"), placeholder="请输入参考音频对应的文字内容...", lines=2)
                        btn_c = gr.Button(I18N("clone_btn"), variant="primary", elem_classes=["primary-btn", "generate-btn"])
                        with gr.Row():
                            p_nc = gr.Textbox(label=I18N("save_name"), placeholder="输入音色名称用于固化", scale=3)
                            s_bc = gr.Button(I18N("save_persona"), elem_classes=["secondary-btn", "icon-btn"], scale=1)
                        confirm_overwrite_bc = gr.Button("确认覆盖", variant="stop", visible=False, elem_classes=["btn-danger"])
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="volume-2"></span><h3 class="card-header-title">输出结果</h3></div>')
                        aud_c = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"], type="filepath", sources=None, interactive=False)
                        msg_c = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                def update_desc_c(name):
                    if not name or name == "(暂无音色)": return ""
                    real = name
                    if name.startswith("[官方]"):
                        m = re.search(r'\((\w+)\)$', name); real = m.group(1) if m else name.replace("[官方] ", "").split(" (")[0]
                    return get_persona_desc(real)
                persona_c.change(update_desc_c, [persona_c], [desc_c])
                btn_ref_p.click(lambda: gr.update(choices=get_persona_list(include_official=True)), None, persona_c)
                btn_c.click(fn_voice_clone_with_persona, [txt_c, lan_c, persona_c, size_c, output_format], [aud_c, msg_c])
                s_bc.click(fn_save_persona, [p_nc, ref_a, ref_t], [msg_c, confirm_overwrite_bc])
                confirm_overwrite_bc.click(fn=lambda n, a, t: fn_save_persona(n, a, t, overwrite=True), inputs=[p_nc, ref_a, ref_t], outputs=[msg_c, confirm_overwrite_bc])
            # Tab 3: 官方精品（卡片网格展示）
            with gr.Tab(I18N("tab_official"), id="官方精品"):
                with gr.Column():
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="star"></span><h3 class="card-header-title">官方精品音色</h3></div>')
                        size_v = gr.Radio(["1.7B", "0.6B"], label=I18N("model_size"), value="1.7B", elem_classes=["model-size-radio"])
                        txt_v = gr.TextArea(label=I18N("official_text_area"), lines=6, placeholder="普通文本直接使用上方音色选择，或使用 [角色名][情感指令]内容 格式生成对话...", elem_classes=["tts-input-textarea"])
                        lan_v = gr.Dropdown(_LANGS, label=I18N("language"), value="Auto", elem_classes=["tts-input-dropdown"])
                        # 音色筛选栏
                        gr.HTML('<div class="filter-bar">'
                            '<span class="filter-bar-label" data-i18n="filter_label">筛选:</span>'
                            '<span class="filter-chip active" data-filter="all" onclick="filterSpeaker(\'all\')" data-i18n="all">全部</span>'
                            '<span class="filter-chip" data-filter="female" onclick="filterSpeaker(\'female\')" data-i18n="female">女声</span>'
                            '<span class="filter-chip" data-filter="male" onclick="filterSpeaker(\'male\')" data-i18n="male">男声</span>'
                            '<span class="filter-chip" data-filter="sweet" onclick="filterSpeaker(\'sweet\')" data-i18n="sweet">甜美</span>'
                            '<span class="filter-chip" data-filter="mature" onclick="filterSpeaker(\'mature\')" data-i18n="mature">成熟</span>'
                            '<span class="filter-chip" data-filter="deep" onclick="filterSpeaker(\'deep\')" data-i18n="deep">低沉</span>'
                            '</div>')
                    # 音色卡片网格
                    speaker_grid_html = gr.HTML(value=generate_speaker_card_grid("Vivian"), elem_id="speaker-card-container")
                    # 隐藏的选中音色桥接组件（JS -> Python）
                    speaker_bridge = gr.Textbox(value="Vivian", elem_id="speaker-bridge-input", visible=False)
                    # 隐藏的选中音色值
                    selected_speaker_key = gr.State(value="Vivian")
                    # 音色详情面板
                    speaker_detail_html = gr.HTML(
                        value='<div class="speaker-detail-panel">'
                              '<h3>🎙️ 薇薇安 (Vivian)</h3>'
                              '<div class="detail-row"><span class="detail-label">音色类型</span><span class="detail-value">少女音</span></div>'
                              '<div class="detail-row"><span class="detail-label">声音特点</span><span class="detail-value">年轻活泼，语速轻快</span></div>'
                              '<div class="detail-row"><span class="detail-label">详细说明</span><span class="detail-value">甜美少女音，活泼热情，适合年轻女性角色配音。擅长日常对话和情感表达。</span></div>'
                              '</div>',
                        elem_id="speaker-detail-container"
                    )
                    # 试听音频播放器
                    preview_audio_html = gr.HTML(
                        value='<div id="speaker-preview-player" style="display:none;margin:12px 0;padding:12px;background:rgba(20,20,40,0.8);border-radius:10px;border:1px solid rgba(139,92,246,0.3);">'
                              '<div style="color:#a5b4fc;font-size:12px;margin-bottom:8px;" id="preview-label">试听中...</div>'
                              '<audio id="preview-audio" controls style="width:100%;height:40px;"></audio>'
                              '</div>',
                        elem_id="speaker-preview-container"
                    )
                    with gr.Tabs(elem_classes=["inner-tabs"]):
                        with gr.Tab(I18N("saved_voices")):
                            persona_v = gr.Dropdown(label=I18N("select_persona"), choices=get_persona_list(), value=I18N("no_persona"), interactive=True)
                            desc_v = gr.Markdown(value="")
                            with gr.Row():
                                btn_ref_v = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"])
                    btn_v = gr.Button(I18N("official_btn"), variant="primary", elem_classes=["primary-btn", "generate-btn"])
                    gr.HTML('<div style="text-align:center;margin-top:-8px;margin-bottom:8px;"><span class="kbd">Ctrl+Enter</span></div>')
                    with gr.Group(elem_classes=["card"]):
                        gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="volume-2"></span><h3 class="card-header-title">输出结果</h3></div>')
                        aud_v = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"], type="filepath", sources=None, interactive=False)
                        msg_v = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                # 官方精品事件绑定
                def update_speaker_detail(key):
                    """更新音色详情面板"""
                    info = OFFICIAL_SPEAKER_INFO.get(key, ("", "", "", ""))
                    return f'''<div class="speaker-detail-panel">
    <h3>🎙️ {info[0]} ({key})</h3>
    <div class="detail-row"><span class="detail-label">音色类型</span><span class="detail-value">{info[2]}</span></div>
    <div class="detail-row"><span class="detail-label">声音特点</span><span class="detail-value">{info[3]}</span></div>
    <div class="detail-row"><span class="detail-label">详细说明</span><span class="detail-value">{info[1]}</span></div>
</div>'''
                def update_speaker_info_v2(choice):
                    match = re.search(r'\((\w+)\)$', choice); key = match.group(1) if match else choice
                    info = OFFICIAL_SPEAKER_INFO.get(key, ("", "", "", ""))
                    return f"🎙️ **{info[0]} ({key})**\n\n**音色类型**：{info[2]}\n**声音特点**：{info[3]}\n\n**详细说明**：{info[1]}"
                def add_official_tag_v2(text, speaker):
                    match = re.search(r'\((\w+)\)$', speaker); s = match.group(1) if match else speaker
                    if not text.strip(): return text
                    return f"{text.rstrip()}\n[{s}] "
                def update_desc_v(name):
                    if not name or name == "(暂无音色)": return ""
                    return get_persona_desc(name)
                persona_v.change(update_desc_v, [persona_v], [desc_v])
                btn_ref_v.click(lambda: gr.update(choices=get_persona_list()), None, persona_v)
                # 卡片点击 -> 桥接 Textbox -> 同步 selected_speaker_key + 更新详情面板
                speaker_bridge.change(lambda x: (x, update_speaker_detail(x)), [speaker_bridge], [selected_speaker_key, speaker_detail_html])
                btn_v.click(fn_custom_voice_v2, [txt_v, lan_v, selected_speaker_key, gr.State(""), size_v, persona_v], [aud_v, msg_v])
            # Tab 4: 剧本工坊
            with gr.Tab(I18N("tab_script"), id="剧本工坊"):
                with gr.Row(equal_height=False):
                    with gr.Column(scale=2):
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="scroll"></span><h3 class="card-header-title">剧本编辑器</h3></div>')
                                size_s = gr.Radio(["1.7B", "0.6B"], label=I18N("model_size"), value="1.7B")
                                script = gr.TextArea(label=I18N("script_content"), lines=12, value="[御姐] 欢迎！\n[旁白] 这里是多人剧本模式。", placeholder="格式: [音色名称] 台词内容\n每行一个角色，使用方括号标记说话人...", elem_classes=["tts-input-textarea"])
                                lan_s = gr.Dropdown(_LANGS, label=I18N("language"), value="Auto", elem_classes=["tts-input-dropdown"])
                                btn_s = gr.Button("🎬 开始合成长剧本", variant="primary", elem_classes=["primary-btn", "generate-btn"])
                    with gr.Column(scale=1, min_width=280, elem_classes=["output-sidebar"]):
                        with gr.Group(elem_classes=["card"]):
                            gr.HTML('<div class="card-header"><span class="card-header-icon">🎭</span><h3 class="card-header-title">快速插入音色</h3></div>')
                            with gr.Tabs(elem_classes=["inner-tabs"]):
                                with gr.Tab(I18N("custom_voice")):
                                    p_list = gr.Dropdown(label=I18N("saved_voices"), choices=get_persona_list(), interactive=True)
                                with gr.Tab(I18N("official_voice_tab")):
                                    p_list_official = gr.Dropdown(label=I18N("official_voice_tab"), choices=_OFFICIAL_DISPLAY_NAMES, interactive=True)
                            btn_ref = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"])
                            aud_s = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"], type="filepath", sources=None, interactive=False)
                            msg_s = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                # 音色插入后自动聚焦剧本编辑器
                script_focus_html = gr.HTML(visible=False)
                def add_tag_and_focus(text, tag, is_speaker=True):
                    tag_text = f"[{tag}] "
                    js_code = '<script>setTimeout(function(){var ta=document.querySelector("#剧本工坊 textarea, [data-testid*=\\"script\\"] textarea");if(ta){var start=ta.selectionStart;var end=ta.selectionEnd;var v=ta.value;ta.value=v.substring(0,start)+\"' + tag_text.replace('"', '\\"') + '\"+v.substring(end);ta.selectionStart=ta.selectionEnd=start+' + str(len(tag_text)) + ';ta.focus();ta.dispatchEvent(new Event("input",{bubbles:true}));}},100);</script>'
                    return text, js_code
                p_list.input(lambda t, r: add_tag_and_focus(t, r, True), [script, p_list], [script, script_focus_html])
                p_list_official.input(lambda t, r: add_tag_and_focus(t, r, True), [script, p_list_official], [script, script_focus_html])
                btn_ref.click(lambda: gr.update(choices=get_persona_list()), None, p_list)
                btn_s.click(fn_script_studio, [script, lan_s, size_s], [aud_s, msg_s])
            # Tab 5: VoxCPM2 (contains 3 sub-tabs)
            with gr.Tab(I18N("tab_voxcpm2"), id="VoxCPM2"):
                with gr.Tabs(elem_classes=["inner-tabs"]):
                    # Sub-tab 5.1: VoxCPM2 声音设计
                    with gr.Tab(I18N("voxcpm_design")):
                        with gr.Column():
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="pen-line"></span><h3 class="card-header-title">VoxCPM2 声音设计</h3></div>')
                                vox_design_txt = gr.Textbox(label=I18N("synthesis_text_vox"), value="你好，这是我用 VoxCPM2 生成的声音。", lines=3, placeholder="请输入需要合成的文本...")
                                vox_design_ins = gr.Textbox(label=I18N("control_instruction"), value="用温暖亲切的语气说话", lines=2, placeholder="如：用温暖亲切的语气说话、带有兴奋的情感、缓慢而沉稳的语速...")
                                vox_design_btn = gr.Button(I18N("generate_btn"), variant="primary", elem_classes=["primary-btn", "generate-btn"])
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="volume-2"></span><h3 class="card-header-title">输出结果</h3></div>')
                                vox_design_aud = gr.Audio(label=I18N("result_audio"), type="filepath", sources=None, interactive=False)
                                vox_design_msg = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                        vox_design_btn.click(fn_voxcpm_design, [vox_design_txt, vox_design_ins], [vox_design_aud, vox_design_msg])
                    # Sub-tab 5.2: VoxCPM2 可控克隆
                    with gr.Tab(I18N("voxcpm_clone")):
                        with gr.Column():
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="dna"></span><h3 class="card-header-title">可控克隆设置</h3></div>')
                                vox_clone_txt = gr.Textbox(label=I18N("synthesis_text_vox"), value="你好，这是我的克隆声音。", lines=3, placeholder="请输入需要合成的文本...")
                                vox_clone_ins = gr.Textbox(label=I18N("control_instruction"), value="用温暖亲切的语气说话", lines=2, placeholder="如：用温暖亲切的语气说话、带有兴奋的情感...")
                                with gr.Tabs(elem_classes=["inner-tabs"]):
                                    with gr.Tab(I18N("saved_voices")):
                                        vox_clone_persona = gr.Dropdown(label=I18N("select_persona"), choices=get_persona_list(include_official=True), value=I18N("no_persona"), interactive=True)
                                        vox_clone_persona_desc = gr.Markdown(value="")
                                        with gr.Row():
                                            vox_clone_persona_ref = gr.Button(I18N("save_name"), elem_classes=["secondary-btn"])
                                    with gr.Tab(I18N("ref_audio")):
                                        vox_clone_ref = gr.Audio(label=I18N("ref_audio"), type="filepath")
                                        vox_clone_ref_txt = gr.Textbox(label=I18N("ref_text"), placeholder="请输入参考音频对应的文字内容...", lines=2)
                                vox_clone_btn = gr.Button(I18N("generate_btn"), variant="primary", elem_classes=["primary-btn", "generate-btn"])
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="volume-2"></span><h3 class="card-header-title">输出结果</h3></div>')
                                vox_clone_aud = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"], type="filepath", sources=None, interactive=False)
                                vox_clone_msg = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                        def update_vox_clone_persona(name):
                            if not name or name == "(暂无音色)": return ""
                            real = name.split(" (", 1)[0] if " (" in name else name
                            wav_path = os.path.join(PERSONA_DIR, f"{real}.wav")
                            txt_path = os.path.join(PERSONA_DIR, f"{real}.txt")
                            if os.path.exists(wav_path):
                                vox_clone_persona_ref.click(lambda: wav_path, None, vox_clone_ref)
                            if os.path.exists(txt_path):
                                try:
                                    with open(txt_path, "r", encoding="utf-8") as f: return f.read()
                                except: pass
                            return ""
                        vox_clone_persona.change(update_vox_clone_persona, [vox_clone_persona], [vox_clone_persona_desc])
                        vox_clone_btn.click(fn_voxcpm_clone, [vox_clone_txt, vox_clone_ins, vox_clone_ref], [vox_clone_aud, vox_clone_msg])
                    # Sub-tab 5.3: VoxCPM2 极致克隆
                    with gr.Tab(I18N("voxcpm_ultimate")):
                        with gr.Column():
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon">🔬</span><h3 class="card-header-title">极致克隆设置</h3></div>')
                                vox_ulti_txt = gr.Textbox(label=I18N("synthesis_text_vox"), value="你好，这是我的声音。", lines=3, placeholder="请输入需要合成的文本...")
                                vox_ulti_ins = gr.Textbox(label=I18N("control_instruction"), value="", lines=2, placeholder="如：用温暖亲切的语气说话...")
                                vox_ulti_ref = gr.Audio(label=I18N("ref_audio"), type="filepath")
                                gr.Markdown("### 高级设置")
                                with gr.Accordion(I18N("advanced_settings"), open=False):
                                    with gr.Row():
                                        vox_ulti_cfg = gr.Slider(minimum=0.5, maximum=2.0, value=1.2, step=0.1, label=I18N("cfg_value"))
                                        vox_ulti_steps = gr.Slider(minimum=2, maximum=10, value=6, step=1, label=I18N("locdit_steps"))
                                    with gr.Row():
                                        vox_ulti_denoise = gr.Slider(minimum=0.0, maximum=1.0, value=1.0, step=0.1, label=I18N("denoise_strength"))
                                        vox_ulti_norm = gr.Checkbox(value=True, label=I18N("text_normalize"))
                                    vox_ulti_seed = gr.Slider(minimum=0, maximum=4294967295, value=0, step=1, label=I18N("randomness"), info="0为随机，其他值为固定种子")
                                vox_ulti_btn = gr.Button(I18N("generate_ultimate"), variant="primary", elem_classes=["primary-btn"])
                            with gr.Group(elem_classes=["card"]):
                                gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="volume-2"></span><h3 class="card-header-title">输出结果</h3></div>')
                                vox_ulti_aud = gr.Audio(label=I18N("result_audio"), elem_classes=["tts-audio-player"], type="filepath", sources=None, interactive=False)
                                vox_ulti_msg = gr.Textbox(label=I18N("status"), lines=1, interactive=False)
                                vox_ulti_ref_text_display = gr.Markdown(value="")
                        vox_ulti_btn.click(fn_voxcpm_ultimate_clone,
                            [vox_ulti_txt, vox_ulti_ins, vox_ulti_ref, vox_ulti_cfg, vox_ulti_norm, vox_ulti_denoise, vox_ulti_steps, vox_ulti_seed],
                            [vox_ulti_aud, vox_ulti_ref_text_display])
            # Tab 6: 历史记录（增强筛选和试听）
            with gr.Tab(I18N("tab_history")):
                with gr.Group(elem_classes=["card"]):
                    gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="history"></span><h3 class="card-header-title">生成历史</h3></div>')
                    total_count = get_total_history_count()
                    if total_count == 0:
                        gr.HTML('<div class="empty-state">'
                                '<span class="empty-state-icon">📭</span>'
                                '<p class="empty-state-text" data-i18n="history_empty_text">暂无生成记录</p>'
                                '<p style="font-size:13px;margin-bottom:16px;" data-i18n="history_empty_hint">合成音频后，历史记录将自动显示在这里</p>'
                                '<div class="empty-state-action">'
                                '<button class="secondary-btn" onclick="document.querySelector(\'[data-testid="🎨 声音设计"]\').click()" data-i18n="history_first_btn">🎨 开始首次合成</button>'
                                '</div></div>')
                    else:
                        # 改进的数量统计
                        gr.HTML(f'<div class="stat-card">'
                                '<span class="stat-card-icon">📜</span>'
                                f'<div><div class="stat-card-value">{total_count}</div>'
                                '<div class="stat-card-label">条历史记录</div></div></div>')
                    # 搜索和筛选栏
                    gr.HTML('<div class="history-filters">'
                            '<span class="filter-bar-label" data-i18n="time_filter">时间:</span>'
                            '<span class="time-filter-chip active" data-time="all" onclick="filterHistoryTime(\'all\')" data-i18n="all">全部</span>'
                            '<span class="time-filter-chip" data-time="today" onclick="filterHistoryTime(\'today\')" data-i18n="today">今天</span>'
                            '<span class="time-filter-chip" data-time="week" onclick="filterHistoryTime(\'week\')" data-i18n="week">本周</span>'
                            '<span class="time-filter-chip" data-time="month" onclick="filterHistoryTime(\'month\')" data-i18n="month">本月</span>'
                            '</div>')
                    with gr.Row():
                        search_box = gr.Textbox(label=I18N("search_file"), placeholder="输入关键词进行模糊匹配...", lines=1, scale=4)
                        time_filter_hidden = gr.State(value="all")
                        with gr.Column(scale=1, min_width=200):
                            history_btn = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"])
                            clear_btn = gr.Button(I18N("clear_search"), elem_classes=["stop-btn"])
                    history_info = gr.Markdown(value="")
                    history_df = gr.Dataframe(
                        headers=["文件名", "生成时间", "时长", "大小"],
                        value=get_history_table_data(),
                        interactive=False
                    )
                    # 批量操作栏
                    gr.HTML('<div class="history-batch-bar">'
                            '<input type="checkbox" class="history-checkbox" id="select-all-history" onclick="toggleAllHistory(this.checked)">'
                            '<span style="font-size:12px;color:var(--text-muted);" data-i18n="select_all">全选</span>'
                            '<span style="flex:1"></span>'
                            '<button class="secondary-btn" style="font-size:11px;padding:4px 8px;" onclick="batchExportHistory()" data-i18n="batch_export">📦 批量导出</button>'
                            '<button class="stop-btn" style="font-size:11px;padding:4px 8px;" onclick="batchDeleteHistory()" data-i18n="batch_delete">🗑️ 批量删除</button>'
                            '</div>')
                    def search_history(keyword, time_filter):
                        results = get_history_table_data(keyword, time_filter)
                        count = len(results)
                        if results == [["暂无记录", "-", "-", "-"]]:
                            info = f"🔍 **无匹配结果** — 未找到包含 `{keyword}` 的文件" if keyword else ""
                        else:
                            info = f"🔍 找到 **{count}** 条匹配记录" if keyword else f"共 **{count}** 条记录"
                        return results, info
                    def clear_search():
                        return "", "all", get_history_table_data(), ""
                    search_box.input(lambda kw, tf: search_history(kw, tf), [search_box, time_filter_hidden], [history_df, history_info])
                    history_btn.click(lambda kw, tf: search_history(kw, tf), [search_box, time_filter_hidden], [history_df, history_info])
                    clear_btn.click(clear_search, None, [search_box, time_filter_hidden, history_df, history_info])
            # Tab 7: 音色库管理（增强试听和视图切换）
            with gr.Tab(I18N("tab_persona")):
                with gr.Group(elem_classes=["card"]):
                    gr.HTML('<div class="card-header"><span class="card-header-icon" data-icon="mic"></span><h3 class="card-header-title">音色库详情</h3></div>')
                    total_persona = get_total_persona_count()
                    if total_persona == 0:
                        gr.HTML('<div class="empty-state">'
                                '<span class="empty-state-icon">🎙️</span>'
                                '<p class="empty-state-text" data-i18n="persona_empty_text">暂无自定义音色</p>'
                                '<p style="font-size:13px;margin-bottom:16px;" data-i18n="persona_empty_hint">在"声音设计"或"语音克隆"中保存音色后，将显示在这里</p>'
                                '<div class="empty-state-action">'
                                '<button class="secondary-btn" onclick="document.querySelector(\'[data-testid="🎨 声音设计"]\').click()" data-i18n="persona_first_btn">🎨 创建首个音色</button>'
                                '</div></div>')
                    else:
                        # 改进的数量统计
                        gr.HTML(f'<div class="stat-card">'
                                '<span class="stat-card-icon">🎙️</span>'
                                f'<div><div class="stat-card-value">{total_persona}</div>'
                                '<div class="stat-card-label">个自定义音色</div></div></div>')
                    # 搜索和视图切换
                    with gr.Row():
                        persona_search = gr.Textbox(label=I18N("search_persona"), placeholder="输入关键词进行模糊匹配...", lines=1, scale=4)
                        with gr.Column(scale=1, min_width=200):
                            gr.HTML('<div style="display:flex;align-items:center;gap:8px;">'
                                    '<div class="view-toggle">'
                                    '<span class="view-toggle-btn active" data-view="list" onclick="switchVoiceView(\'list\')" data-i18n="list">☰ 列表</span>'
                                    '<span class="view-toggle-btn" data-view="card" onclick="switchVoiceView(\'card\')" data-i18n="card">⊞ 卡片</span>'
                                    '</div></div>')
                    with gr.Row():
                        persona_search_btn = gr.Button("🔍 搜索", variant="primary", elem_classes=["primary-btn"], scale=1)
                        persona_clear_btn = gr.Button(I18N("clear_search"), elem_classes=["stop-btn"], scale=1)
                        btn_refresh_persona = gr.Button(I18N("refresh_list"), elem_classes=["secondary-btn"], scale=1)
                    persona_search_info = gr.Markdown(value="")
                    # 列表视图
                    persona_df = gr.Dataframe(
                        headers=["音色名称", "固化状态", "音频大小", "创建时间", "参考文本"],
                        value=get_persona_detail_table(),
                        interactive=True,
                        elem_id="persona-list-view"
                    )
                    # 卡片视图（默认隐藏）
                    persona_card_grid = gr.HTML(value="", visible=False, elem_id="persona-card-view")
                    with gr.Row():
                        selected_persona = gr.Textbox(label=I18N("current_persona"), interactive=False)
                        preview_audio = gr.Audio(label=I18N("preview"), interactive=False)
                    with gr.Row():
                        btn_play = gr.Button(I18N("play_btn"), elem_classes=["secondary-btn"])
                        btn_delete = gr.Button(I18N("delete_btn"), elem_classes=["stop-btn"])
                    delete_status = gr.Markdown(value="")
                def on_persona_row_select(evt):
                    if evt and evt.value and len(evt.value) > 0:
                        return evt.value[0]
                    return ""
                def play_persona(name):
                    if not name or name == "暂无音色":
                        return None, "❌ 未选择有效音色"
                    wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
                    if not os.path.exists(wav_path):
                        return None, f"❌ 音频文件不存在: {name}"
                    try:
                        wav, sr = sf.read(wav_path)
                        return (sr, wav), f"🎵 正在播放: {name}"
                    except Exception as e:
                        return None, f"❌ 播放失败: {e}"
                def do_delete_persona(name):
                    if not name or name == "暂无音色":
                        return "❌ 未选择有效音色"
                    
                    # 输入验证
                    valid, err_msg = _validate_persona_name(name)
                    if not valid:
                        return f"❌ {err_msg}"
                    
                    try:
                        for ext in [".wav", ".txt", ".pt"]:
                            p = os.path.join(PERSONA_DIR, f"{name}{ext}")
                            p_real = os.path.realpath(p)
                            # 验证路径在 PERSONA_DIR 内
                            if not p_real.startswith(os.path.realpath(PERSONA_DIR)):
                                return "❌ 非法路径"
                            if os.path.exists(p):
                                os.remove(p)
                        if name in _persona_embedding_cache:
                            del _persona_embedding_cache[name]
                        return f"✅ 音色 [{name}] 已删除"
                    except Exception as e:
                        logger.error(f"删除音色失败: {e}")
                        return f"❌ 删除失败: {e}"
                persona_df.select(on_persona_row_select, None, selected_persona)
                btn_play.click(play_persona, [selected_persona], [preview_audio, delete_status])
                def delete_and_refresh(name):
                    status = do_delete_persona(name)
                    table = get_persona_detail_table()
                    return status, table
                btn_delete.click(delete_and_refresh, [selected_persona], [delete_status, persona_df])
                def search_persona(keyword):
                    results = get_persona_detail_table(keyword); count = len(results)
                    if results == [["暂无音色", "-", "-", "-", "-"]]:
                        info = f"🔍 **无匹配结果** — 未找到包含 `{keyword}` 的音色" if keyword else ""
                    else:
                        info = f"🔍 找到 **{count}** 个匹配音色" if keyword else f"共 **{count}** 个音色"
                    return results, info
                def clear_persona_search():
                    return "", get_persona_detail_table(), ""
                persona_search.input(search_persona, [persona_search], [persona_df, persona_search_info])
                persona_search_btn.click(search_persona, [persona_search], [persona_df, persona_search_info])
                persona_clear_btn.click(clear_persona_search, None, [persona_search, persona_df, persona_search_info])
        def on_tab_select(evt):
            tab_id = evt.value if evt.value else ""
            try:
                if tab_id == "剧本工坊": load_model("语音克隆")
                elif tab_id: load_model(tab_id)
            except Exception: pass
        main_tabs.select(on_tab_select)
        # 引擎切换状态标记（防止定时器覆盖错误状态）
        engine_switch_error = [False]  # 使用列表作为可变标记
        def refresh_status():
            # 如果引擎切换出错，不要覆盖错误信息
            if engine_switch_error[0]:
                return gr.update()  # 不更新 status_bar
            return '<span class="status-pulse"></span> **双引擎就绪 · 等待输入** | ' + _gen_tracker.status_text()
        try:
            timer = gr.Timer(value=2); timer.tick(refresh_status, None, status_bar)
        except (TypeError, AttributeError): pass
        # 进度条定时器刷新
        def refresh_progress():
            html = _progress_mgr.get_progress_html()
            return html
        try:
            progress_timer = gr.Timer(value=0.5)
            progress_timer.tick(refresh_progress, None, progress_bar)
        except (TypeError, AttributeError): pass
        # 引擎切换事件绑定
        def on_engine_change(engine_name):
            try:
                qwen_size = "1.7B" if "1.7B" in engine_name else "0.6B" if "0.6B" in engine_name else "1.7B"
                final_status = None

                # 重置错误标记
                engine_switch_error[0] = False

                # 切换期间禁用生成按钮（通过 JS 注入）
                disable_js = '<script>document.querySelectorAll(".primary-btn").forEach(function(b){b.disabled=true;b.style.opacity="0.5";});</script>'

                # 逐次消费生成器，取最后一次状态
                # 注意：生成器内部已包含完整异常处理，这里只负责消费状态
                try:
                    for step_result in switch_engine(engine_name, qwen_size):
                        # 生成器每次 yield (status_text, extra1, extra2, extra3)
                        if isinstance(step_result, tuple) and len(step_result) >= 1:
                            final_status = step_result[0]
                            logger.info(f"[UI回调] 步骤状态: {final_status}")
                        else:
                            final_status = str(step_result) if step_result is not None else "未知状态"
                            logger.info(f"[UI回调] 步骤状态: {final_status}")
                except GeneratorExit:
                    pass

                if final_status is None:
                    final_status = f"{engine_name} 加载完成"

                # 切换完成，启用生成按钮
                enable_js = '<script>document.querySelectorAll(".primary-btn").forEach(function(b){b.disabled=false;b.style.opacity="";});</script>'

                # 检查是否是错误状态
                is_error = any(kw in str(final_status) for kw in ['失败', '错误', '异常', '不足', '不存在'])
                engine_status_val = f"{engine_name} | {'就绪' if not is_error and '就绪' in str(final_status) else '错误'}"
                logger.info(f"[UI回调] 最终状态: {final_status}, 引擎显示: {engine_status_val}, 是否错误: {is_error}")

                # 如果是错误状态，设置错误标志防止定时器覆盖
                if is_error:
                    engine_switch_error[0] = True
                    # 返回错误信息，并在 status_bar 中显示完整错误
                    return f"❌ {final_status}", engine_status_val, enable_js
                else:
                    return final_status, engine_status_val, enable_js

            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                error_msg = f"引擎切换异常: {type(e).__name__}: {e}\n\n详细堆栈:\n{tb}"
                logger.error(f"[UI回调] 异常: {error_msg}")
                engine_status_val = f"{engine_name} | 错误"
                engine_switch_error[0] = True
                enable_js = '<script>document.querySelectorAll(".primary-btn").forEach(function(b){b.disabled=false;b.style.opacity="";});</script>'
                return f"❌ {error_msg}", engine_status_val, enable_js
        engine_btn_state = gr.HTML(value="", elem_classes=["engine-btn-state"], visible=True)
        engine_selector.change(on_engine_change, [engine_selector], [status_bar, engine_status_display, engine_btn_state])

        gr.HTML('<div class="enhanced-footer">'
                '<div class="footer-grid">'
                '<div><p class="footer-brand" data-i18n="footer_brand">🎙️ AI 语音工坊 Pro</p>'
                '<p style="color:var(--text-muted);font-size:13px;line-height:1.6;" data-i18n="footer_desc">集成 Qwen3TTS 与 VoxCPM2 双引擎，提供专业级语音合成、声音设计与多人剧本编辑能力。</p></div>'
                '<div><p class="footer-title" data-i18n="footer_features">核心功能</p>'
                '<span class="footer-link" data-i18n="tab_voice_design">🎨 声音设计</span><span class="footer-link" data-i18n="tab_voice_clone">👥 语音克隆</span><span class="footer-link" data-i18n="tab_official">🌟 官方精品</span><span class="footer-link" data-i18n="tab_script">🎬 剧本工坊</span></div>'
                '<div><p class="footer-title" data-i18n="footer_tech">技术栈</p>'
                '<span class="footer-link">Qwen3TTS 引擎</span><span class="footer-link">VoxCPM2 引擎</span><span class="footer-link">CUDA Graph 加速</span><span class="footer-link">Gradio UI</span></div>'
                '<div><p class="footer-title" data-i18n="footer_links">链接</p>'
                '<a class="footer-link" href="https://qwen.ai/blog?id=qwen3tts-0115" target="_blank" data-i18n="footer_blog">Qwen3TTS 官方博客</a>'
                '<a class="footer-link" href="https://github.com/QwenLM" target="_blank">GitHub</a>'
                '<a class="footer-link" href="https://github.com/FunAudioLLM/VoxCPM" target="_blank">VoxCPM2 GitHub</a>'
                '<a class="footer-link" href="https://funaudiollm.github.io/" target="_blank">FunAudioLLM</a></div>'
                '</div>'
                '<div class="footer-bottom" data-i18n="footer_bottom">Powered by <strong>Qwen3TTS</strong> · VoxCPM2 · CUDA Graph 加速内核</div></div>')

    # Launch server - try HTTP first for local development compatibility
    try:
        app, _, _ = demo.launch(
            server_name=ip, server_port=int(port),
            prevent_thread_lock=True,
            i18n=I18N,
        )
    except Exception:
        # Fallback to HTTPS if HTTP fails
        cert_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "cert.pem")
        key_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "key.pem")
        
        # Try multiple possible cert paths
        cert_paths = [
            (cert_path, key_path),
            ("bin/cert.pem", "bin/key.pem"),
            (os.path.join(os.getcwd(), "bin", "cert.pem"), os.path.join(os.getcwd(), "bin", "key.pem")),
        ]
        
        launched = False
        for cert, key in cert_paths:
            if os.path.exists(cert) and os.path.exists(key):
                try:
                    app, _, _ = demo.launch(
                        server_name=ip, server_port=int(port),
                        ssl_certfile=cert, ssl_keyfile=key,
                        prevent_thread_lock=True,
                        i18n=I18N,
                    )
                    launched = True
                    break
                except Exception:
                    continue
        
        if not launched:
            raise RuntimeError("Failed to launch server with both HTTP and HTTPS")

    from ..api import register_api_endpoints
    register_api_endpoints(app)

    _cleanup_temp_files()

    while True:
        time.sleep(1)

