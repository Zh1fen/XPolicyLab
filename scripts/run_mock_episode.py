#!/usr/bin/env python3
"""运行无模型、无硬件的统一环境接口闭环；可选保存逐步 JSONL 反馈。"""

import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT.parent), str(ROOT)]

from XPolicyLab.environment import JsonlRecorder, MappedPolicy, MockEnvironment, run_episode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finish-after", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--execute-horizon", type=int, default=2)
    parser.add_argument("--record", type=Path, help="反馈事件 JSONL；不保存图像")
    args = parser.parse_args()
    policy = MappedPolicy(reset=lambda: None, infer=lambda obs: [{"command": [0.0]}] * 4,
                          observation_mapper=lambda obs: obs, action_mapper=lambda actions: actions)
    context = JsonlRecorder(args.record) if args.record is not None else nullcontext(None)
    with MockEnvironment(finish_after=args.finish_after) as env, context as recorder:
        result = run_episode(env, policy, max_steps=args.max_steps,
                             execute_horizon=args.execute_horizon, on_event=recorder)
    print(json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
