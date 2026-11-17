#!/usr/bin/env python3
"""CPU-only demo websocket smoke; requires root pyproject dependencies, no conda or real env_cfg."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def check_actions(actions, dims, *, batched: bool) -> None:
    import numpy as np

    batches = actions if batched else [actions]
    if len(batches) != (2 if batched else 1):
        raise AssertionError("Unexpected action batch size")
    expected = {
        "left_arm_joint_state": dims["arm_dim"][0],
        "right_arm_joint_state": dims["arm_dim"][1],
        "left_ee_joint_state": dims["ee_dim"][0],
        "right_ee_joint_state": dims["ee_dim"][1],
    }
    for chunk in batches:
        if not chunk:
            raise AssertionError("Empty action chunk")
        for action in chunk:
            if set(action) != set(expected):
                raise AssertionError(f"Unexpected action keys: {set(action)}")
            for key, width in expected.items():
                array = np.asarray(action[key])
                if array.shape != (width,) or not np.isfinite(array).all():
                    raise AssertionError(f"Invalid action shape or value: {key}")


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    # Import the real core dependencies, without importing any policy model stack.
    sys.path[:0] = [str(ROOT.parent), str(ROOT)]
    import numpy as np
    import yaml
    from client_server.ws import WsModelClient
    from XPolicyLab.utils.process_data import decode_image_bit, encode_image_bit
    from XPolicyLab.environment import ClientPolicy, MockEnvironment, run_episode

    dims = json.loads((ROOT / "utils/robot/_robot_info.json").read_text())["arx_x5"]
    with tempfile.TemporaryDirectory(prefix="xpl-smoke-") as name:
        workspace = Path(name)
        # The real shared helpers read env_cfg next to the importable checkout.
        # Copy only the core + demo: filesystem '..' through a symlink would still
        # resolve against the real checkout and escape the temporary fixture tree.
        checkout = workspace / "XPolicyLab"
        checkout.mkdir()
        for source in ("utils", "client_server", "environment", "policy/demo_policy"):
            shutil.copytree(ROOT / source, checkout / source, ignore=shutil.ignore_patterns("__pycache__"))
        for source in ("__init__.py", "_robolab_compat.py", "XPolicyLab.py", "model_template.py", "setup_policy_server.py", "policy/__init__.py"):
            shutil.copy2(ROOT / source, checkout / source)
        config_root = workspace / "env_cfg"
        (config_root / "robot").mkdir(parents=True)
        (config_root / "sim").mkdir()
        (config_root / "robot/_robot_info.json").write_text(json.dumps({"arx_x5": dims}))
        (config_root / "arx_x5.yml").write_text("config:\n  robot: arx_x5\n  sim: smoke\n")
        (config_root / "sim/smoke.yml").write_text("scene:\n  num_envs: 2\n")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        deploy = yaml.safe_load((ROOT / "policy/demo_policy/deploy.yml").read_text())
        deploy.update(host="127.0.0.1", port=port, env_cfg_type="arx_x5", action_type="joint",
                      bench_name="smoke", task_name="smoke", ckpt_name="demo", seed=0)
        deploy_path = workspace / "deploy.yml"
        deploy_path.write_text(yaml.safe_dump(deploy))
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(workspace), str(workspace / "XPolicyLab")]))
        with (workspace / "server.log").open("w+") as log:
            server = subprocess.Popen(
                [sys.executable, str(workspace / "XPolicyLab/setup_policy_server.py"), "--config_path", str(deploy_path)],
                cwd=workspace, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            client = None
            try:
                client = WsModelClient(
                    url=f"ws://127.0.0.1:{port}", evaluation_id="infra-smoke", trial_id="smoke",
                    connect_timeout_s=2, handshake_timeout_s=2, request_timeout_s=5,
                    max_connect_attempts=30, connect_retry_delay_s=0.1, max_connect_seconds=10,
                )
                image = np.zeros((24, 32, 3), dtype=np.uint8)
                image[..., 0] = 240
                encoded = encode_image_bit(image)
                decoded = decode_image_bit(encoded)
                if decoded.shape != image.shape or decoded[..., 0].mean() < 230 or decoded[..., 2].mean() > 10:
                    raise AssertionError("Shared encode/decode failed RGB roundtrip")
                for encoded_mode in (False, True):
                    colors = [encoded, np.asarray(list(encoded), dtype=np.uint8), image] if encoded_mode else [image] * 3
                    observation = {
                        "vision": {camera: {"color": color} for camera, color in zip(
                            ("cam_head", "cam_left_wrist", "cam_right_wrist"), colors
                        )},
                        "instruction": "CPU smoke test", "env_idx": 0,
                    }
                    client.call("reset")
                    client.call("update_obs", observation)
                    check_actions(client.call("get_action"), dims, batched=False)
                    batch = [observation, dict(observation, env_idx=1)]
                    client.call("update_obs_batch", batch)
                    check_actions(client.call("get_action_batch", [0, 1]), dims, batched=True)
                    print(f"PASS: demo reset, single/batch ws calls, {'mixed encoded' if encoded_mode else 'array'} observations")
                with MockEnvironment(finish_after=3) as mock_env:
                    result = run_episode(mock_env, ClientPolicy(client, step_feedback=True),
                                         max_steps=5, execute_horizon=1)
                    if result.steps != 3 or result.success is not True:
                        raise AssertionError("Unified environment rollout did not finish correctly")
                print("PASS: unified environment -> demo ws model -> execution feedback / trial_end")
            except BaseException:
                log.flush()
                log.seek(0)
                print(log.read(), file=sys.stderr)
                raise
            finally:
                if client is not None:
                    client.close()
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
    print("PASS: shared RGB roundtrip; isolated parent-workspace fixtures cleaned up. No model or simulator evaluated.")


if __name__ == "__main__":
    main()
