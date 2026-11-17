"""Evaluation scope, score reconciliation and batch lifecycle, without model dependencies."""

import json
from pathlib import Path
import shlex
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from XPolicyLab.web.catalog import Catalog, ValidationError
from XPolicyLab.web.evaluation import LIBERO_STANDARD_SUITES, LIBERO_SUITE_TASKS, libero_metrics, libero_suites, parse_libero_log
from XPolicyLab.web.jobs import Manager


def client_log(suite, trials):
    lines = []
    successes = 0
    for task in range(LIBERO_SUITE_TASKS[suite]):
        outcomes = [episode % 2 == 0 for episode in range(trials)]
        lines += [f"Task: task_{task}", *[f"Success: {value}" for value in outcomes],
                  f"Current task success rate: {sum(outcomes) / trials}"]
        successes += sum(outcomes)
    total = LIBERO_SUITE_TASKS[suite] * trials
    return "\n".join([*lines, f"Total success rate: {successes / total}", f"Total episodes: {total}"]) + "\n"


class ScoreTests(unittest.TestCase):
    def test_known_suite_counts_and_standard_versus_extended_scope(self):
        self.assertEqual(libero_suites("all"), list(LIBERO_STANDARD_SUITES))
        self.assertNotIn("libero_90", libero_suites("all"))
        self.assertEqual(sum(LIBERO_SUITE_TASKS[suite] for suite in libero_suites("all_with_90")), 130)

    def test_task_and_total_results_reconcile_from_integer_outcomes(self):
        result = parse_libero_log(client_log("libero_10", 50), "libero_10", 50)
        self.assertEqual((result["episodes"], result["successes"]), (500, 250))
        self.assertEqual(len(result["tasks"]), 10)

    def test_missing_short_inconsistent_and_exception_results_are_rejected(self):
        valid = client_log("libero_10", 2)
        for text in ("", valid.replace("Total episodes: 20", "Total episodes: 19"),
                     valid.replace("Success: True", "Success: False", 1),
                     valid.replace("Current task success rate: 0.5", "Current task success rate: nan", 1),
                     valid + "\nCaught exception: simulator failed"):
            with self.subTest(text=text[-90:]), self.assertRaises(ValueError):
                parse_libero_log(text, "libero_10", 2)

    def test_macro_and_episode_weighted_averages_are_separate(self):
        results = [dict(suite="libero_10", episodes=500, successes=500, success_rate=1),
                   dict(suite="libero_90", episodes=4500, successes=0, success_rate=0)]
        metrics = libero_metrics(["libero_10", "libero_90"], 50, results)
        self.assertEqual(metrics["success_rate"], 0.5)
        self.assertEqual(metrics["weighted_success_rate"], 0.1)
        self.assertEqual(metrics["report_scope"], "extended_with_90")
        partial = libero_metrics(["libero_10", "libero_90"], 50, results[:1])
        self.assertFalse(partial["complete"])
        self.assertNotIn("success_rate", partial)

    def test_task_budget_mismatch_cannot_hide_behind_a_correct_total(self):
        text = client_log("libero_10", 4)
        text = text.replace("Task: task_0\n", "Task: task_0\nSuccess: True\nSuccess: False\n")
        text = text.replace("Task: task_1\nSuccess: True\nSuccess: False\n", "Task: task_1\n")
        with self.assertRaisesRegex(ValueError, "某任务"):
            parse_libero_log(text, "libero_10", 4)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="robolab-evaluation-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "checkout"
        (self.root / "configs").mkdir(parents=True)
        (self.root / "configs/policy_workspace.json").write_text(json.dumps({"active_policies": ["Pi_05", "demo_policy"]}))
        self.adapter = self.root / "policy/Pi_05"
        (self.adapter / "checkpoints/run/29999/params").mkdir(parents=True)
        (self.adapter / "openpi/.venv/bin").mkdir(parents=True)
        (self.adapter / "openpi/.venv/bin/python").symlink_to(sys.executable)
        self.client = self.base / "client"
        self.client.mkdir()
        (self.client / "main.py").touch()
        self.config = dict(libero=dict(client_root=str(self.client), client_python=sys.executable, uv_bin=sys.executable,
                                       startup_timeout_s=5, timeout_s=5),
                           standard={"RoboDojo": dict(eval_env="simulation", tasks=["task_a", "task_b"],
                                                      policies=["Pi_05"], robots=["arx_x5"])},
                           policy_environments={"Pi_05": "uv"})
        self.catalog = Catalog(self.config, self.root)
        self.manager = None

    def parameters(self, **overrides):
        return dict(policy="Pi_05", benchmark="libero", task="all", checkpoint="run/29999", **overrides)

    def test_default_batch_has_four_suites_and_2000_episodes(self):
        params = self.catalog.validate(self.parameters())
        self.assertEqual(params["episodes"], 50)
        self.assertEqual(params["expected_episodes"], 2000)
        self.assertEqual(params["tasks"], list(LIBERO_STANDARD_SUITES))
        self.assertEqual(params["evaluation_protocol"], "50_trials_per_task")
        self.assertNotIn("max_steps", params)  # LIBERO limits come from its native client.
        smoke = self.catalog.validate(self.parameters(episodes=3))
        self.assertEqual(smoke["expected_episodes"], 120)
        self.assertEqual(smoke["evaluation_protocol"], "smoke")

    def test_extended_all_is_explicit_and_unknown_selection_is_rejected(self):
        raw = self.parameters()
        raw["task"] = "all_with_90"
        self.assertEqual(self.catalog.validate(raw)["expected_episodes"], 6500)
        raw["task"] = "libero_100"
        with self.assertRaises(ValidationError):
            self.catalog.validate(raw)

    def prepare_standard(self):
        (self.base / "env_cfg").mkdir()
        (self.base / "env_cfg/arx_x5.yml").touch()
        (self.base / "scripts").mkdir()
        (self.base / "scripts/eval_policy.sh").touch()
        params = self.parameters()
        params.update(benchmark="RoboDojo", task="all", robot="arx_x5")
        with patch("XPolicyLab.web.catalog.shutil.which", return_value=sys.executable):
            return self.catalog.validate(params)

    def test_standard_task_batch_is_a_configured_subset_with_native_budget(self):
        params = self.prepare_standard()
        self.assertEqual(params["tasks"], ["task_a", "task_b"])
        self.assertIsNone(params["episodes"])
        self.assertEqual(params["coverage"], "configured_tasks")
        self.assertEqual(params["evaluation_protocol"], "external_client_config")
        snapshot = self.catalog.snapshot()
        robotwin = next(item for item in snapshot["benchmarks"] if item["id"] == "RoboTwin")
        self.assertFalse(robotwin["ready"])
        self.assertEqual(robotwin["policies"], [])

    def prepare_fake_processes(self, fail_suite="", pause_suite=""):
        # A real TCP subprocess replaces the GPU server; real CLI clients emit fixture results.
        server = self.base / "server.py"
        server.write_text("import os,socket\nprint('FAKE_MODEL_STARTED',flush=True)\ns=socket.socket()\ns.bind(('127.0.0.1',int(os.environ['POLICY_PORT'])))\ns.listen()\nwhile True:\n c,_=s.accept()\n c.close()\n")
        client = self.base / "evaluate.py"
        client.write_text(
            "import sys,time\nsuite=sys.argv[1];trials=int(sys.argv[2])\n"
            f"if suite == {pause_suite!r}: time.sleep(10)\n"
            "n=90 if suite=='libero_90' else 10\ntotal=0\n"
            "for task in range(n):\n successes=0\n for i in range(trials):\n  outcome=i%2==0\n  successes+=outcome\n  print(f'Success: {outcome}',flush=True)\n total+=successes\n print(f'Current task success rate: {successes/trials}',flush=True)\n"
            "print(f'Total success rate: {total/(n*trials)}',flush=True)\n"
            f"reported = n * trials - int(suite == {fail_suite!r})\nprint('Total episodes:', reported, flush=True)\n"
        )
        for name, target in (("serve_libero.sh", server), ("eval_libero.sh", client)):
            (self.adapter / name).write_text(f"#!/bin/bash\nexec {shlex.quote(sys.executable)} -u {shlex.quote(str(target))} \"$@\"\n")
        self.manager = Manager(self.catalog, self.base / "history")
        self.addCleanup(self.manager.close)

    def finish(self, run_id):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            run = self.manager.store.get(run_id)
            if run["status"] not in {"queued", "running", "cancelling"}:
                return run
            time.sleep(0.03)
        self.fail("fixture evaluation did not finish")

    def enqueue(self, params):
        with patch("XPolicyLab.evaluation.catalog.shutil.which", return_value=sys.executable):
            return self.manager.create(params)["id"]

    def test_four_suite_batch_loads_once_and_saves_each_suite(self):
        self.prepare_fake_processes()
        run_id = self.enqueue(self.catalog.validate(self.parameters()))
        run = self.finish(run_id)
        self.assertEqual(run["status"], "succeeded", run["error"])
        self.assertEqual(run["metrics"]["episodes"], 2000)
        self.assertEqual(run["metrics"]["successes"], 1000)
        self.assertEqual(run["metrics"]["success_rate"], 0.5)
        self.assertEqual(run["metrics"]["report_scope"], "libero_four_suites")
        directory = self.manager.store.directory(run_id)
        self.assertEqual((directory / "console.log").read_text().count("FAKE_MODEL_STARTED"), 1)
        for suite in LIBERO_STANDARD_SUITES:
            self.assertTrue((directory / "suites" / suite / "client.log").is_file())
        self.assertTrue(json.loads((directory / "metrics.json").read_text())["complete"])

    def test_incomplete_second_suite_fails_and_preserves_first_suite(self):
        self.prepare_fake_processes(fail_suite="libero_object")
        run_id = self.enqueue(self.catalog.validate(self.parameters(episodes=2)))
        run = self.finish(run_id)
        self.assertEqual(run["status"], "failed")
        self.assertIn("预算不完整", run["error"])
        self.assertEqual([suite["suite"] for suite in run["metrics"]["suites"]], ["libero_spatial"])
        self.assertFalse(run["metrics"]["complete"])
        self.assertNotIn("success_rate", run["metrics"])

    def test_cancel_batch_preserves_completed_suites(self):
        self.prepare_fake_processes(pause_suite="libero_object")
        run_id = self.enqueue(self.catalog.validate(self.parameters(episodes=2)))
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            run = self.manager.store.get(run_id)
            if "[2/4]" in run["stage"]:
                break
            time.sleep(0.02)
        else:
            self.fail("second suite never started")
        self.manager.cancel(run_id)
        run = self.finish(run_id)
        self.assertEqual(run["status"], "cancelled")
        self.assertEqual(len(run["metrics"]["suites"]), 1)
        self.assertFalse(run["metrics"]["complete"])

    def test_standard_batch_executes_each_task_without_inventing_success_scores(self):
        params = self.prepare_standard()
        self.prepare_fake_processes()
        (self.adapter / "eval.sh").write_text('#!/bin/bash\nset -e\nprintf "TASK=%s\\n" "$2"\n')
        run_id = self.enqueue(params)
        run = self.finish(run_id)
        self.assertEqual(run["status"], "succeeded", run["error"])
        self.assertEqual([task["task"] for task in run["metrics"]["tasks"]], ["task_a", "task_b"])
        self.assertNotIn("success_rate", run["metrics"])
        self.assertTrue(run["metrics"]["complete"])


if __name__ == "__main__":
    unittest.main()
