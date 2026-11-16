"""Contract, outcome and execution failure tests requiring no model or hardware dependencies."""

import importlib.util
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch

from XPolicyLab.environment import (
    CallbackEnvironment, ClientPolicy, EpisodeError, ExecutionFeedback, JsonlRecorder,
    LocalModelPolicy, MappedPolicy, MockEnvironment, PolicyAdapter, StepEnvAdapter,
    TaskEnvAdapter, run_episode,
    validate_robot_action,
)
from XPolicyLab.environment.contracts import validate_action

ROOT = Path(__file__).resolve().parents[1]
ACTION = {"command": [0.25]}


def observation(step=0):
    return {"vision": {}, "state": {"step": step}, "instruction": "contract test"}


class SpyPolicy(PolicyAdapter):
    def __init__(self, chunk=None):
        self.chunk = [ACTION] * 4 if chunk is None else chunk
        self.observations = []
        self.feedbacks = []
        self.results = []
        self.resets = 0

    def reset(self):
        self.resets += 1

    def predict(self, obs):
        self.observations.append(obs)
        return self.chunk

    def feedback(self, feedback):
        self.feedbacks.append(feedback)

    def finish(self, result):
        self.results.append(result)


class FakeStepEnv:
    def __init__(self, result):
        self.result = result
        self.actions = []
        self.reset_args = None

    def reset(self, **kwargs):
        self.reset_args = kwargs
        return {"raw": 0}, {"reset": True}

    def step(self, action):
        self.actions.append(action)
        return self.result


