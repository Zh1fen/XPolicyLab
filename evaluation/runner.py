"""Single-worker queue executing explicit argument arrays, with bounded process-group cleanup."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time

from .store import Store, now


class Cancelled(Exception):
    pass


class Manager:
    def __init__(self, catalog, data_dir):
        self.catalog = catalog
        self.store = Store(data_dir)
        self.wake = threading.Event()
        self.shutdown = threading.Event()
        self.cancelled = set()
        self.lock = threading.RLock()
        self.processes = {}
        self.thread = threading.Thread(target=self._loop, name="evaluation-queue", daemon=True)
        self.thread.start()

    def create(self, raw):
        from XPolicyLab.evaluation.snapshot import prepare
        snapshot = prepare(self.catalog, raw)
        with self.lock:
            result = self.store.create(snapshot["parameters"], snapshot["revision"], snapshot)
            self.wake.set()
        return result

    def cancel(self, run_id):
        with self.lock:
            run = self.store.request_cancel(run_id)
            if run["status"] in {"cancelled", "cancelling"}:
                self.cancelled.add(run_id)
                self.wake.set()
        return run

    def _check(self, run_id):
        if self.shutdown.is_set() or run_id in self.cancelled:
            raise Cancelled

    def _spawn(self, run_id, args, env=None, cwd=None):
        self._check(run_id)
        with (self.store.directory(run_id) / "console.log").open("ab", buffering=0) as log:
            log.write(("\n$ " + __import__("shlex").join(map(str, args)) + "\n").encode())
            process = subprocess.Popen(list(map(str, args)), cwd=cwd or self.catalog.root,
                                       env=dict(os.environ, PYTHONUNBUFFERED="1", **(env or {})),
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.setdefault(run_id, []).append(process)
        return process

    def _wait(self, run_id, process, timeout=None):
        start = time.monotonic()
        while process.poll() is None:
            self._check(run_id)
            if timeout is not None and time.monotonic() - start > timeout:
                raise RuntimeError("运行超过配置的超时限制")
            self.shutdown.wait(0.1)
        self._check(run_id)
        if process.returncode:
            raise RuntimeError(f"评测进程退出码 {process.returncode}，请查看运行日志")

    def _cleanup(self, run_id):
        # A completed launcher can leave children behind; address its process group too.
        groups = self.processes.pop(run_id, [])
        for sig, budget in ((signal.SIGINT, 3), (signal.SIGTERM, 2), (signal.SIGKILL, 1)):
            alive = []
            for process in groups:
                try:
                    os.killpg(process.pid, sig)
                    alive.append(process)
                except ProcessLookupError:
                    pass
            if not alive:
                break
            deadline = time.monotonic() + budget
            while time.monotonic() < deadline:
                present = False
                for process in alive:
                    process.poll()  # Reap an exited group leader before checking its children.
                    try:
                        os.killpg(process.pid, 0)
                        present = True
                    except ProcessLookupError:
                        pass
                if not present:
                    break
                time.sleep(0.05)
        for process in groups:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass

    def _save_metrics(self, run_id, metrics):
        (self.store.directory(run_id) / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
        self.store.update(run_id, metrics=metrics)

    def _run_logged(self, run_id, args, env, timeout, output):
        """Keep live output in console.log and a separate log for each selected unit."""
        log = self.store.directory(run_id) / "console.log"
        offset = log.stat().st_size if log.exists() else 0
        try:
            process = self._spawn(run_id, args, env)
            self._wait(run_id, process, timeout)
        finally:
            output.parent.mkdir(parents=True, exist_ok=True)
            if log.exists():
                with log.open("rb") as stream:
                    stream.seek(offset)
                    output.write_bytes(stream.read())
            else:
                output.write_text("")
        return output.read_text(errors="replace")

    def _loop(self):
        while not self.shutdown.is_set():
            with self.lock:
                run = self.store.claim()
            if not run:
                self.wake.wait(0.5)
                self.wake.clear()
                continue
            run_id = run["id"]
            status, error, metrics = "succeeded", None, {}
            try:
                metrics = self._execute(run)
            except Cancelled:
                status = "cancelled"
                metrics = self.store.get(run_id)["metrics"]
            except Exception as exc:
                status, error = "failed", str(exc)
                metrics = self.store.get(run_id)["metrics"]
                with (self.store.directory(run_id) / "console.log").open("a") as log:
                    log.write(f"\n[控制台] {type(exc).__name__}: {exc}\n")
            finally:
                self._cleanup(run_id)
            if run_id in self.cancelled:
                status = "cancelled"
            self.store.finish(run_id, status, metrics, error)

    def _execute(self, run):
        from XPolicyLab.evaluation.backends import get_backend
        from XPolicyLab.evaluation.snapshot import verify
        from XPolicyLab.evaluation.runtime import ExecutionContext
        snapshot = self.store.load_snapshot(run["id"])
        verify(snapshot)
        return get_backend(snapshot["benchmark"]).execute(ExecutionContext(self, run, snapshot))

    def close(self):
        self.shutdown.set()
        for run in self.store.active():
            if run["status"] in {"queued", "running", "cancelling"}:
                self.cancel(run["id"])
        self.wake.set()
        self.thread.join(timeout=15)
