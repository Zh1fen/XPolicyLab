"""standard evaluation backend."""
import shutil
from ..common import ValidationError
from ..snapshot import resolve_environment


def describe(catalog, backend_id):
    name = backend_id
    entry = catalog.config.get("standard", {}).get(name, {})
    missing = []
    if not (catalog.root.parent / "scripts/eval_policy.sh").is_file():
        missing.append("父工作区缺少 scripts/eval_policy.sh")
    if not (catalog.root.parent / "env_cfg").is_dir():
        missing.append("父工作区缺少 env_cfg/")
    if shutil.which("conda") is None:
        missing.append("当前 PATH 没有 conda")
    if not entry.get("eval_env"):
        missing.append(f"配置 standard.{name}.eval_env")
    if not entry.get("tasks"):
        missing.append(f"配置 standard.{name}.tasks")
    if not entry.get("policies"):
        missing.append(f"配置 standard.{name}.policies，明确已接入的模型")
    tasks = entry.get("tasks", [])
    return dict(id=name, name=name, kind="simulation", requires_checkpoint=True, policies=entry.get("policies", []),
                           description="按已登记任务调用 adapter；这是本地任务集合，不代表官方完整 benchmark。预算由外部客户端配置决定。",
                           tasks=["all", *tasks] if tasks else [], default_task="all",
                           task_options=[dict(id="all", label=f"全部已登记任务 · {len(tasks)} 项"),
                                         *[dict(id=task, label=task) for task in tasks]] if tasks else [],
                           registered_tasks=tasks, coverage="configured_tasks", robots=entry.get("robots", ["arx_x5"]),
                           ready=not missing, gaps=missing)


def normalize(catalog, raw, params):
    policy = params["policy"]
    bench = params["benchmark"]
    task = params["task"]
    entry = catalog.config["standard"][bench]
    if not catalog.config.get("policy_environments", {}).get(policy):
        raise ValidationError(f"配置 policy_environments.{policy}")
    robot = raw.get("robot", "arx_x5")
    if robot not in entry.get("robots", ["arx_x5"]) or not (catalog.root.parent / "env_cfg" / f"{robot}.yml").is_file():
        raise ValidationError("机器人配置未登记或对应 env_cfg 文件缺失")
    action = raw.get("action_type", "joint")
    if action not in ("joint", "ee"):
        raise ValidationError("action_type 必须为 joint 或 ee")
    params.update(robot=robot, action_type=action)
    params.update(tasks=list(entry["tasks"]) if task == "all" else [task],
                  evaluation_protocol="external_client_config", coverage="configured_tasks")



def execute(ctx):
    run = ctx.run
    run_id, params = run["id"], run["parameters"]
    root = ctx.catalog.root
    directory = ctx.directory
    config = ctx.catalog.config["standard"][params["benchmark"]]
    tasks = params.get("tasks", [params["task"]])
    metrics = dict(real_evaluation=True, complete=False, coverage="configured_tasks", tasks=[],
                   expected_tasks=tasks, note="本地已登记任务；预算与指标由外部客户端决定，不代表官方完整 benchmark")
    ctx.save_metrics(metrics)
    for index, task in enumerate(tasks):
        ctx.check(run_id)
        ctx.stage(f"{params['benchmark']} [{index + 1}/{len(tasks)}] {task}")
        # Task names come only from the trusted config, never from an arbitrary shell command.
        ctx.run_logged(run_id, ["bash", root / "policy" / params["policy"] / "eval.sh",
                                  params["benchmark"], task, ctx.catalog.checkpoint_path(params), params["robot"],
                                  params["action_type"], str(params["seed"]), str(params["policy_gpu"]), str(params["env_gpu"]),
                                  ctx.catalog.config["policy_environments"][params["policy"]], config["eval_env"]],
                          {**resolve_environment(config.get("environment", {})), "EVAL_ENV_TYPE": "sim"}, config.get("timeout_s", 86400), directory / "tasks" / f"{index:03d}" / "client.log")
        metrics["tasks"].append(dict(task=task, process_completed=True))
        metrics["complete"] = len(metrics["tasks"]) == len(tasks)
        ctx.save_metrics(metrics)
    return metrics


def freeze(catalog, params):
    from ..snapshot import fingerprint
    import copy
    import os
    bench, policy = params["benchmark"], params["policy"]
    config = dict(standard={bench: copy.deepcopy(catalog.config["standard"][bench])}, policy_environments={policy: catalog.config["policy_environments"][policy]})
    entry = config["standard"][bench]
    fields = ("LINGBOT_VA_CONFIG_NAME", "LINGBOT_VA_CHECKPOINT_PATH", "LINGBOT_VA_STEP", "LINGBOT_VA_BASE_MODEL_PATH",
              "LINGBOT_VA_VA_HOST", "LINGBOT_VA_VA_PORT", "LINGBOT_VA_VA_TIMEOUT")
    entry["environment"] = {**{key: os.environ[key] for key in fields if key in os.environ}, **entry.get("environment", {})}
    files = [fingerprint(catalog.root.parent / "env_cfg" / f"{params['robot']}.yml", "robot environment")]
    return config, files
