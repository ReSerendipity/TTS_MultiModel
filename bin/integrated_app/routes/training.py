import asyncio
import contextlib
import json
import logging
import os
import sys

import aiofiles
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger("tts_multimodel.training")
router = APIRouter(prefix="/api/training", tags=["training"])

_training_process = None
_training_reader_task = None
_training_log = ""
_training_log_lock = asyncio.Lock()
_MAX_LOG_LENGTH = 1_000_000


def _validate_path(base_dir: str, user_path: str) -> str:
    """Validate that user_path resolves within base_dir (path traversal guard)."""
    joined = os.path.realpath(os.path.join(base_dir, user_path))
    base = os.path.realpath(base_dir)
    if not joined.startswith(base + os.sep) and joined != base:
        raise ValueError(f"Path traversal detected: {user_path}")
    return joined


async def _detect_sample_rate(pretrained_path: str) -> int:
    config_file = os.path.join(pretrained_path, "config.json")
    if not os.path.isfile(config_file):
        logger.warning(f"在 {config_file} 未找到 config.json，使用默认 sample_rate=44100")
        return 44100
    try:
        async with aiofiles.open(config_file, encoding="utf-8") as f:
            content = await f.read()
            cfg = json.loads(content)
        sr = int(cfg["audio_vae_config"]["sample_rate"])
        logger.info(f"自动检测 sample_rate={sr} 来自 {config_file}")
        return sr
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.warning(f"从 {config_file} 检测 sample_rate 失败: {e}，使用默认值 44100")
        return 44100


async def _detect_out_sample_rate(pretrained_path: str) -> int:
    config_file = os.path.join(pretrained_path, "config.json")
    if not os.path.isfile(config_file):
        return 0
    try:
        async with aiofiles.open(config_file, encoding="utf-8") as f:
            content = await f.read()
            cfg = json.loads(content)
        out_sr = cfg.get("audio_vae_config", {}).get("out_sample_rate")
        return int(out_sr) if out_sr else 0
    except (KeyError, ValueError, json.JSONDecodeError):
        return 0


def _validate_training_params(body: dict) -> list[str]:
    """Validate numeric parameter ranges for the training endpoint."""
    errors: list[str] = []

    _RANGE_CHECKS = {
        "learning_rate": (float, True, 0, True, 1.0, "> 0 and <= 1.0"),
        "num_iters": (int, False, 1, True, 100000, ">= 1 and <= 100000"),
        "batch_size": (int, False, 1, True, 32, ">= 1 and <= 32"),
        "grad_accum_steps": (int, False, 1, True, 64, ">= 1 and <= 64"),
        "save_interval": (int, False, 100, True, 50000, ">= 100 and <= 50000"),
        "log_interval": (int, False, 1, True, 1000, ">= 1 and <= 1000"),
        "weight_decay": (float, False, 0, True, 1.0, ">= 0 and <= 1.0"),
        "warmup_steps": (int, False, 0, True, 10000, ">= 0 and <= 10000"),
        "max_grad_norm": (float, True, 0, True, 100.0, "> 0 and <= 100.0"),
        "num_workers": (int, False, 0, True, 16, ">= 0 and <= 16"),
        "valid_interval": (int, False, 100, True, 50000, ">= 100 and <= 50000"),
    }

    for param, (typ, lo_strict, lo, hi_strict, hi, desc) in _RANGE_CHECKS.items():
        if param in body:
            try:
                val = typ(body[param])
            except (ValueError, TypeError):
                errors.append(f"{param} must be {typ.__name__}, got {body[param]!r}")
                continue
            lo_ok = val > lo if lo_strict else val >= lo
            hi_ok = val <= hi if hi_strict else val < hi
            if not (lo_ok and hi_ok):
                errors.append(f"{param} must be {desc}, got {val}")

    if "max_steps" in body:
        try:
            val = int(body["max_steps"])
            if not (0 <= val <= 100000):
                errors.append(f"max_steps must be >= 0 and <= 100000, got {val}")
        except (ValueError, TypeError):
            errors.append(f"max_steps must be int, got {body['max_steps']!r}")

    return errors


def _is_training_running() -> bool:
    return _training_process is not None and _training_process.returncode is None


async def _read_training_output(process: asyncio.subprocess.Process):
    """异步读取训练子进程 stdout 并追加到全局日志缓冲区。"""
    global _training_log
    if process.stdout is None:
        return
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace")
            async with _training_log_lock:
                _training_log += decoded
                if len(_training_log) > _MAX_LOG_LENGTH:
                    _training_log = _training_log[-_MAX_LOG_LENGTH:]
    except Exception as e:
        async with _training_log_lock:
            _training_log += f"\nLog read error: {e}\n"


