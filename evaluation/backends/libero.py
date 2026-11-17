"""libero evaluation backend."""
import socket
import time
import shutil
from ..common import ValidationError
from ..libero import LIBERO_SELECTIONS, LIBERO_SUITE_TASKS, libero_suites, libero_metrics, parse_libero_log


def describe(catalog, backend_id):
    libero = catalog.config.get("libero", {})
    gaps = []
    client = catalog.path(libero["client_root"]) if libero.get("client_root") else None
    if client is None or not (client / "main.py").is_file():
        gaps.append("配置 libero.client_root，指向已有 LIBERO 客户端")
    if client is not None:
        python = catalog.path(libero["client_python"]) if libero.get("client_python") else client / ".venv/bin/python"
        if not python.is_file():
            gaps.append("LIBERO 客户端 Python 不存在")
    if not (catalog.root / "policy/Pi_05/openpi/.venv/bin/python").is_file():
        gaps.append("Pi_05 的 OpenPI 环境尚未安装")
    if shutil.which(libero.get("uv_bin", "uv")) is None:
        gaps.append("找不到 uv")
    if not catalog.checkpoints("Pi_05"):
        gaps.append("Pi_05 没有可选本地 checkpoint")
    return dict(id="libero", name="LIBERO", kind="simulation", uses_episodes=True, requires_checkpoint=True, description="Pi_05 原生 OpenPI 服务与已有 LIBERO 客户端。", policies=["Pi_05"], tasks=[item["id"] for item in LIBERO_SELECTIONS], task_options=LIBERO_SELECTIONS, default_task="all", default_episodes=50, max_episodes=50, suite_task_counts=LIBERO_SUITE_TASKS, ready=not gaps, gaps=gaps)


def normalize(catalog, raw, params):
    suites = libero_suites(params["task"])
    params.update(tasks=suites, expected_episodes=sum(LIBERO_SUITE_TASKS[suite] for suite in suites) * params["episodes"], evaluation_protocol="50_trials_per_task" if params["episodes"] == 50 else "smoke")
    if not params["checkpoint"].rsplit("/", 1)[-1].isdigit():
        raise ValidationError("LIBERO 需要精确到数字 step 的 checkpoint")


def execute(ctx):
    run = ctx.run
    run_id, params = run["id"], run["parameters"]
    root = ctx.catalog.root
    directory = ctx.directory
    config = ctx.catalog.config["libero"]
    suites = params.get("tasks", libero_suites(params["task"]))
    results = []
    ctx.save_metrics(libero_metrics(suites, params["episodes"], results))
    checkpoint = ctx.catalog.checkpoint_path(params)
    client = ctx.catalog.path(config["client_root"])
    python = ctx.catalog.path(config["client_python"]) if config.get("client_python") else client / ".venv/bin/python"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(PI05_CHECKPOINT_DIR=str(checkpoint), PI05_CHECKPOINT_STEP=checkpoint.name,
               PI05_RUN_NAME=checkpoint.parent.name, POLICY_PORT=str(port), POLICY_HOST="127.0.0.1",
               POLICY_GPU_ID=str(params["policy_gpu"]), EVAL_GPU_ID=str(params["env_gpu"]), EVAL_SEED=str(params["seed"]),
               LIBERO_CLIENT_ROOT=str(client), LIBERO_PYTHON=str(python), EVAL_RESULT_ROOT=str(directory / "results"),
               UV_BIN=config.get("uv_bin", "uv"), PI05_TRAIN_CONFIG=config.get("train_config", "pi05_libero"),
               OPENPI_ROOT=config.get("openpi_root", str(root / "policy/Pi_05/openpi")),
               MUJOCO_GL=config.get("mujoco_gl", "egl"))
    ctx.stage("加载 Pi_05 模型")
    server = ctx.spawn(run_id, ["bash", root / "policy/Pi_05/serve_libero.sh"], env)
    deadline = time.monotonic() + config.get("startup_timeout_s", 600)
    while True:
        ctx.check(run_id)
        if server.poll() is not None:
            raise RuntimeError("模型服务启动失败，查看日志获取模型侧错误")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError("模型服务启动超时")
            time.sleep(0.2)
    for index, suite in enumerate(suites):
        ctx.check(run_id)
        ctx.stage(f"LIBERO [{index + 1}/{len(suites)}] {suite}")
        unit_dir = directory / "suites" / suite
        try:
            text = ctx.run_logged(run_id, ["bash", root / "policy/Pi_05/eval_libero.sh", suite, str(params["episodes"])],
                                    dict(env, EVAL_RESULT_ROOT=str(unit_dir / "results")),
                                    config.get("timeout_s", 86400), unit_dir / "client.log")
            results.append(parse_libero_log(text, suite, params["episodes"]))
        except Exception:
            metrics = libero_metrics(suites, params["episodes"], results)
            metrics["incomplete_suite"] = suite
            ctx.save_metrics(metrics)
            raise
        metrics = libero_metrics(suites, params["episodes"], results)
        ctx.save_metrics(metrics)
    return metrics


def freeze(catalog, params):
    from ..snapshot import fingerprint
    import copy
    import os
    config = copy.deepcopy(catalog.config["libero"])
    config["train_config"] = config.get("train_config", os.environ.get("PI05_TRAIN_CONFIG", "pi05_libero"))
    config["openpi_root"] = str(catalog.path(config.get("openpi_root", os.environ.get("OPENPI_ROOT", str(catalog.root / "policy/Pi_05/openpi")))))
    config["mujoco_gl"] = config.get("mujoco_gl", os.environ.get("MUJOCO_GL", "egl"))
    config["uv_bin"] = shutil.which(config.get("uv_bin", "uv")) or config.get("uv_bin", "uv")
    return {"libero": config}, [fingerprint(catalog.path(config["client_root"]) / "main.py", "LIBERO client")]


def checkpoint_choices(base, policy):
    if policy != "Pi_05":
        return None
    choices = []
    if base.is_dir():
        for run in sorted(base.iterdir()):
            if not run.is_dir():
                continue
            steps = [step for step in run.iterdir() if step.is_dir() and step.name.isdigit() and (step / "params").is_dir()]
            for step in sorted(steps, key=lambda step: int(step.name), reverse=True):
                choices.append(dict(id=f"{run.name}/{step.name}", label=f"{run.name} · step {step.name}"))
            if not steps:
                choices.append(dict(id=run.name, label=run.name))
    return choices
