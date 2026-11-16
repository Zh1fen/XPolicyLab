#!/usr/bin/env python3
"""通过 module:factory 接入仿真/真机环境，并连接标准 XPolicyLab websocket 策略服务。"""

import argparse
import importlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT.parent), str(ROOT)]

from XPolicyLab.environment import ClientPolicy, EpisodeError, JsonlRecorder, run_episode


def load_environment(factory: str, config: dict):
    module_name, separator, name = factory.partition(":")
    if not separator or not module_name or not name or name.startswith("_"):
        raise ValueError("env factory must be module:public_callable")
    create = getattr(importlib.import_module(module_name), name)
    env = create(config)
    if not all(callable(getattr(env, method, None)) for method in ("reset", "step", "validate_action", "stop", "close")):
        close = getattr(env, "close", None)
        if callable(close):
            close()
        raise TypeError("factory must return an Environment (reset, step, validate_action, stop, close)")
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-factory", required=True)
    parser.add_argument("--env-config", type=Path, help="传入 factory 的 JSON 对象；run 字段由启动参数提供")
    parser.add_argument("--policy-url", required=True)
    parser.add_argument("--max-steps", type=int, required=True)
    parser.add_argument("--execute-horizon", type=int, default=1)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--evaluation-id", default="environment-run")
    parser.add_argument("--trial-id", default=None)
    parser.add_argument("--step-feedback", action="store_true", help="服务端须支持 on_execution_feedback")
    for argument in ("bench-name", "task-name", "env-cfg-type", "policy-name", "additional-info"):
        parser.add_argument("--" + argument)
    args = parser.parse_args()
    if args.max_steps <= 0 or args.execute_horizon <= 0:
        parser.error("max-steps and execute-horizon must be positive")
    config = json.loads(args.env_config.read_text()) if args.env_config else {}
    if not isinstance(config, dict) or "run" in config:
        parser.error("env-config must be a JSON object without the reserved run key")
    config["run"] = {name: getattr(args, name) for name in
                     ("bench_name", "task_name", "env_cfg_type", "policy_name", "additional_info", "seed")}
    from client_server.ws import WsModelClient

    # Establish the policy connection before factory construction or any hardware reset.
    with WsModelClient(url=args.policy_url, evaluation_id=args.evaluation_id,
                       trial_id=args.trial_id or str(uuid4())) as client:
        env = load_environment(args.env_factory, config)
        recorder = None
        try:
            recorder = JsonlRecorder(args.record) if args.record else None
            result = run_episode(env, ClientPolicy(client, step_feedback=args.step_feedback),
                                 max_steps=args.max_steps, execute_horizon=args.execute_horizon,
                                 seed=args.seed, on_event=recorder)
            print(json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False))
            return 0
        except EpisodeError as exc:
            print(json.dumps(exc.result.to_dict(), ensure_ascii=False, allow_nan=False), file=sys.stderr)
            return 1
        finally:
            try:
                env.close()
            finally:
                if recorder is not None:
                    recorder.close()


if __name__ == "__main__":
    sys.exit(main())
