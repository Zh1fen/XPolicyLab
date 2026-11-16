"""Verify launch commands without loading a model, touching checkpoints, or starting a simulator."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Pi05LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="xpl-launch-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = self.root / "Pi_05"
        (self.policy / "openpi").mkdir(parents=True)
        for name in ("train.sh", "serve_libero.sh", "eval_libero.sh"):
            shutil.copy(ROOT / "policy/Pi_05" / name, self.policy / name)
        self.capture = self.root / "capture.json"
        self.stub = self.root / "uv"
        self.stub.write_text(
            "#!/usr/bin/env python3\nimport json, os, sys\nfrom pathlib import Path\n"
            "Path(os.environ['CAPTURE']).write_text(json.dumps({'argv':sys.argv[1:], 'cwd':os.getcwd(), "
            "'gpu':os.environ.get('CUDA_VISIBLE_DEVICES'), 'egl':os.environ.get('MUJOCO_EGL_DEVICE_ID')}))\n"
        )
        self.stub.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ["PATH"],
                        CAPTURE=str(self.capture), OPENPI_LOCAL_CACHE_ROOT=str(self.root / "cache"))

    def run_script(self, name, *args, extra_env=None):
        return subprocess.run(["bash", str(self.policy / name), *args], cwd=self.root,
                              env=self.env | (extra_env or {}), capture_output=True, text=True)

    def test_training_never_implicitly_overwrites(self):
        for extra in ([], ["--resume"], ["--overwrite"]):
            result = self.run_script("train.sh", "Libero", "test", "franka", "ee", "0", "0,1", *extra)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = json.loads(self.capture.read_text())["argv"]
            self.assertEqual("--overwrite" in args, "--overwrite" in extra)
            self.assertEqual("--resume" in args, "--resume" in extra)
            self.assertFalse((self.policy / "checkpoints").exists())

    def test_native_server_uses_explicit_checkpoint_and_port(self):
        checkpoint = self.root / "checkpoint with spaces" / "29999"
        (checkpoint / "params").mkdir(parents=True)
        result = self.run_script("serve_libero.sh", extra_env={
            "PI05_CHECKPOINT_DIR": str(checkpoint), "POLICY_PORT": "8123", "POLICY_GPU_ID": "2",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads(self.capture.read_text())
        self.assertIn(str(checkpoint), captured["argv"])
        self.assertIn("8123", captured["argv"])
        self.assertEqual(captured["gpu"], "2")

    def test_native_client_uses_explicit_environment_and_metadata(self):
        client = self.root / "client with spaces"
        client.mkdir()
        (client / "main.py").write_text("# stub\n")
        result = self.run_script("eval_libero.sh", "libero_goal", "2", extra_env={
            "LIBERO_CLIENT_ROOT": str(client), "LIBERO_PYTHON": str(self.stub),
            "PI05_CHECKPOINT_STEP": "29000", "EVAL_GPU_ID": "3", "EVAL_SEED": "42",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads(self.capture.read_text())
        self.assertEqual(captured["cwd"], str(client))
        self.assertEqual(captured["egl"], "3")
        self.assertIn("29000", captured["argv"])
        self.assertIn("42", captured["argv"])

    def test_missing_required_config_fails_before_launch(self):
        env = {key: value for key, value in self.env.items()
               if key not in {"PI05_CHECKPOINT_DIR", "LIBERO_CLIENT_ROOT", "PI05_CHECKPOINT_STEP"}}
        for name in ("serve_libero.sh", "eval_libero.sh"):
            result = subprocess.run(["bash", str(self.policy / name)], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.capture.exists())


if __name__ == "__main__":
    unittest.main()
