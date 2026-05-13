import os
import sys
import json
import subprocess
import threading
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/training", tags=["training"])

_training_process = None
_training_log = ""
_training_log_lock = threading.Lock()


def _validate_path(base_dir: str, user_path: str) -> str:
    """Validate that user_path resolves within base_dir (path traversal guard)."""
    joined = os.path.realpath(os.path.join(base_dir, user_path))
    base = os.path.realpath(base_dir)
    if not joined.startswith(base + os.sep) and joined != base:
        raise ValueError(f"Path traversal detected: {user_path}")
    return joined


def _detect_sample_rate(pretrained_path: str) -> int:
    config_file = os.path.join(pretrained_path, "config.json")
    if not os.path.isfile(config_file):
        logger.warning(f"config.json not found at {config_file}, using default sample_rate=44100")
        return 44100
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        sr = int(cfg["audio_vae_config"]["sample_rate"])
        logger.info(f"Auto-detected sample_rate={sr} from {config_file}")
        return sr
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to detect sample_rate from {config_file}: {e}, using default 44100")
        return 44100


def _detect_out_sample_rate(pretrained_path: str) -> int:
    config_file = os.path.join(pretrained_path, "config.json")
    if not os.path.isfile(config_file):
        return 0
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        out_sr = cfg.get("audio_vae_config", {}).get("out_sample_rate")
        return int(out_sr) if out_sr else 0
    except (KeyError, ValueError, json.JSONDecodeError):
        return 0


@router.post("/start")
async def start_training(request: Request):
    global _training_process, _training_log

    if _training_process is not None and _training_process.poll() is None:
        return JSONResponse({"status": "error", "message": "Training already running"})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"})

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

    sample_rate = _detect_sample_rate(pretrained_path)
    out_sample_rate = _detect_out_sample_rate(pretrained_path)

    user_sr = body.get("sample_rate")
    if user_sr is not None:
        user_sr = int(user_sr)
        if user_sr != sample_rate:
            logger.warning(f"User sample_rate={user_sr} differs from auto-detected {sample_rate}, using auto-detected value")
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
        with open(config_path, "w", encoding="utf-8") as f:
            _yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    except ImportError:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.warning("PyYAML not installed, saved config as JSON instead")

    cmd = [sys.executable, train_script, "--config_path", config_path]

    with _training_log_lock:
        _training_log = f"Starting training: {' '.join(cmd)}\n"

    try:
        _training_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=project_root,
            env={**os.environ, "TOKENIZERS_PARALLELISM": "false"},
        )

        def _read_output():
            global _training_log
            try:
                for line in iter(_training_process.stdout.readline, b""):
                    decoded = line.decode("utf-8", errors="replace")
                    with _training_log_lock:
                        _training_log += decoded
            except Exception as e:
                with _training_log_lock:
                    _training_log += f"\nLog read error: {e}\n"

        t = threading.Thread(target=_read_output, daemon=True)
        t.start()

        return JSONResponse({"status": "ok", "process_id": _training_process.pid})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})


@router.post("/stop")
async def stop_training():
    global _training_process
    if _training_process is not None and _training_process.poll() is None:
        _training_process.terminate()
        try:
            _training_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _training_process.kill()
        return JSONResponse({"status": "ok", "message": "Training stopped"})
    return JSONResponse({"status": "ok", "message": "No training running"})


@router.get("/log")
async def get_training_log():
    global _training_process, _training_log
    running = _training_process is not None and _training_process.poll() is None
    with _training_log_lock:
        log = _training_log
    return JSONResponse({"log": log, "running": running})
