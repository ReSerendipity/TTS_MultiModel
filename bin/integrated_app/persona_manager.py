"""音色管理：保存、加载、删除、列表查询、嵌入缓存等"""

import logging
import os
from datetime import datetime

from .config import (
    _PERSONA_NAME_RE,
    PERSONA_DIR,
)
from .generation import preprocess_and_save_temp
from .model_manager import _model_lock, _persona_embedding_cache
from .model_registry import registry
from .persona_metadata import (
    PersonaMetadata,
    save_persona_metadata,
)

logger = logging.getLogger("tts_multimodel")


def _validate_persona_name(name: str) -> tuple[bool, str]:
    """验证音色名称合法性，防止路径遍历和注入"""
    if not name:
        return False, "名称不能为空"
    if not _PERSONA_NAME_RE.match(name):
        return False, "名称格式不合法（仅支持字母、数字、下划线、连字符、中文，1-50字符）"
    return True, ""


def _verify_persona_sync(name: str, wav_path: str, ref_text: str) -> None:
    """后台验证音色：检查模型就绪并持有模型锁，避免与卸载/切换并发。"""
    if not registry.is_voxcpm_ready():
        logger.warning(f"[音色固化] 跳过音色 [{name}] 验证：VoxCPM2 模型未就绪")
        return

    try:
        with _model_lock:
            # 再次检查，防止获取锁期间模型被卸载
            if not registry.is_voxcpm_ready():
                logger.warning(f"[音色固化] 跳过音色 [{name}] 验证：模型在获取锁后被卸载")
                return
            logger.info(f"[音色固化] 后台验证音色 [{name}] 通过官方 generate(reference_wav_path=...)")
            _ = registry.voxcpm_model.generate(
                text=ref_text.strip(),
                reference_wav_path=wav_path,
                normalize=True,
                cfg_value=2.0,
                inference_timesteps=10,
                denoise=True,
                min_len=2,
                max_len=100,
            )
            logger.info(f"[音色固化] 音色 [{name}] 后台验证成功")
    except Exception as e:
        logger.error(f"[音色固化] 音色 [{name}] 后台验证失败: {e}")


def fn_save_persona(name: str, audio_input, ref_text: str, overwrite: bool = False) -> tuple[str, bool]:
    """保存音色到音色库（固化）- 使用官方 VoxCPM2 API"""
    if not name or audio_input is None:
        return "❌ 失败：需输入名称及音频", False

    valid, err_msg = _validate_persona_name(name)
    if not valid:
        return f"❌ {err_msg}", False

    try:
        wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
        txt_path = os.path.join(PERSONA_DIR, f"{name}.txt")
        wav_real = os.path.realpath(wav_path)
        if not wav_real.startswith(os.path.realpath(PERSONA_DIR)):
            return "❌ 非法路径", False

        existing = os.path.exists(wav_path) or os.path.exists(txt_path)
        if existing and not overwrite:
            return f"⚠️ 音色 [{name}] 已存在，再次点击保存将覆盖原有音色", True

        tmp_p, sr_p, wav_p = preprocess_and_save_temp(audio_input, f"{name}.wav")
        os.replace(tmp_p, wav_path)

        meta = PersonaMetadata(
            name=name,
            description=ref_text if ref_text else "",
            voice_type="",
            traits="",
            created_at=datetime.now().isoformat(),
        )
        save_persona_metadata(PERSONA_DIR, name, meta)

        # 保存参考文本
        if ref_text:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(ref_text)

        # 非阻塞音色验证（对齐官方行为：官方仅保存，不验证）
        if ref_text and ref_text.strip():
            import threading

            threading.Thread(
                target=_verify_persona_sync,
                args=(name, wav_path, ref_text),
                daemon=True,
            ).start()

        # 清除缓存中的旧数据
        if name in _persona_embedding_cache:
            del _persona_embedding_cache[name]

        return f"✅ 音色 [{name}] 已成功固化！", False
    except Exception as e:
        logger.error(f"音色固化失败: {e}")
        return f"❌ 固化失败: {str(e)}", False


