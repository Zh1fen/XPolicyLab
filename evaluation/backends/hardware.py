"""hardware evaluation backend."""
import sys
import json
from ..common import ValidationError, integer


def describe(catalog, backend_id):
    profiles = catalog.config.get("real_profiles", [])
    return dict(id="real", name="真机接口", kind="hardware", policies=sorted({p["policy"] for p in profiles}), description="统一环境 factory", tasks=[p["id"] for p in profiles], ready=bool(profiles), gaps=[] if profiles else ["尚未配置硬件 profile"])


def normalize(catalog, raw, params):
    profile = next(p for p in catalog.config["real_profiles"] if p["id"] == params["task"])
    if profile["policy"] != params["policy"]:
        raise ValidationError("该硬件 profile 与所选模型不匹配")
    params["evaluation_protocol"] = "single_episode"
    params["max_steps"] = integer(raw.get("max_steps", 200), "控制步数上限", 1, 100000)


def execute(ctx):
    run = ctx.run
    run_id, params = run["id"], run["parameters"]
    root = ctx.catalog.root
    directory = ctx.directory
    profile = next(p for p in ctx.catalog.config["real_profiles"] if p["id"] == params["task"])
    ctx.stage("统一真机环境接口")
    args = [profile.get("python", sys.executable), root / "scripts/run_environment.py", "--env-factory", profile["env_factory"],
            "--policy-url", profile["policy_url"], "--max-steps", str(params["max_steps"]), "--seed", str(params["seed"]),
            "--record", directory / "events.jsonl", "--policy-name", params["policy"]]
    if profile.get("env_config"):
        args += ["--env-config", ctx.catalog.path(profile["env_config"])]
    process = ctx.spawn(run_id, args)
    ctx.wait(run_id, process, profile.get("timeout_s", 3600))
    return read_result(directory / "events.jsonl")


def read_result(path):
    metrics = {"real_evaluation": True, "success": None, "success_known": False}
    if path.is_file():
        for line in path.read_text().splitlines():
            event = json.loads(line)
            if event.get("event") == "episode_end":
                result = event["result"]
                success = result.get("success")
                if success is not None and type(success) is not bool:
                    raise ValueError("硬件结果 success 必须为 bool 或 null")
                metrics.update({key: result[key] for key in ("success", "terminated", "truncated", "steps", "reason") if key in result})
                metrics["success_known"] = success is not None
    return metrics


def freeze(catalog, params):
    from ..snapshot import fingerprint
    import copy
    from urllib.parse import urlsplit
    selected = next(profile for profile in catalog.config["real_profiles"] if profile["id"] == params["task"])
    profile = copy.deepcopy({key: selected[key] for key in ("id", "policy", "python", "env_factory", "policy_url", "env_config", "timeout_s") if key in selected})
    url = urlsplit(profile.get("policy_url", ""))
    if url.username or url.password or url.query:
        raise ValidationError("policy_url 不应包含凭据；请使用独立的受保护代理地址")
    files = [fingerprint(catalog.path(profile["env_config"]), "hardware environment")] if profile.get("env_config") else []
    return {"real_profiles": [profile]}, files
