#!/usr/bin/env python3
"""CPU protocol fixture for the console. Its results are never model benchmark scores."""

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT.parent), str(ROOT)]
from XPolicyLab.environment import JsonlRecorder, MappedPolicy, MockEnvironment, run_episode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    params = json.loads(args.request.read_text())
    passed = 0
    policy = MappedPolicy(reset=lambda: None, infer=lambda obs: [{"command": [0.0]}] * 2,
                          observation_mapper=lambda obs: obs, action_mapper=lambda value: value)
    print("[协议检查] CPU mock，不加载模型，不计入真实 benchmark 成功率。", flush=True)
    with JsonlRecorder(args.output / "events.jsonl") as recorder:
        for index in range(params["episodes"]):
            with MockEnvironment(finish_after=3) as env:
                execute = env.execute_fn
                def step(action):
                    time.sleep(0.03)
                    return execute(action)
                env.execute_fn = step
                result = run_episode(env, policy, max_steps=10, seed=params["seed"], on_event=recorder)
            passed += result.success is True
            print(f"[episode {index + 1}/{params['episodes']}] 协议闭环通过，执行 {result.steps} 步", flush=True)
    metrics = dict(real_evaluation=False, protocol_passed=passed, protocol_total=params["episodes"], episodes=params["episodes"])
    (args.output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
