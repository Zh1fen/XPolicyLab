"""protocol evaluation backend."""
import json
import sys


def describe(catalog, backend_id):
    return dict(id="protocol", name="协议检查", kind="debug", uses_episodes=True, default_episodes=3, max_episodes=50, description="CPU", policies=["demo_policy"], tasks=["interface_check"], ready=True, gaps=[])


def normalize(catalog, raw, params):
    pass


def execute(ctx):
    run = ctx.run
    run_id, params = run["id"], run["parameters"]
    root = ctx.catalog.root
    directory = ctx.directory
    ctx.stage("CPU 协议检查")
    process = ctx.spawn(run_id, [sys.executable, root / "scripts/web_worker.py", "--request", directory / "parameters.json", "--output", directory])
    ctx.wait(run_id, process, 120)
    return json.loads((directory / "metrics.json").read_text())


def freeze(catalog, params):
    return {}, []