@router.post("/start", summary="开始训练", description="启动 LoRA 微调训练")
async def start_training(request: Request):
    global _training_process, _training_reader_task, _training_log

    if _is_training_running():
        return JSONResponse({"status": "error", "message": "Training already running"})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"})

    validation_errors = _validate_training_params(body)
    if validation_errors:
        return JSONResponse(
            {"status": "error", "message": "Parameter validation failed", "errors": validation_errors},
            status_code=422,
        )

    pretrained_path = body.get("pretrained_path", "pretrained_models/VoxCPM2")
    train_manifest = body.get("train_manifest", "")
    val_manifest = body.get("val_manifest", "")
    save_path = body.get("save_path", "lora/my_lora")
    learning_rate = body.get("learning_rate", 1e-4)
    num_iters = body.get("num_iters", 2000)
    batch_size = body.get("batch_size", 1)
    grad_accum_steps = body.get("grad_accum_steps", 1)
    save_interval = body.get("save_interval", 1000)
    log_interval = body.get("log_interval", 10)
    lora_config = body.get("lora", {})
    weight_decay = body.get("weight_decay", 0.01)
    warmup_steps = body.get("warmup_steps", 100)
    max_grad_norm = body.get("max_grad_norm", 1.0)
    num_workers = body.get("num_workers", 2)
    valid_interval = body.get("valid_interval", 1000)
    lambdas = body.get("lambdas", {"loss/diff": 1.0, "loss/stop": 1.0})

    if not train_manifest:
        return JSONResponse({"status": "error", "message": "train_manifest is required"})

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    train_script = os.path.join(project_root, "scripts", "train_voxcpm_finetune.py")

    if not os.path.isfile(train_script):
        return JSONResponse({"status": "error", "message": f"Training script not found: {train_script}"})

    try:
        pretrained_dir = os.path.join(project_root, "pretrained_models")
        pretrained_path = _validate_path(pretrained_dir, pretrained_path)
    except ValueError as e:
        return JSONResponse({"status": "error", "message": str(e)})

    try:
        train_manifest = _validate_path(project_root, train_manifest)
    except ValueError as e:
        return JSONResponse({"status": "error", "message": str(e)})

    try:
        save_path = _validate_path(project_root, save_path)
    except ValueError as e:
        return JSONResponse({"status": "error", "message": str(e)})

    sample_rate = await _detect_sample_rate(pretrained_path)
    out_sample_rate = await _detect_out_sample_rate(pretrained_path)

    user_sr = body.get("sample_rate")
    if user_sr is not None:
        user_sr = int(user_sr)
        if user_sr != sample_rate:
            logger.warning(f"用户 sample_rate={user_sr} 与自动检测值 {sample_rate} 不同，使用自动检测值")
    else:
        user_sr = sample_rate

    os.makedirs(save_path, exist_ok=True)
    checkpoints_dir = os.path.join(save_path, "checkpoints")
    logs_dir = os.path.join(save_path, "logs")
    os.makedirs(checkpoints_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)

    resolved_max_steps = int(body.get("max_steps", 0)) or int(num_iters)

    config = {
        "pretrained_path": pretrained_path,
        "train_manifest": train_manifest,
        "val_manifest": val_manifest if val_manifest else "",
        "sample_rate": int(user_sr),
        "out_sample_rate": int(out_sample_rate),
        "batch_size": int(batch_size),
        "grad_accum_steps": int(grad_accum_steps),
        "num_workers": int(num_workers),
        "num_iters": int(num_iters),
        "log_interval": int(log_interval),
        "valid_interval": int(valid_interval),
        "save_interval": int(save_interval),
        "learning_rate": float(learning_rate),
        "weight_decay": float(weight_decay),
        "warmup_steps": int(warmup_steps),
        "max_steps": resolved_max_steps,
        "max_grad_norm": float(max_grad_norm),
        "save_path": checkpoints_dir,
        "tensorboard": logs_dir,
        "lambdas": lambdas,
    }

    if lora_config:
        config["lora"] = lora_config

    config_path = os.path.join(save_path, "train_config.yaml")
    try:
        import yaml as _yaml

        async with aiofiles.open(config_path, "w", encoding="utf-8") as f:
            await f.write(_yaml.dump(config, default_flow_style=False, allow_unicode=True))
    except ImportError:
        async with aiofiles.open(config_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(config, indent=2, ensure_ascii=False))
        logger.warning("未安装 PyYAML，已改为保存 JSON 格式配置")

    cmd = [sys.executable, train_script, "--config_path", config_path]

    async with _training_log_lock:
        _training_log = f"Starting training: {' '.join(cmd)}\n"

    try:
        _training_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=project_root,
            env={**os.environ, "TOKENIZERS_PARALLELISM": "false"},
        )

        _training_reader_task = asyncio.create_task(_read_training_output(_training_process))

        return JSONResponse({"status": "ok", "process_id": _training_process.pid})
    except Exception as e:
        logger.error(f"训练启动失败: {e}")
        return JSONResponse({"status": "error", "message": "训练启动失败，请检查配置和日志"})


@router.post("/stop", summary="停止训练", description="停止正在进行的训练")
async def stop_training():
    global _training_process, _training_reader_task
    if _is_training_running():
        _training_process.terminate()
        try:
            await asyncio.wait_for(_training_process.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            _training_process.kill()
            await _training_process.wait()
        if _training_reader_task is not None:
            _training_reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await _training_reader_task
            _training_reader_task = None
        return JSONResponse({"status": "ok", "message": "Training stopped"})
    return JSONResponse({"status": "ok", "message": "No training running"})


@router.get("/log", summary="训练日志", description="获取训练日志")
async def get_training_log():
    global _training_process, _training_log
    running = _is_training_running()
    async with _training_log_lock:
        log = _training_log
    return JSONResponse({"log": log, "running": running})