class EnvironmentTests(unittest.TestCase):
    def test_terminal_chunk_stops_immediately_and_reports_feedback(self):
        env, policy = MockEnvironment(finish_after=2), SpyPolicy()
        result = run_episode(env, policy, max_steps=10, seed=42)
        self.assertEqual((result.steps, result.policy_calls, result.success), (2, 1, True))
        self.assertTrue(result.terminated)
        self.assertFalse(result.truncated)
        self.assertEqual(env.seed, 42)
        self.assertEqual(env.stop_reasons, ["terminated"])
        self.assertEqual(len(policy.feedbacks), 2)
        self.assertEqual(len(policy.results), 1)
        self.assertEqual(len(env.actions), 2)

    def test_execute_horizon_reobserves_before_next_prediction(self):
        env, policy = MockEnvironment(finish_after=3), SpyPolicy()
        result = run_episode(env, policy, max_steps=10, execute_horizon=1)
        self.assertEqual(result.policy_calls, 3)
        self.assertEqual([x["state"]["mock_step"] for x in policy.observations], [0, 1, 2])

    def test_step_limit_is_not_success_or_environment_termination(self):
        env, policy = MockEnvironment(finish_after=100), SpyPolicy()
        result = run_episode(env, policy, max_steps=2)
        self.assertEqual(result.reason, "step_limit")
        self.assertTrue(result.truncated)
        self.assertFalse(result.terminated)
        self.assertIsNone(result.success)
        self.assertEqual(env.stop_reasons, ["step_limit"])

    def test_cancellation_discards_remaining_chunk(self):
        env, policy = MockEnvironment(finish_after=10), SpyPolicy()
        result = run_episode(env, policy, max_steps=10, should_stop=lambda: env.steps >= 1)
        self.assertEqual(result.steps, 1)
        self.assertEqual(result.reason, "cancelled")
        self.assertEqual(len(env.actions), 1)
        self.assertTrue(result.truncated)

    def test_empty_and_malformed_chunks_never_execute(self):
        for chunk in ([], {"actions": [ACTION]}, [ACTION, {"command": [float("nan")]}]):
            with self.subTest(chunk=chunk):
                env, policy = MockEnvironment(), SpyPolicy(chunk)
                with self.assertRaises(EpisodeError) as raised:
                    run_episode(env, policy, max_steps=10)
                self.assertEqual(len(env.actions), 0)
                self.assertEqual(raised.exception.result.reason, "error")
                self.assertEqual(len(policy.results), 1)
                self.assertEqual(env.stop_reasons, ["error"])

    def test_error_after_execute_is_not_retried(self):
        calls = []

        def execute(action):
            calls.append(action)
            raise OSError("device disconnected after command submission")

        env = CallbackEnvironment(reset=lambda *_: None, observe=observation, execute=execute,
                                  stop=lambda why: calls.append(why), close=lambda: None,
                                  action_validator=validate_action)
        with self.assertRaises(EpisodeError) as raised:
            run_episode(env, SpyPolicy(), max_steps=10)
        self.assertEqual(calls, [ACTION, "error"])
        self.assertEqual(raised.exception.result.error_phase, "execute")
        self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_feedback_delivery_failure_stops_after_executed_action(self):
        env, policy = MockEnvironment(finish_after=10), SpyPolicy()

        def fail(_):
            raise ConnectionError("lost feedback connection")

        policy.feedback = fail
        with self.assertRaises(EpisodeError) as raised:
            run_episode(env, policy, max_steps=10)
        self.assertEqual(raised.exception.result.steps, 1)
        self.assertEqual(raised.exception.result.error_phase, "feedback")
        self.assertEqual(len(env.actions), 1)
        self.assertEqual(env.stop_reasons, ["error"])

    def test_stop_failure_is_reported(self):
        env = MockEnvironment(finish_after=1)

        def fail(_):
            raise OSError("stop failed")

        env.stop_fn = fail
        with self.assertRaises(EpisodeError) as raised:
            run_episode(env, SpyPolicy(), max_steps=10)
        self.assertEqual(raised.exception.result.error_phase, "stop")

    def test_reset_failure_still_attempts_stop(self):
        env, policy = MockEnvironment(), SpyPolicy()

        def fail(*_):
            raise ValueError("reset failed")

        env.reset_fn = fail
        with self.assertRaises(EpisodeError) as raised:
            run_episode(env, policy, max_steps=10)
        self.assertEqual(raised.exception.result.steps, 0)
        self.assertEqual(raised.exception.result.error_phase, "reset")
        self.assertEqual(env.stop_reasons, ["error"])

    def test_finish_failure_keeps_execution_count(self):
        policy, env = SpyPolicy(), MockEnvironment(finish_after=1)

        def fail(_):
            raise ConnectionError("trial_end failed")

        policy.finish = fail
        with self.assertRaises(EpisodeError) as raised:
            run_episode(env, policy, max_steps=10)
        self.assertEqual(raised.exception.result.steps, 1)
        self.assertEqual(raised.exception.result.error_phase, "finish")
        self.assertEqual(env.stop_reasons, ["terminated"])

    def test_keyboard_interrupt_stops_and_is_reraised(self):
        env, policy = MockEnvironment(), SpyPolicy()

        def interrupt(_):
            raise KeyboardInterrupt

        policy.predict = interrupt
        with self.assertRaises(KeyboardInterrupt):
            run_episode(env, policy, max_steps=10)
        self.assertEqual(env.stop_reasons, ["cancelled"])
        self.assertEqual(len(policy.results), 1)

    def test_lifecycle_and_idempotent_close(self):
        env = MockEnvironment(finish_after=1)
        with self.assertRaises(RuntimeError):
            env.step(ACTION)
        env.reset()
        env.step(ACTION)
        with self.assertRaises(RuntimeError):
            env.step(ACTION)
        env.stop("done")
        env.close()
        env.close()
        self.assertEqual(env.stop_reasons, ["done"])
        self.assertTrue(env.closed)
        with self.assertRaises(RuntimeError):
            env.reset()

    def test_invalid_budgets_fail_before_reset(self):
        for kwargs in ({"max_steps": 0}, {"max_steps": True}, {"max_steps": 1, "execute_horizon": 0}):
            env, policy = MockEnvironment(), SpyPolicy()
            with self.assertRaises(ValueError):
                run_episode(env, policy, **kwargs)
            self.assertEqual(policy.resets, 0)

    def test_jsonl_records_outcomes_without_observations(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "events.jsonl"
            with JsonlRecorder(path) as recorder:
                run_episode(MockEnvironment(finish_after=2), SpyPolicy(), max_steps=10, on_event=recorder)
            events = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual([e["event"] for e in events], ["reset", "step", "step", "episode_end"])
        self.assertEqual(events[-1]["result"]["steps"], 2)
        self.assertTrue(events[-1]["result"]["success"])
        self.assertNotIn("observation", json.dumps(events))

    def test_recorder_error_stops_motion(self):
        env, policy = MockEnvironment(finish_after=10), SpyPolicy()

        def record(event):
            if event["event"] == "step":
                raise OSError("disk full")

        with self.assertRaises(EpisodeError) as raised:
            run_episode(env, policy, max_steps=10, on_event=record)
        self.assertEqual(raised.exception.result.steps, 1)
        self.assertEqual(raised.exception.result.error_phase, "record")


class SimulatorAdapterTests(unittest.TestCase):
    def wrap(self, raw, **kwargs):
        native = FakeStepEnv(raw)
        env = StepEnvAdapter(native, observation_mapper=lambda _: observation(),
                             action_mapper=lambda action: [action["command"][0]], **kwargs)
        return native, env

    def test_five_tuple_maps_actions_and_unknown_success(self):
        native, env = self.wrap(({"raw": 1}, 100.0, True, False, {}))
        env.reset(seed=7, options={"layout": 1})
        result = env.step(ACTION)
        self.assertEqual(native.actions, [[0.25]])
        self.assertEqual(native.reset_args, {"seed": 7, "options": {"layout": 1}})
        self.assertTrue(result.feedback.terminated)
        self.assertIsNone(result.feedback.success)  # even with positive reward and done=True

    def test_four_tuple_time_limit_is_truncation(self):
        _, env = self.wrap(({}, 0, True, {"TimeLimit.truncated": True}))
        env.reset()
        feedback = env.step(ACTION).feedback
        self.assertFalse(feedback.terminated)
        self.assertTrue(feedback.truncated)
        self.assertIsNone(feedback.success)

    def test_success_is_explicit_and_independent_from_done(self):
        for value in (True, False):
            _, env = self.wrap(({}, 0, True, False, {"success": value}))
            env.reset()
            self.assertEqual(env.step(ACTION).feedback.success, value)

    def test_custom_reset_and_success_mapping(self):
        _, env = self.wrap(({}, 0, False, True, {"status": "solved"}),
                           reset_fn=lambda seed, options: ({}, {"seed": seed}),
                           success_fn=lambda obs, info: info["status"] == "solved")
        self.assertEqual(env.reset(seed=3).info["seed"], 3)
        self.assertTrue(env.step(ACTION).feedback.success)

    def test_nonboolean_done_and_success_are_not_silently_coerced(self):
        for raw in (({}, 1, "false", False, {}), ({}, 0, True, False, {"success": "false"})):
            _, env = self.wrap(raw)
            env.reset()
            with self.assertRaises(TypeError):
                env.step(ACTION)

    def test_invalid_legacy_truncation_is_rejected(self):
        _, env = self.wrap(({}, 0, False, {"TimeLimit.truncated": True}))
        env.reset()
        with self.assertRaises(ValueError):
            env.step(ACTION)

    def test_task_env_fallback_does_not_invent_success(self):
        class Task:
            def reset(self): self.steps = 0
            def get_obs(self): return observation(self.steps)
            def take_action(self, action): self.steps += 1
            def is_episode_end(self): return self.steps == 1

        with self.assertRaises(TypeError):
            TaskEnvAdapter(Task())
        env = TaskEnvAdapter(Task(), feedback_fn=lambda task: ExecutionFeedback(terminated=task.is_episode_end()))
        result = run_episode(env, SpyPolicy(), max_steps=10)
        self.assertTrue(result.terminated)
        self.assertIsNone(result.success)
        with self.assertRaises(ValueError):
            env.reset(seed=12)

    def test_task_feedback_can_identify_time_limit(self):
        class Task:
            def reset(self): self.done = False
            def get_obs(self): return observation()
            def take_action(self, action): self.done = True
            def is_episode_end(self): return self.done

        env = TaskEnvAdapter(Task(), feedback_fn=lambda task: ExecutionFeedback(truncated=task.done))
        result = run_episode(env, SpyPolicy(), max_steps=10)
        self.assertTrue(result.truncated)
        self.assertFalse(result.terminated)


class PolicyAdapterTests(unittest.TestCase):
    def test_native_api_requires_and_applies_two_mappings(self):
        seen = []
        policy = MappedPolicy(reset=lambda: seen.append("reset"),
                              infer=lambda obs: seen.append(obs) or {"native": [0.25]},
                              observation_mapper=lambda obs: {"prompt": obs["instruction"]},
                              action_mapper=lambda result: [{"command": result["native"]}])
        result = run_episode(MockEnvironment(finish_after=1), policy, max_steps=3)
        self.assertTrue(result.success)
        self.assertEqual(seen, ["reset", {"prompt": "CPU interface check"}])

    def test_client_feedback_can_be_disabled_for_legacy_servers(self):
        class Client:
            def __init__(self): self.methods = []
            def call(self, func_name, obs=None):
                self.methods.append(func_name)
                return [ACTION] if func_name == "get_action" else None

        client = Client()
        run_episode(MockEnvironment(finish_after=1), ClientPolicy(client, trial_feedback=False), max_steps=3)
        self.assertEqual(client.methods, ["reset", "update_obs", "get_action"])

    @unittest.skipUnless(importlib.util.find_spec("numpy") and importlib.util.find_spec("cv2"), "needs core dependencies")
    def test_local_model_uses_shared_decoder_and_receives_feedback(self):
        import numpy as np
        from XPolicyLab.utils.process_data import encode_image_bit

        class Model:
            def reset(self): self.feedbacks = []
            def update_obs(self, obs): self.obs = obs
            def get_action(self): return [ACTION]
            def on_execution_feedback(self, feedback): self.feedbacks.append(feedback)
            def on_trial_end(self, result): self.result = result

        model = Model()
        env = MockEnvironment(finish_after=1)
        image = np.zeros((16, 16, 3), dtype=np.uint8)
        image[..., 0] = 240
        env.observe_fn = lambda: dict(observation(), vision={"cam_head": {"color": encode_image_bit(image)}})
        run_episode(env, LocalModelPolicy(model), max_steps=3)
        self.assertIsInstance(model.obs["vision"]["cam_head"]["color"], np.ndarray)
        self.assertGreater(model.obs["vision"]["cam_head"]["color"][..., 0].mean(), 230)
        self.assertTrue(model.feedbacks[0]["success"])
        self.assertTrue(model.result["success"])

    @unittest.skipUnless(importlib.util.find_spec("numpy") and importlib.util.find_spec("cv2"), "needs core dependencies")
    def test_robot_action_validation_uses_shared_dimensions(self):
        import numpy as np
        from XPolicyLab.utils.process_data import unpack_robot_state

        dimensions = json.loads((ROOT / "utils/robot/_robot_info.json").read_text())["arx_x5"]
        width = sum(dimensions["arm_dim"]) + sum(dimensions["ee_dim"])
        action = unpack_robot_state(np.zeros(width), "joint", dimensions, source_type="obs")
        with patch("XPolicyLab.utils.process_data.get_robot_action_dim_info", return_value=dimensions) as lookup:
            validate_robot_action(action, "arx_x5", "joint")
            lookup.assert_called_with("arx_x5")
            with self.assertRaises(ValueError):
                validate_robot_action(dict(action, extra=[0.0]), "arx_x5", "joint")

    def test_feedback_and_action_validation_reject_invalid_values(self):
        for kwargs in ({"success": "false"}, {"reward": float("nan")}, {"terminated": 1}):
            with self.assertRaises((ValueError, TypeError)):
                ExecutionFeedback(**kwargs)
        for action in ({}, {"command": [[1.0]]}, {"command": [True]}, {"command": [float("inf")]}):
            with self.assertRaises((ValueError, TypeError)):
                validate_action(action)

    def test_mock_cli_runs_without_robot_or_model(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/run_mock_episode.py"), "--finish-after", "2"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["steps"], 2)


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in
                         ("numpy", "cv2", "websockets", "msgpack_numpy", "pydantic")), "needs core dependencies")
class WebsocketEnvironmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_server_receives_step_and_trial_feedback(self):
        from client_server.ws import PolicyServer, PolicyServerConfig, WsModelClient
        from XPolicyLab.model_template import ModelTemplate

        class ProbeModel(ModelTemplate):
            def __init__(self): self.feedbacks = []; self.results = []
            def reset(self): self.resets = getattr(self, "resets", 0) + 1
            def update_obs(self, obs): self.observation = obs
            def get_action(self): return [ACTION] * 4
            def on_execution_feedback(self, feedback): self.feedbacks.append(feedback)
            def on_trial_end(self, result): self.results.append(result)

        model = ProbeModel()
        server = PolicyServer(model, PolicyServerConfig(host="127.0.0.1", port=0))
        await server.start()

        def rollout():
            with WsModelClient(url=server.url, evaluation_id="environment-contract", trial_id="trial-1",
                               connect_timeout_s=2, request_timeout_s=3, handshake_timeout_s=2) as client:
                with MockEnvironment(finish_after=2) as env:
                    return run_episode(env, ClientPolicy(client, step_feedback=True), max_steps=5)

        try:
            result = await asyncio.wait_for(asyncio.to_thread(rollout), timeout=15)
        finally:
            await server.stop()
        self.assertTrue(result.success)
        self.assertEqual(model.resets, 1)
        self.assertEqual([f["success"] for f in model.feedbacks], [None, True])
        self.assertEqual([f["env_step"] for f in model.feedbacks], [1, 2])
        self.assertEqual(len(model.results), 1)
        self.assertEqual(model.results[0]["steps"], 2)
        self.assertTrue(model.results[0]["terminated"])
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "feedback.jsonl"
            # Restart on a new OS-selected port, then pass the newly bound URL to the CLI.
            await server.start()
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(ROOT / "scripts/run_environment.py"),
                "--env-factory", "XPolicyLab.environment.mock:create_mock_environment",
                "--policy-url", server.url, "--max-steps", "5", "--step-feedback", "--record", str(path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                await server.stop()
            self.assertEqual(process.returncode, 0, stderr.decode())
            summary = json.loads(stdout.decode().splitlines()[-1])
            self.assertEqual(summary["steps"], 3)
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(events[-1]["event"], "episode_end")


class EnvironmentLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="xpl-env-launch-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        utils = self.root / "XPolicyLab/utils"
        utils.mkdir(parents=True)
        for name in ("run_unified_env_client.sh", "run_real_env_client.sh", "run_sim_env_client.sh"):
            shutil.copy2(ROOT / "utils" / name, utils)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        conda_root = self.root / "conda"
        (conda_root / "etc/profile.d").mkdir(parents=True)
        (conda_root / "etc/profile.d/conda.sh").write_text("conda() { return 0; }\n")
        conda = bin_dir / "conda"
        conda.write_text("#!/usr/bin/env python3\nimport os\nprint(os.environ['TEST_CONDA_ROOT'])\n")
        conda.chmod(0o755)
        python = bin_dir / "python"
        python.write_text("#!/usr/bin/env python3\nimport json,sys,os\nfrom pathlib import Path\n"
                          "Path(os.environ['TEST_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n")
        python.chmod(0o755)
        self.capture = self.root / "capture.json"
        self.env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
                        TEST_CONDA_ROOT=str(conda_root), TEST_CAPTURE=str(self.capture),
                        XPOLICYLAB_ENV_FACTORY="project.robot:create_env", XPOLICYLAB_MAX_STEPS="9")
        self.args = ["false", "test-env", "12345", "bench", "task", "robot", "Pi_05", "action_type=joint",
                     str(self.root), "7", "0", "127.0.0.1", "ws"]

    def run_launcher(self, name, env=None, args=None):
        return subprocess.run(["bash", str(self.root / "XPolicyLab/utils" / name), *(args or self.args)],
                              env=env or self.env, capture_output=True, text=True)

    def test_both_sim_and_real_use_the_same_factory_entry(self):
        for name in ("run_sim_env_client.sh", "run_real_env_client.sh"):
            result = self.run_launcher(name)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = json.loads(self.capture.read_text())
            self.assertEqual(args[0], str(self.root / "XPolicyLab/scripts/run_environment.py"))
            self.assertIn("project.robot:create_env", args)
            self.assertIn("ws://127.0.0.1:12345", args)
            self.assertIn("9", args)
            self.assertIn("action_type=joint", args)

    def test_factory_requires_explicit_budget(self):
        env = dict(self.env)
        del env["XPOLICYLAB_MAX_STEPS"]
        result = self.run_launcher("run_unified_env_client.sh", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.capture.exists())

    def test_factory_rejects_batch_mode(self):
        result = self.run_launcher("run_unified_env_client.sh", args=["true", *self.args[1:]])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.capture.exists())


if __name__ == "__main__":
    unittest.main()
