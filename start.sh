#!/bin/bash
set -e

echo "=== TTS MultiModel 启动脚本 ==="

VENV_DIR=".venv"
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
fi

PORT=${PORT:-7869}
HOST=${HOST:-127.0.0.1}

echo "启动服务: http://${HOST}:${PORT}"
python -c "from integrated_app.app_server import run_server; run_server('${HOST}', ${PORT})"
