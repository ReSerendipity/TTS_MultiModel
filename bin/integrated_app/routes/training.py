import os
import sys
import json
import subprocess
import threading
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

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
    num_iters = body.get("num_iters", 10000)
    batch_size = body.get("batch_size", 1)
    grad_accum_steps = body.get("grad_accum_steps", 1)
    save_interval = body.get("save_interval", 1000)
    log_interval = body.get("log_interval", 100)
    lora_config = body.get("lora", {})

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

    lora_json = json.dumps(lora_config) if lora_config else ""

    cmd = [
        sys.executable, train_script,
        "--pretrained_path", pretrained_path,
        "--train_manifest", train_manifest,
        "--save_path", save_path,
        "--learning_rate", str(learning_rate),
        "--num_iters", str(num_iters),
        "--batch_size", str(batch_size),
        "--grad_accum_steps", str(grad_accum_steps),
        "--save_interval", str(save_interval),
        "--log_interval", str(log_interval),
        "--sample_rate", "16000",
    ]

    if val_manifest:
        cmd.extend(["--val_manifest", val_manifest])

    if lora_json:
        cmd.extend(["--lora", lora_json])

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
