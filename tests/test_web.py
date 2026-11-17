"""HTTP, persistent history and subprocess lifecycle tests using CPU-only protocol runs."""

import http.client
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from XPolicyLab.web.catalog import Catalog, ValidationError, ROOT
from XPolicyLab.web.server import ConsoleServer
from XPolicyLab.web.store import Store


def request_parameters(**values):
    return dict(policy="demo_policy", benchmark="protocol", task="interface_check", episodes=2, seed=7, **values)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()

    def test_only_selected_policies_are_exposed(self):
        snapshot = self.catalog.snapshot()
        self.assertEqual(len(snapshot["policies"]), 8)
        self.assertNotIn("ACT", [p["id"] for p in snapshot["policies"]])
        self.assertTrue(snapshot["benchmarks"][0]["ready"])

    def test_invalid_model_task_and_command_strings_are_rejected(self):
        for change in ({"policy": "../ACT"}, {"task": "$(touch /tmp/no)"}, {"episodes": True}, {"episodes": 1000},
                       {"benchmark": "unknown"}, {"policy_gpu": "0; echo bad"}):
            params = request_parameters()
            params.update(change)
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.catalog.validate(params)

    def test_protocol_run_cannot_claim_real_model_inference(self):
        params = request_parameters()
        params["policy"] = "Pi_05"
        with self.assertRaises(ValidationError):
            self.catalog.validate(params)

    def test_unconfigured_hardware_cannot_launch(self):
        params = request_parameters()
        params.update(benchmark="real", task="robot")
        with self.assertRaises(ValidationError):
            self.catalog.validate(params)

    def test_hardware_profile_cannot_be_used_with_the_wrong_model(self):
        catalog = Catalog({"real_profiles": [{"id": "arm-a", "policy": "Pi_05"}, {"id": "arm-b", "policy": "StarVLA"}]})
        params = request_parameters()
        params.update(policy="StarVLA", benchmark="real", task="arm-a")
        with self.assertRaisesRegex(ValidationError, "模型不匹配"):
            catalog.validate(params)


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="xpl-web-test-")
        self.addCleanup(self.temp.cleanup)
        self.server = ConsoleServer(("127.0.0.1", 0), Catalog(), self.temp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        status, html, _ = self.http("GET", "/", auth=False)
        self.assertEqual(status, 200)
        self.token = re.search(r'name="xpl-token" content="([^"]+)"', html.decode())[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def http(self, method, path, data=None, auth=True, headers=None):
        con = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        request_headers = {"Content-Type": "application/json"}
        if auth:
            request_headers["X-XPL-Token"] = self.token
        request_headers.update(headers or {})
        con.request(method, path, body=json.dumps(data) if data is not None else None, headers=request_headers)
        response = con.getresponse()
        body = response.read()
        status, response_headers = response.status, dict(response.getheaders())
        con.close()
        return status, body, response_headers

    def api(self, method, path, data=None):
        status, body, _ = self.http(method, path, data)
        return status, json.loads(body)

    def finish(self, run_id):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            _, run = self.api("GET", f"/api/runs/{run_id}")
            if run["status"] not in {"queued", "running", "cancelling"}:
                return run
            time.sleep(0.05)
        self.fail("CPU fixture did not finish")

    def test_api_requires_session_and_mutations_reject_cookie_only(self):
        self.assertEqual(self.http("GET", "/api/runs", auth=False)[0], 403)
        self.assertEqual(self.http("POST", "/api/runs", request_parameters(), auth=False,
                                   headers={"Cookie": f"xpl_session={self.token}"})[0], 403)
        self.assertEqual(self.http("GET", "/api/runs", headers={"Host": "untrusted.invalid"})[0], 403)

    def test_ip_homepage_establishes_session_without_url_key(self):
        self.server.allowed_hosts.add("192.0.2.8")
        host = {"Host": f"192.0.2.8:{self.server.server_port}"}
        status, body, headers = self.http("GET", "/", auth=False, headers=host)
        self.assertEqual(status, 200)
        self.assertIn("RoboLab", body.decode())
        self.assertIn(self.token, body.decode())
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        session = {**host, "Cookie": cookie}
        self.assertEqual(self.http("GET", "/", auth=False, headers=session)[0], 200)
        self.assertEqual(self.http("GET", "/api/catalog", auth=False, headers=session)[0], 200)
        self.assertEqual(self.http("POST", "/api/runs", request_parameters(), auth=False,
                                   headers=session)[0], 403)

    def test_static_assets_and_catalog_are_live(self):
        for path in ("/style.css", "/app.js"):
            status, body, _ = self.http("GET", path)
            self.assertEqual(status, 200)
            self.assertGreater(len(body), 100)
        status, catalog = self.api("GET", "/api/catalog")
        self.assertEqual(status, 200)
        self.assertEqual(len(catalog["policies"]), 8)

    def test_run_lifecycle_metrics_logs_and_artifacts(self):
        status, run = self.api("POST", "/api/runs", request_parameters(label="接口回归"))
        self.assertEqual(status, 201)
        run = self.finish(run["id"])
        self.assertEqual(run["status"], "succeeded", run.get("error"))
        self.assertFalse(run["metrics"]["real_evaluation"])
        self.assertEqual(run["metrics"]["protocol_passed"], 2)
        self.assertNotIn("success_rate", run["metrics"])
        self.assertIn("revision", run)
        _, log = self.api("GET", f"/api/runs/{run['id']}/logs")
        self.assertIn("CPU mock", log["text"])
        _, next_log = self.api("GET", f"/api/runs/{run['id']}/logs?offset={log['offset']}")
        self.assertEqual(next_log["text"], "")
        _, artifacts = self.api("GET", f"/api/runs/{run['id']}/artifacts")
        self.assertIn("metrics.json", [p["path"] for p in artifacts["files"]])
        status, metrics, _ = self.http("GET", f"/api/runs/{run['id']}/files/metrics.json")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(metrics)["protocol_total"], 2)
        status, partial, headers = self.http("GET", f"/api/runs/{run['id']}/files/metrics.json", headers={"Range": "bytes=0-9"})
        self.assertEqual(status, 206)
        self.assertEqual(len(partial), 10)
        self.assertIn("Content-Range", headers)

    def test_cancel_running_process_and_preserve_history(self):
        params = request_parameters()
        params["episodes"] = 50
        _, run = self.api("POST", "/api/runs", params)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and self.server.manager.store.get(run["id"])["status"] == "queued":
            time.sleep(0.03)
        self.api("POST", f"/api/runs/{run['id']}/cancel", {})
        result = self.finish(run["id"])
        self.assertEqual(result["status"], "cancelled")
        self.assertTrue((Path(self.temp.name) / "history.sqlite3").is_file())

    def test_outside_and_symlink_artifacts_are_not_readable(self):
        _, run = self.api("POST", "/api/runs", request_parameters())
        self.finish(run["id"])
        folder = self.server.manager.store.directory(run["id"])
        (folder / "external.json").symlink_to(ROOT / "configs/policy_workspace.json")
        for path in ("../history.sqlite3", "external.json"):
            status, _, _ = self.http("GET", f"/api/runs/{run['id']}/files/{path}")
            self.assertEqual(status, 403)

    def test_invalid_request_does_not_create_a_run(self):
        params = request_parameters()
        params["policy"] = "bad; command"
        self.assertEqual(self.api("POST", "/api/runs", params)[0], 400)
        self.assertEqual(self.api("GET", "/api/runs")[1]["runs"], [])

    def test_queued_cancellation_never_launches_the_job(self):
        params = request_parameters()
        params["episodes"] = 50
        _, first = self.api("POST", "/api/runs", params)
        _, second = self.api("POST", "/api/runs", request_parameters())
        self.api("POST", f"/api/runs/{second['id']}/cancel", {})
        self.assertEqual(self.finish(second["id"])["status"], "cancelled")
        self.assertFalse((self.server.manager.store.directory(second["id"]) / "console.log").exists())
        self.api("POST", f"/api/runs/{first['id']}/cancel", {})
        self.finish(first["id"])

    def test_worker_error_is_persisted_as_failure(self):
        with patch.object(self.server.manager, "_execute", side_effect=RuntimeError("fixture failure")):
            _, run = self.api("POST", "/api/runs", request_parameters())
            result = self.finish(run["id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("fixture failure", result["error"])

    def test_data_directory_lock_prevents_duplicate_controllers(self):
        with self.assertRaisesRegex(RuntimeError, "已有控制台"):
            ConsoleServer(("127.0.0.1", 0), Catalog(), self.temp.name)


class PersistenceTests(unittest.TestCase):
    def test_history_survives_restart_and_active_runs_are_interrupted(self):
        with tempfile.TemporaryDirectory() as name:
            store = Store(name)
            run = store.create(request_parameters(), "revision")
            store.update(run["id"], status="running")
            restored = Store(name).get(run["id"])
            self.assertEqual(restored["status"], "interrupted")
            self.assertEqual(restored["parameters"]["seed"], 7)


if __name__ == "__main__":
    unittest.main()
