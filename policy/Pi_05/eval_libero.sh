#!/bin/bash
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: LIBERO_CLIENT_ROOT=/path/to/libero PI05_CHECKPOINT_STEP=29999 bash $0 [suite] [trials] [client flags...]"
  echo "Optional: LIBERO_PYTHON, POLICY_HOST=127.0.0.1, POLICY_PORT=8000, EVAL_GPU_ID=0,"
  echo "  PI05_RUN_NAME=Libero-pi05_libero-franka-ee-0, EVAL_SEED=7, EVAL_RESULT_ROOT."
  echo "Requires the external client described in docs/reproduction/pi05-libero.md (native OpenPI protocol)."
  exit 0
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${LIBERO_CLIENT_ROOT:?Set LIBERO_CLIENT_ROOT to the external LIBERO client project}"
: "${PI05_CHECKPOINT_STEP:?Set PI05_CHECKPOINT_STEP to match the served checkpoint}"
SUITE="${1:-libero_spatial}"
TRIALS="${2:-50}"
if [[ $# -gt 0 ]]; then shift; fi
if [[ $# -gt 0 ]]; then shift; fi
case "${SUITE}" in
  libero_spatial|libero_object|libero_goal|libero_10|libero_90) ;;
  *) echo "Unknown LIBERO suite: ${SUITE}" >&2; exit 1 ;;
esac
[[ "${TRIALS}" =~ ^[1-9][0-9]*$ ]] || { echo "Trials must be a positive integer" >&2; exit 1; }
[[ "${PI05_CHECKPOINT_STEP}" =~ ^[0-9]+$ ]] || { echo "Checkpoint step must be an integer" >&2; exit 1; }
CLIENT_ROOT="$(cd "${LIBERO_CLIENT_ROOT}" && pwd)"
CLIENT_PYTHON="${LIBERO_PYTHON:-${CLIENT_ROOT}/.venv/bin/python}"
[[ -f "${CLIENT_ROOT}/main.py" ]] || { echo "Missing LIBERO client: ${CLIENT_ROOT}/main.py" >&2; exit 1; }
[[ -x "${CLIENT_PYTHON}" ]] || { echo "Missing executable LIBERO_PYTHON: ${CLIENT_PYTHON}" >&2; exit 1; }

cd "${CLIENT_ROOT}"
export MUJOCO_GL="${MUJOCO_GL:-egl}"
export MUJOCO_EGL_DEVICE_ID="${EVAL_GPU_ID:-0}"
exec "${CLIENT_PYTHON}" main.py \
  --args.host "${POLICY_HOST:-127.0.0.1}" \
  --args.port "${POLICY_PORT:-8000}" \
  --args.task-suite-name "${SUITE}" \
  --args.checkpoint-step "${PI05_CHECKPOINT_STEP}" \
  --args.ckpt-name "${PI05_RUN_NAME:-Libero-pi05_libero-franka-ee-0}" \
  --args.seed "${EVAL_SEED:-7}" \
  --args.result-root "${EVAL_RESULT_ROOT:-${SCRIPT_DIR}/eval_result}" \
  --args.num-trials-per-task "${TRIALS}" "$@"
