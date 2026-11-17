"""Trusted launch configuration and validation for console requests."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

from .common import ValidationError, integer
from .backends import BACKENDS, get_backend

ROOT = Path(__file__).resolve().parents[1]


class Catalog:
    def __init__(self, config=None, root=ROOT):
        self.root = Path(root).resolve()
        self.config = config or {}
        self.policies = json.loads((self.root / "configs/policy_workspace.json").read_text())["active_policies"]

    def path(self, value):
        p = Path(value).expanduser()
        return (p if p.is_absolute() else self.root / p).resolve()

    def checkpoints(self, policy):
        base = self.root / "policy" / policy / "checkpoints"
        for backend in dict.fromkeys(BACKENDS.values()):
            provider = getattr(backend, "checkpoint_choices", None)
            if provider is not None:
                choices = provider(base, policy)
                if choices is not None:
                    return choices
        return [dict(id=run.name, label=run.name) for run in sorted(base.iterdir()) if run.is_dir()] if base.is_dir() else []

    def snapshot(self):
        benchmarks = [backend.describe(self, name) for name, backend in BACKENDS.items()]
        return dict(policies=[dict(id=p, checkpoints=self.checkpoints(p)) for p in self.policies], benchmarks=benchmarks,
                    policy_environments=self.config.get("policy_environments", {}),
                    defaults=dict(policy="demo_policy", benchmark="protocol", task="interface_check", seed=0, episodes=3,
                                  policy_gpu=0, env_gpu=0, robot="arx_x5", action_type="joint"))

    def validate(self, raw):
        if not isinstance(raw, dict):
            raise ValidationError("请求必须为 JSON 对象")
        snapshot = self.snapshot()
        policy, bench = raw.get("policy"), raw.get("benchmark")
        if policy not in self.policies:
            raise ValidationError("模型不在活动策略名单中")
        benchmark = next((b for b in snapshot["benchmarks"] if b["id"] == bench), None)
        if benchmark is None:
            raise ValidationError("未知 benchmark")
        if not benchmark["ready"]:
            raise ValidationError("；".join(benchmark["gaps"]))
        if policy not in benchmark["policies"]:
            raise ValidationError("该模型与评测入口尚未配置兼容关系")
        task = raw.get("task")
        if task not in benchmark["tasks"]:
            raise ValidationError("请选择已登记的任务或 suite")
        label = raw.get("label", "")
        if not isinstance(label, str) or len(label) > 100:
            raise ValidationError("运行名称最长 100 字符")
        result = dict(policy=policy, benchmark=bench, task=task, label=label.strip(), kind=benchmark["kind"],
                      seed=integer(raw.get("seed", 0), "seed", 0, 2147483647),
                      episodes=(None if not benchmark.get("uses_episodes") else integer(raw.get("episodes", benchmark["default_episodes"]), "每任务 episodes", 1, benchmark["max_episodes"])),
                      policy_gpu=integer(raw.get("policy_gpu", 0), "模型 GPU", 0, 127),
                      env_gpu=integer(raw.get("env_gpu", 0), "环境 GPU", 0, 127))
        if benchmark.get("requires_checkpoint"):
            checkpoint = raw.get("checkpoint")
            if checkpoint not in {c["id"] for c in self.checkpoints(policy)}:
                raise ValidationError("请选择当前可用的本地 checkpoint")
            result["checkpoint"] = checkpoint
        get_backend(bench).normalize(self, raw, result)
        return result

    def checkpoint_path(self, params):
        from XPolicyLab.utils.checkpoint_resolver import resolve_checkpoint_root

        policy_dir = self.root / "policy" / params["policy"]
        selected = policy_dir / "checkpoints" / params["checkpoint"]
        return resolve_checkpoint_root({"checkpoint_path": str(selected)}, policy_dir / "checkpoints", policy_dir=policy_dir)
