#!/usr/bin/env bash
# Shared ownership of adapter-created process groups; external services are never registered.
eval_init() {
    EVAL_PROCESS_GROUPS=()
    trap 'eval_cleanup' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
}
eval_register() { EVAL_PROCESS_GROUPS+=("$1"); }
eval_cleanup() {
    local pgid sig attempt
    trap - EXIT INT TERM
    for sig in TERM KILL; do
        for pgid in "${EVAL_PROCESS_GROUPS[@]}"; do
            kill -"${sig}" -- -"${pgid}" 2>/dev/null || true
        done
        if [[ "${sig}" == TERM ]]; then
            for attempt in {1..20}; do
                local found=0
                for pgid in "${EVAL_PROCESS_GROUPS[@]}"; do
                    if kill -0 -- -"${pgid}" 2>/dev/null; then found=1; fi
                done
                [[ "${found}" == 0 ]] && break
                sleep 0.1
            done
        fi
    done
    for pgid in "${EVAL_PROCESS_GROUPS[@]}"; do wait "${pgid}" 2>/dev/null || true; done
}
eval_run_client() {
    setsid "$@" &
    local client_pid=$!
    eval_register "${client_pid}"
    wait "${client_pid}"
}
eval_free_port() { bash "${UTILS_DIR}/get_free_port.sh"; }
eval_wait_server() { bash "${UTILS_DIR}/wait_for_policy_server.sh" "$@"; }
