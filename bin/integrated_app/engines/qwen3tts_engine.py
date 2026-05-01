# -*- coding: utf-8 -*-
"""Qwen3-TTS 引擎：声音设计、语音克隆、官方精品、剧本工坊"""

import os
import re
import time
import logging

import torch
import numpy as np

from faster_qwen3_tts.generate import fast_generate

from ..config import PERSONA_DIR, OFFICIAL_SPEAKERS, OFFICIAL_SPEAKER_INFO, _OFFICIAL_SPEAKERS_LOWER
from ..exceptions import TTSError, PersonaError, GenerationError
from ..model_manager import (
    load_model, _check_model_ready, _gen_tracker, _progress_mgr,
)
from ..generation import (
    save_audio, split_text_for_tts, merge_audio_segments,
    preprocess_and_save_temp,
)
from ..utils import cleanup_temp_files
from ..persona_manager import load_persona_embedding

logger = logging.getLogger("tts_multimodel")


def fn_voice_clone_with_persona(text, lang, persona_name, size, output_format="wav", use_upload=False, ref_audio=None, ref_text=""):
    """使用已保存音色进行语音克隆，支持跨模式调用（含官方音色），支持长文本自动分割"""
    from ..exceptions import tts_error_handler

    @tts_error_handler
    def _wrapped(text, lang, persona_name, size, output_format="wav", use_upload=False, ref_audio=None, ref_text=""):
        _gen_tracker.start_generation()
        segments = split_text_for_tts(text)
        _progress_mgr.start(total_segments=len(segments), phase="加载模型中...")
        start_time = time.time()
        try:
            return _fn_voice_clone_with_persona_impl(text, lang, persona_name, size, output_format, use_upload, ref_audio, ref_text, start_time)
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.reset()
            cleanup_temp_files()
            logger.info(f"生成耗时 {elapsed:.1f} 秒")

    return _wrapped(text, lang, persona_name, size, output_format, use_upload, ref_audio, ref_text)


