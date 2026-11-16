#!/bin/bash
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: PI05_CHECKPOINT_DIR=/absolute/path/to/step bash $0 [OpenPI serve flags...]"
  echo "Optional: PI05_TRAIN_CONFIG=pi05_libero, POLICY_PORT=8000, POLICY_GPU_ID=0, OPENPI_ROOT, UV_BIN."
  echo "Serves the native OpenPI protocol, not the XPolicyLab protocol."
  exit 0
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${PI05_CHECKPOINT_DIR:?Set PI05_CHECKPOINT_DIR to the exact checkpoint step directory}"
CKPT_DIR="$(cd "${PI05_CHECKPOINT_DIR}" && pwd)"
[[ -d "${CKPT_DIR}/params" ]] || { echo "Missing checkpoint params: ${CKPT_DIR}/params" >&2; exit 1; }

cd "${OPENPI_ROOT:-${SCRIPT_DIR}/openpi}"
export CUDA_VISIBLE_DEVICES="${POLICY_GPU_ID:-0}"
exec "${UV_BIN:-uv}" run --frozen scripts/serve_policy.py --port "${POLICY_PORT:-8000}" policy:checkpoint \
  --policy.config "${PI05_TRAIN_CONFIG:-pi05_libero}" \
  --policy.dir "${CKPT_DIR}" "$@"