def get_persona_list(search_keyword: str = "") -> list[str]:
    """获取自定义音色列表，支持搜索过滤"""
    wav_files = [f[:-4] for f in os.listdir(PERSONA_DIR) if f.endswith(".wav")]
    custom = sorted(wav_files) if wav_files else []

    if search_keyword:
        kw = search_keyword.lower()
        custom = [c for c in custom if kw in c.lower()]

    return custom if custom else ["(暂无音色)"]


def get_total_persona_count() -> int:
    """获取自定义音色总数"""
    files = [f for f in os.listdir(PERSONA_DIR) if f.endswith(".wav")]
    return len(files)


def get_persona_detail_table(search_keyword: str = "") -> list[list[str]]:
    """获取自定义音色详情表格数据"""
    table = []

    files = [f.replace(".wav", "") for f in os.listdir(PERSONA_DIR) if f.endswith(".wav")]
    files = sorted(files)

    if search_keyword:
        kw = search_keyword.lower()
        files = [f for f in files if kw in f.lower()]

    for name in files:
        wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
        txt_path = os.path.join(PERSONA_DIR, f"{name}.txt")

        ref_text = ""
        if os.path.exists(txt_path):
            with open(txt_path, encoding="utf-8") as f:
                ref_text = f.read()
            if len(ref_text) > 50:
                ref_text = ref_text[:50] + "..."

        stat = os.stat(wav_path) if os.path.exists(wav_path) else None
        wav_size = f"{stat.st_size / 1024:.1f} KB" if stat else "-"
        wav_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M") if stat else "-"

        table.append([name, "✅ 已固化", wav_size, wav_time, ref_text if ref_text else "-"])

    if not table:
        table = [["暂无音色", "-", "-", "-", "-"]]
    return table


def get_persona_desc(name: str) -> str:
    """获取音色描述信息"""
    wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
    if os.path.exists(wav_path):
        return f"**{name}**（自定义音色）\n\n自定义音色，适用于个性化语音合成。"
    return ""


def load_persona_embedding(name: str) -> tuple | None:
    """加载已保存音色的 WAV 路径和参考文本（由官方 API 在生成时计算嵌入）"""
    cached = _persona_embedding_cache.get(name)
    if cached is not None:
        return cached

    wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
    txt_path = os.path.join(PERSONA_DIR, f"{name}.txt")

    wav_exists = os.path.exists(wav_path)
    txt_exists = os.path.exists(txt_path)

    ref_text = ""
    if txt_exists:
        with open(txt_path, encoding="utf-8") as f:
            ref_text = f.read()

    if wav_exists:
        result = (wav_path, ref_text)
    else:
        return None

    _persona_embedding_cache.put(name, result)
    return result


def get_persona_map() -> dict[str, dict[str, str]]:
    """获取音色名称到 wav 路径的映射"""
    persona_map: dict[str, dict[str, str]] = {}
    if not os.path.exists(PERSONA_DIR):
        return persona_map
    for f in os.listdir(PERSONA_DIR):
        if f.endswith(".wav"):
            name = f[:-4]
            wav_path = os.path.join(PERSONA_DIR, f)
            persona_map[name] = {"wav": wav_path}
    return persona_map


def delete_persona(name: str) -> tuple[bool, str]:
    """删除指定音色及其关联文件（.wav / .txt / .pt）。

    Returns:
        (success, message): 成功返回 (True, 提示信息)，失败返回 (False, 错误原因)。
    """
    if not name:
        return False, "名称不能为空"

    valid, err_msg = _validate_persona_name(name)
    if not valid:
        return False, err_msg

    wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
    txt_path = os.path.join(PERSONA_DIR, f"{name}.txt")
    pt_path = os.path.join(PERSONA_DIR, f"{name}.pt")

    real_wav = os.path.realpath(wav_path)
    if not real_wav.startswith(os.path.realpath(PERSONA_DIR)):
        return False, "非法路径"

    deleted_any = False
    errors: list[str] = []

    for path in (wav_path, txt_path, pt_path):
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted_any = True
            except OSError as e:
                errors.append(f"删除 {os.path.basename(path)} 失败: {e}")

    if name in _persona_embedding_cache:
        try:
            del _persona_embedding_cache[name]
        except Exception:
            pass

    if errors:
        return False, "; ".join(errors)
    if not deleted_any:
        return False, f"音色 [{name}] 不存在"
    return True, f"音色 [{name}] 已删除"