def _fn_voice_clone_with_persona_impl(text, lang, persona_name, size, output_format="wav", use_upload=False, ref_audio=None, ref_text="", start_time=0):
    if not persona_name or persona_name == "(暂无音色)":
        if use_upload and ref_audio is not None:
            model = load_model("语音克隆", size)
            tmp_path, _, _ = preprocess_and_save_temp(ref_audio)
            audio_list, sr = model.generate_voice_clone(text=text, language=lang, ref_audio=tmp_path, ref_text=ref_text)
            save_audio(audio_list[0], sr, f"clone_{size}")
            return (sr, audio_list[0]), f"完成！({size}核心，上传音频)"
        raise PersonaError("请先选择音色或上传参考音频")

    real_name = persona_name
    if persona_name.startswith("[官方]"):
        match = re.search(r'\((\w+)\)$', persona_name)
        real_name = match.group(1) if match else persona_name.replace("[官方] ", "").split(" (")[0]

    persona_data = load_persona_embedding(real_name)
    if persona_data is None:
        raise PersonaError(f"音色 [{real_name}] 文件不存在")

    vcp_data, wav_path, stored_ref_text = persona_data

    if wav_path == "__official__":
        model = load_model("官方精品", size)
        speaker_id = stored_ref_text.lower()
        segments = split_text_for_tts(text)
        audio_segments = []
        total = len(segments)
        for i, seg in enumerate(segments):
            elapsed = time.time() - start_time
            if i > 0:
                avg = elapsed / i
                remaining = avg * (total - i)
                logger.info(f"官方音色生成: 第 {i+1}/{total} 段，预计剩余 {remaining:.1f}s")
            _progress_mgr.advance_segment(f"第 {i+1}/{total} 段推理中...")
            al, sr = model.generate_custom_voice(text=seg, language=lang, speaker=speaker_id, instruct=None)
            audio_segments.append(al[0])
        merged, sr = merge_audio_segments(audio_segments, sr)
        if merged is None:
            raise GenerationError("官方音色生成失败")
        save_audio(merged, sr, f"official_{speaker_id}")
        zh_name = OFFICIAL_SPEAKER_INFO.get(stored_ref_text, (speaker_id, "", "", ""))[0]
        if len(segments) > 1:
            return (sr, merged), f"✅ 完成！官方音色: {zh_name} ({stored_ref_text})，分段: {len(segments)}"
        return (sr, merged), f"✅ 完成！官方音色: {zh_name} ({stored_ref_text})"

    model = load_model("语音克隆", size)
    segments = split_text_for_tts(text)
    audio_segments = []
    total = len(segments)

    m = model.model.model
    talker = m.talker
    config = m.config.talker_config
    speech_tokenizer = m.speech_tokenizer

    voice_clone_prompt = None
    ref_codes_tensor = None
    if vcp_data is not None:
        try:
            items = vcp_data["items"]
            voice_clone_prompt = {
                "ref_code": [torch.tensor(it["ref_code"]) if it.get("ref_code") is not None else None for it in items],
                "ref_spk_embedding": [torch.tensor(it["ref_spk_embedding"]) if it.get("ref_spk_embedding") is not None else None for it in items],
                "x_vector_only_mode": [it.get("x_vector_only_mode", False) for it in items],
                "icl_mode": [it.get("icl_mode", False) for it in items],
            }
            if voice_clone_prompt["ref_code"] and voice_clone_prompt["ref_code"][0] is not None:
                ref_codes_tensor = voice_clone_prompt["ref_code"][0]
        except Exception as e:
            logger.warning(f"构建 voice_clone_prompt 失败: {e}")
            voice_clone_prompt = None

    for idx, seg_text in enumerate(segments):
        seg_text = seg_text.strip()
        if not seg_text:
            continue

        _progress_mgr.advance_segment(f"第 {idx+1}/{total} 段推理中...")

        elapsed = time.time() - start_time
        if idx > 0:
            avg = elapsed / idx
            remaining = avg * (total - idx)
            logger.info(f"第 {idx+1}/{total} 段，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"第 1/{total} 段...")

        if voice_clone_prompt is not None:
            try:
                input_texts = [model.model._build_assistant_text(seg_text)]
                input_ids = model.model._tokenize_texts(input_texts)
                ref_ids = [None] * len(input_ids)

                tie, tam, tth, tpe = model.model._build_talker_inputs_local(
                    m=m,
                    input_ids=input_ids,
                    ref_ids=ref_ids,
                    voice_clone_prompt=voice_clone_prompt,
                    languages=[lang] if lang is not None else ["Auto"],
                    speakers=None,
                    non_streaming_mode=True,
                    instruct_ids=[None],
                )

                if not model.model._warmed_up:
                    model.model._warmup(tie.shape[1])

                talker.rope_deltas = None

                codec_ids, timing = fast_generate(
                    talker=talker,
                    talker_input_embeds=tie,
                    attention_mask=tam,
                    trailing_text_hiddens=tth,
                    tts_pad_embed=tpe,
                    config=config,
                    predictor_graph=model.model.predictor_graph,
                    talker_graph=model.model.talker_graph,
                    max_new_tokens=2048,
                    min_new_tokens=2,
                    temperature=0.9,
                    top_k=50,
                    top_p=1.0,
                    do_sample=True,
                    repetition_penalty=1.05,
                )

                if codec_ids is None:
                    continue

                if ref_codes_tensor is not None:
                    codes_for_decode = torch.cat([ref_codes_tensor.to(codec_ids.device), codec_ids], dim=0)
                else:
                    codes_for_decode = codec_ids

                al, sr = speech_tokenizer.decode({"audio_codes": codes_for_decode.unsqueeze(0)})

                ref_len = ref_codes_tensor.shape[0] if ref_codes_tensor is not None else 0
                total_len = codes_for_decode.shape[0]
                audio_arrays = []
                for a in al:
                    if hasattr(a, 'cpu'):
                        a = a.flatten().cpu().numpy()
                    else:
                        a = a.flatten() if hasattr(a, 'flatten') else a
                    if ref_len > 0:
                        cut = int(ref_len / max(total_len, 1) * len(a))
                        a = a[cut:]
                    audio_arrays.append(a)

                audio_segments.append(audio_arrays[0])
                continue
            except Exception as e:
                logger.warning(f"快速路径推理失败，回退标准模式: {e}")

        al, sr = model.generate_voice_clone(
            text=seg_text, language=lang, ref_audio=wav_path, ref_text=stored_ref_text
        )
        audio_segments.append(al[0])

    if not audio_segments:
        raise GenerationError("语音克隆生成失败：无有效音频段")

    merged, sr = merge_audio_segments(audio_segments, sr)
    if merged is None:
        raise GenerationError("语音克隆生成失败：音频合并失败")

    save_audio(merged, sr, f"clone_persona_{persona_name}")
    if len(segments) > 1:
        return (sr, merged), f"✅ 完成！({size}核心，音色: {persona_name}，分段: {len(segments)})"
    return (sr, merged), f"✅ 完成！({size}核心，音色: {persona_name})"


def fn_voice_design(text, lang, instruct, output_format="wav"):
    """声音设计生成"""
    from ..exceptions import tts_error_handler

    @tts_error_handler
    def _wrapped(text, lang, instruct, output_format="wav"):
        if not _check_model_ready():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        _progress_mgr.start(total_segments=1, phase="加载模型中...")
        start_time = time.time()
        try:
            _progress_mgr.update_phase("加载声音设计模型...")
            model = load_model("声音设计")
            _progress_mgr.update_phase("CUDA Graph 预热中...")
            _progress_mgr.update_phase("推理生成中...")
            audio_list, sr = model.generate_voice_design(text=text, language=lang, instruct=instruct)
            _progress_mgr.update_phase("音频后处理...")
            save_audio(audio_list[0], sr, "design", format=output_format)
            _progress_mgr.advance_segment("完成")
            return (sr, audio_list[0]), "生成成功！"
        except TTSError:
            raise
        except Exception as e:
            _progress_mgr.update_phase(f"出错: {e}")
            raise GenerationError(f"声音设计生成失败: {e}") from e
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.reset()
            cleanup_temp_files()

    return _wrapped(text, lang, instruct, output_format)


def fn_voice_clone(text, lang, ref_audio, ref_text, size):
    """语音克隆生成"""
    if not _check_model_ready():
        raise GenerationError("模型正在加载或切换中，请稍后再试")
    model = load_model("语音克隆", size)
    if ref_audio is None:
        raise GenerationError("需上传参考音频")
    tmp_path, _, _ = preprocess_and_save_temp(ref_audio)
    audio_list, sr = model.generate_voice_clone(text=text, language=lang, ref_audio=tmp_path, ref_text=ref_text)
    save_audio(audio_list[0], sr, f"clone_{size}")
    return (sr, audio_list[0]), f"完成！({size}核心)"


def fn_custom_voice(text, lang, speaker, instruct, size):
    """官方精品音色生成"""
    from ..exceptions import tts_error_handler

    @tts_error_handler
    def _wrapped(text, lang, speaker, instruct, size):
        if not _check_model_ready():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        try:
            model = load_model("官方精品", size)
            if '[' in text and ']' in text:
                lines = text.strip().split('\n')
                combined_wav, sr_final = [], 24000
                for line in lines:
                    match = re.match(r"\[([^\]]+)\]\s*(?:\[([^\]]+)\])?\s*(.*)", line)
                    if match:
                        spk, ins, content = match.groups()
                        if not content.strip():
                            continue
                        segments = split_text_for_tts(content.strip())
                        for seg in segments:
                            wavs, sr = model.generate_custom_voice(text=seg.strip(), language=lang, speaker=spk.strip().lower(), instruct=ins.strip() if ins else None)
                            combined_wav.append(wavs[0])
                        combined_wav.append(np.zeros(int(sr * 0.4)))
                        sr_final = sr
                if combined_wav:
                    res_wav = np.concatenate(combined_wav)
                    save_audio(res_wav, sr_final, "custom_dialogue")
                    return (sr_final, res_wav), "多人对话生成成功！"
            audio_list, sr = model.generate_custom_voice(text=text, language=lang, speaker=speaker.lower(), instruct=instruct)
            save_audio(audio_list[0], sr, f"custom_{speaker}")
            return (sr, audio_list[0]), "生成成功！"
        finally:
            cleanup_temp_files()

    return _wrapped(text, lang, speaker, instruct, size)


def fn_custom_voice_v2(text, lang, speaker, instruct, size, persona_name="(暂无音色)"):
    """官方精品模式增强版：支持官方音色和已保存音色"""
    if persona_name and persona_name != "(暂无音色)":
        return fn_voice_clone_with_persona(text, lang, persona_name, size)
    return fn_custom_voice(text, lang, speaker, instruct, size)


def fn_script_studio(script_text, lang, size):
    """剧本工坊生成"""
    from ..exceptions import tts_error_handler

    @tts_error_handler
    def _wrapped(script_text, lang, size):
        if not _check_model_ready():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        start_time = time.time()
        valid_lines = [l for l in script_text.strip().split('\n') if ']' in l]
        _progress_mgr.start(total_segments=len(valid_lines), phase="剧本合成中...")
        try:
            return _fn_script_studio_impl(script_text, lang, size, start_time)
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.reset()
            cleanup_temp_files()
            logger.info(f"剧本合成耗时 {elapsed:.1f} 秒")

    return _wrapped(script_text, lang, size)


def _fn_script_studio_impl(script_text, lang, size, start_time):
    lines = script_text.strip().split('\n')
    valid_lines = [l for l in lines if ']' in l]
    total_roles = len(valid_lines)
    combined_wav, sr_final = [], 24000
    persona_cache = {}
    model_clone = None
    model_custom = None
    role_idx = 0

    for line in lines:
        if ']' not in line:
            continue
        role_idx += 1
        _progress_mgr.advance_segment(f"角色 [{line.split(']')[0].replace('[', '').strip()}] 合成中...")
        elapsed = time.time() - start_time
        if role_idx > 1:
            avg = elapsed / (role_idx - 1)
            remaining = avg * (total_roles - role_idx + 1)
            logger.info(f"剧本进度: 第 {role_idx}/{total_roles} 角色，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"剧本进度: 第 {role_idx}/{total_roles} 角色...")
        try:
            role_part, content = line.split(']', 1)
            role_name = role_part.replace('[', '').strip()
            if not content.strip():
                continue

            is_official = role_name.lower() in _OFFICIAL_SPEAKERS_LOWER
            real_name = role_name

            if is_official:
                if model_custom is None:
                    model_custom = load_model("官方精品", size)

                if role_name not in persona_cache:
                    persona_cache[role_name] = ("__official__", role_name.lower())

                speaker_id = persona_cache[role_name][1]
                audio_list, sr = model_custom.generate_custom_voice(text=content.strip(), language=lang, speaker=speaker_id, instruct=None)
                combined_wav.append(audio_list[0])
                combined_wav.append(np.zeros(int(sr * 0.4)))
                sr_final = sr
                continue

            if model_clone is None:
                model_clone = load_model("语音克隆", size)

            ref_wav = os.path.join(PERSONA_DIR, f"{role_name}.wav")
            if not os.path.exists(ref_wav):
                continue

            if role_name not in persona_cache:
                persona_data = load_persona_embedding(role_name)
                persona_cache[role_name] = persona_data
            else:
                persona_data = persona_cache[role_name]

            if persona_data is None:
                continue

            vcp_data, wav_path, ref_text = persona_data

            if vcp_data is not None:
                try:
                    if role_name not in persona_cache:
                        items = vcp_data["items"]
                        voice_clone_prompt = {
                            "ref_code": [torch.tensor(it["ref_code"]) if it.get("ref_code") is not None else None for it in items],
                            "ref_spk_embedding": [torch.tensor(it["ref_spk_embedding"]) if it.get("ref_spk_embedding") is not None else None for it in items],
                            "x_vector_only_mode": [it.get("x_vector_only_mode", False) for it in items],
                            "icl_mode": [it.get("icl_mode", False) for it in items],
                        }
                        ref_codes_tensor = None
                        if voice_clone_prompt["ref_code"] and voice_clone_prompt["ref_code"][0] is not None:
                            ref_codes_tensor = voice_clone_prompt["ref_code"][0]
                        m = model_clone.model.model
                        talker = m.talker
                        config = m.config.talker_config
                        speech_tokenizer = m.speech_tokenizer
                        persona_cache[role_name] = (persona_data, voice_clone_prompt, ref_codes_tensor, m, talker, config, speech_tokenizer)
                    else:
                        _, voice_clone_prompt, ref_codes_tensor, m, talker, config, speech_tokenizer = persona_cache[role_name]

                    input_texts = [model_clone.model._build_assistant_text(content.strip())]
                    input_ids = model_clone.model._tokenize_texts(input_texts)
                    ref_ids = [None] * len(input_ids)

                    tie, tam, tth, tpe = model_clone.model._build_talker_inputs_local(
                        m=m, input_ids=input_ids, ref_ids=ref_ids,
                        voice_clone_prompt=voice_clone_prompt,
                        languages=[lang] if lang is not None else ["Auto"],
                        speakers=None, non_streaming_mode=True, instruct_ids=[None],
                    )

                    if not model_clone.model._warmed_up:
                        model_clone.model._warmup(tie.shape[1])

                    talker.rope_deltas = None

                    codec_ids, timing = fast_generate(
                        talker=talker, talker_input_embeds=tie, attention_mask=tam,
                        trailing_text_hiddens=tth, tts_pad_embed=tpe, config=config,
                        predictor_graph=model_clone.model.predictor_graph, talker_graph=model_clone.model.talker_graph,
                        max_new_tokens=2048, min_new_tokens=2, temperature=0.9, top_k=50,
                        top_p=1.0, do_sample=True, repetition_penalty=1.05,
                    )

                    if codec_ids is None:
                        continue

                    if ref_codes_tensor is not None:
                        codes_for_decode = torch.cat([ref_codes_tensor.to(codec_ids.device), codec_ids], dim=0)
                    else:
                        codes_for_decode = codec_ids

                    audio_list, sr = speech_tokenizer.decode({"audio_codes": codes_for_decode.unsqueeze(0)})

                    ref_len = ref_codes_tensor.shape[0] if ref_codes_tensor is not None else 0
                    total_len = codes_for_decode.shape[0]
                    audio_arrays = []
                    for a in audio_list:
                        if hasattr(a, 'cpu'):
                            a = a.flatten().cpu().numpy()
                        else:
                            a = a.flatten() if hasattr(a, 'flatten') else a
                        if ref_len > 0:
                            cut = int(ref_len / max(total_len, 1) * len(a))
                            a = a[cut:]
                        audio_arrays.append(a)

                    combined_wav.append(audio_arrays[0])
                    combined_wav.append(np.zeros(int(sr * 0.4)))
                    sr_final = sr
                    continue
                except Exception as e:
                    logger.warning(f"剧本快速推理失败 [{role_name}]: {e}")
                    pass

            audio_list, sr = model_clone.generate_voice_clone(
                text=content.strip(), language=lang, ref_audio=wav_path, ref_text=ref_text
            )
            combined_wav.append(audio_list[0])
            combined_wav.append(np.zeros(int(sr * 0.4)))
            sr_final = sr
        except Exception as e:
            logger.error(f"剧本出错: {e}")

    if not combined_wav:
        raise GenerationError("剧本合成失败：无匹配角色或生成失败")
    res_wav = np.concatenate(combined_wav)
    save_audio(res_wav, sr_final, "script")
    return (sr_final, res_wav), f"✅ 合成完成！规格: {size}"
