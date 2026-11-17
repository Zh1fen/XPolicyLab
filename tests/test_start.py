"""Root launcher behavior, configuration precedence and actual local HTTP startup."""

import http.client
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StartScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="robolab-start-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "checkout with spaces"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "configs").mkdir()
        shutil.copy2(ROOT / "start.sh", self.root / "start.sh")
        (self.root / "configs/web.example.json").write_text("{}")
        (self.root / "scripts/run_web.py").write_text(
            "import os,sys,json\nprint(json.dumps({'cwd':os.getcwd(),'args':sys.argv[1:]}))\n"
        )

    def run_start(self, *args, python=sys.executable):
        return subprocess.run([str(self.root / "start.sh"), *args], cwd=self.temp.name,
                              env=dict(os.environ, ROBOLAB_PYTHON=python), capture_output=True, text=True)

    def test_starts_from_another_directory_with_automatic_example_config(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["cwd"], str(self.root))
        self.assertEqual(data["args"], ["--config", "configs/web.example.json"])

    def test_local_config_is_preferred(self):
        (self.root / "configs/web.local.json").write_text("{}")
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["args"], ["--config", "configs/web.local.json"])

    def test_explicit_config_and_other_flags_are_forwarded_after_defaults(self):
        result = self.run_start("--config", "/my/config.json", "--port", "9000")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["args"], ["--config", "configs/web.example.json", "--config", "/my/config.json", "--port", "9000"])

    def test_missing_python_has_a_clear_error(self):
        result = self.run_start(python="/not/a/python")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("找不到 Python", result.stderr)

    def test_actual_root_launcher_serves_robolab_without_model_dependencies(self):
        config = Path(self.temp.name) / "config.json"
        config.write_text("{}")
        process = subprocess.Popen(
            [str(ROOT / "start.sh"), "--port", "0", "--data-dir", str(Path(self.temp.name) / "history"), "--config", str(config)],
            cwd=self.temp.name, env=dict(os.environ, ROBOLAB_PYTHON=sys.executable),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            ready, _, _ = select.select([process.stdout], [], [], 8)
            self.assertTrue(ready, "launcher did not announce startup")
            line = process.stdout.readline()
            self.assertIn("RoboLab 控制台", line)
            port = int(re.search(r"127\.0\.0\.1:(\d+)", line)[1])
            con = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            con.request("GET", "/")
            response = con.getresponse()
            page = response.read().decode()
            self.assertEqual(response.status, 200)
            self.assertIn("RoboLab · 控制台", page)
            self.assertNotIn("XPolicyLab", page)
            self.assertIn("RoboLabConsole", response.getheader("Server"))
            token = re.search(r'name="xpl-token" content="([^"]+)"', page)[1]
            con.request("GET", "/api/catalog", headers={"X-XPL-Token": token})
            response = con.getresponse()
            self.assertEqual(response.status, 200)
            catalog = json.loads(response.read())
            self.assertTrue(catalog["benchmarks"][0]["ready"])
            con.close()
        finally:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            output = process.stdout.read()
            process.stdout.close()
        for text in ("Python", "配置文件", "历史目录", "监听地址", "服务已就绪", "控制台已停止"):
            self.assertIn(text, output)


if __name__ == "__main__":
    unittest.main()
