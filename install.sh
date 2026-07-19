#!/bin/bash
set -e

echo "=== TTS MultiModel 安装脚本 ==="

PYTHON=${PYTHON:-python3}
VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境..."
    $PYTHON -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "安装依赖..."
pip install -e .

echo "安装完成！运行 ./start.sh 启动服务"
