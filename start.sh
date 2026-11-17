#!/usr/bin/env bash
# RoboLab 本地控制台：从任意目录启动，自动选择工作区配置。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${ROBOLAB_PYTHON:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "找不到 Python 3，请安装 Python >=3.10，或设置 ROBOLAB_PYTHON。" >&2
    exit 1
fi

if [[ -f configs/web.local.json ]]; then
    config=configs/web.local.json
else
    config=configs/web.example.json
fi

# 显式传入的 --config / --port 等参数在默认配置之后交给原入口处理。
exec "${PYTHON_BIN}" "${ROOT_DIR}/scripts/run_web.py" --config "${config}" "$@"
