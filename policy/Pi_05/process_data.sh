#!/usr/bin/env bash
set -euo pipefail
POLICY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "${POLICY_DIR}/openpi/.venv/bin/python" ]]; then
    default_python="${POLICY_DIR}/openpi/.venv/bin/python"
else
    default_python=python
fi
cd "${POLICY_DIR}/openpi"
exec "${OPENPI_DATA_PYTHON:-${default_python}}" scripts/process_data.py --mode "${OPENPI_DATA_MODE:-image}" "$@"
