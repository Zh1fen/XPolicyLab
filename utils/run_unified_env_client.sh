#!/usr/bin/env bash
# Called after the parent sim/real launcher has activated the environment.
set -euo pipefail

if [[ $# -lt 13 ]]; then
  echo "Usage: $0 <the 13 standard environment-client arguments>" >&2
  exit 1
fi
root_dir=${9}
protocol=${13}
: "${XPOLICYLAB_ENV_FACTORY:?Set XPOLICYLAB_ENV_FACTORY to module:factory}"
: "${XPOLICYLAB_MAX_STEPS:?Set XPOLICYLAB_MAX_STEPS to an explicit environment action budget}"
if [[ "${protocol}" != ws ]]; then
  echo "The unified environment entry point requires protocol=ws" >&2
  exit 1
fi
if [[ "${1}" != false ]]; then
  echo "The unified environment entry point is single-environment; set deploy.yml eval_batch: false" >&2
  exit 1
fi
export PYTHONPATH="${root_dir}/XPolicyLab:${root_dir}${PYTHONPATH:+:${PYTHONPATH}}"
args=(
  --env-factory "${XPOLICYLAB_ENV_FACTORY}"
  --policy-url "ws://${12}:${3}"
  --max-steps "${XPOLICYLAB_MAX_STEPS}"
  --execute-horizon "${XPOLICYLAB_EXECUTE_HORIZON:-1}"
  --seed "${10}"
  --bench-name "${4}"
  --task-name "${5}"
  --env-cfg-type "${6}"
  --policy-name "${7}"
  --additional-info "${8}"
)
if [[ -n "${XPOLICYLAB_ENV_CONFIG:-}" ]]; then args+=(--env-config "${XPOLICYLAB_ENV_CONFIG}"); fi
if [[ -n "${XPOLICYLAB_RECORD_PATH:-}" ]]; then args+=(--record "${XPOLICYLAB_RECORD_PATH}"); fi
if [[ "${XPOLICYLAB_STEP_FEEDBACK:-0}" == 1 ]]; then args+=(--step-feedback); fi
exec python "${root_dir}/XPolicyLab/scripts/run_environment.py" "${args[@]}"
