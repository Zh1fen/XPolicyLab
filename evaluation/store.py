"""Published run artifacts, FIFO claims and compare-and-set lifecycle transitions."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


ACTIVE = ("queued", "running", "cancelling")
TERMINAL = ("succeeded", "failed", "cancelled", "interrupted")
TRANSITIONS = {"queued": {"running", "cancelled", "interrupted"},
               "running": {"cancelling", "succeeded", "failed", "cancelled", "interrupted"},
               "cancelling": {"cancelled", "interrupted"}}


class Store:
    def __init__(self, data_dir):
        self.root = Path(data_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "history.sqlite3"
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("""CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT, status TEXT, stage TEXT,
              parameters TEXT, revision TEXT, metrics TEXT, error TEXT, finished_at TEXT)""")
            columns = {row[1] for row in con.execute("PRAGMA table_info(runs)")}
            for name, kind in (("sequence", "INTEGER"), ("snapshot_version", "INTEGER"), ("snapshot_sha256", "TEXT")):
                if name not in columns:
                    con.execute(f"ALTER TABLE runs ADD COLUMN {name} {kind}")
            con.execute("UPDATE runs SET sequence=rowid WHERE sequence IS NULL")
            con.execute("CREATE INDEX IF NOT EXISTS run_queue ON runs(status,created_at,sequence)")
            con.execute("UPDATE runs SET status='interrupted', stage='服务已重启', error='控制台上次异常退出；请检查残留进程', finished_at=?, updated_at=? WHERE status IN ('running','cancelling')", (now(), now()))
            con.execute("UPDATE runs SET status='interrupted', stage='需要重新提交', error='旧排队记录缺少执行快照；请按当前配置重新提交', finished_at=?, updated_at=? WHERE status='queued' AND snapshot_version IS NULL", (now(), now()))
        # Unpublished directories are evidence of an interrupted publish, never executable runs.
        self.recovery_report = self.unpublished_directories()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def decode(self, row):
        if row is None:
            return None
        item = dict(row)
        item["parameters"] = json.loads(item["parameters"])
        item["metrics"] = json.loads(item["metrics"] or "{}")
        return item

    @staticmethod
    def _write(path, value):
        data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _sync_directory(path):
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def create(self, parameters, revision, snapshot=None):
        run_id = uuid4().hex[:16]
        stamp = now()
        staging = self.root / ".staging" / run_id
        staging.mkdir(parents=True)
        try:
            self._write(staging / "parameters.json", parameters)
            digest = self._write(staging / "snapshot.json", snapshot) if snapshot is not None else None
            if snapshot is not None:
                self._write(staging / "backend_config.json", snapshot["configuration"])
            destination = self.directory(run_id)
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Files precede publication. A failed DB commit leaves an identifiable orphan, not a job.
            self._sync_directory(staging)
            os.replace(staging, destination)
            self._sync_directory(destination.parent)
            self._sync_directory(staging.parent)
            with self.connect() as con:
                con.execute("BEGIN IMMEDIATE")
                sequence = con.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM runs").fetchone()[0]
                con.execute("""INSERT INTO runs
                    (id,created_at,updated_at,status,stage,parameters,revision,metrics,error,finished_at,sequence,snapshot_version,snapshot_sha256)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (run_id, stamp, stamp, "queued", "等待执行", json.dumps(parameters), revision,
                    "{}", None, None, sequence, snapshot["version"] if snapshot else None, digest))
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        return self.get(run_id)

    def unpublished_directories(self):
        with self.connect() as con:
            known = {row[0] for row in con.execute("SELECT id FROM runs")}
        return {"staging": sorted(str(p) for p in (self.root / ".staging").glob("*") if p.is_dir()),
                "unpublished": sorted(str(p) for p in (self.root / "runs").glob("*") if p.is_dir() and p.name not in known)}

    def load_snapshot(self, run_id):
        run = self.get(run_id)
        if run is None or run["snapshot_version"] != 1:
            raise ValueError("运行缺少受支持的执行快照；请按当前配置重新提交")
        data = (self.directory(run_id) / "snapshot.json").read_bytes()
        if hashlib.sha256(data).hexdigest() != run["snapshot_sha256"]:
            raise ValueError("执行快照摘要不匹配")
        snapshot = json.loads(data)
        if snapshot.get("version") != 1 or snapshot["parameters"] != run["parameters"]:
            raise ValueError("执行快照版本或参数不匹配")
        return snapshot

    def get(self, run_id):
        with self.connect() as con:
            return self.decode(con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())

    def list(self, limit=500, offset=0):
        with self.connect() as con:
            return [self.decode(row) for row in con.execute("SELECT * FROM runs ORDER BY created_at DESC,sequence DESC LIMIT ? OFFSET ?", (limit, offset))]

    def active(self):
        with self.connect() as con:
            return [self.decode(row) for row in con.execute("SELECT * FROM runs WHERE status IN ('queued','running','cancelling') ORDER BY created_at,sequence")]

    def claim(self):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM runs WHERE status='queued' ORDER BY created_at,sequence LIMIT 1").fetchone()
            if row is None:
                return None
            con.execute("UPDATE runs SET status='running',stage='准备运行',updated_at=? WHERE id=? AND status='queued'", (now(), row["id"]))
            return self.decode(con.execute("SELECT * FROM runs WHERE id=?", (row["id"],)).fetchone())

    def update(self, run_id, expected=None, **values):
        if not values or not values.keys() <= {"status", "stage", "metrics", "error", "finished_at"}:
            raise ValueError("invalid update")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                return False
            old = row[0]
            if expected is not None and old not in expected:
                return False
            if "status" in values and values["status"] != old and values["status"] not in TRANSITIONS.get(old, set()):
                return False
            if "metrics" in values:
                values["metrics"] = json.dumps(values["metrics"], ensure_ascii=False, allow_nan=False)
            values["updated_at"] = now()
            con.execute("UPDATE runs SET " + ",".join(f"{key}=?" for key in values) + " WHERE id=? AND status=?", (*values.values(), run_id, old))
            return True

    def request_cancel(self, run_id):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            if row[0] in ACTIVE:
                queued = row[0] == "queued"
                con.execute("UPDATE runs SET status=?,stage=?,finished_at=?,updated_at=? WHERE id=? AND status=?",
                            ("cancelled" if queued else "cancelling", "已取消" if queued else "正在停止", now() if queued else None, now(), run_id, row[0]))
        return self.get(run_id)

    def finish(self, run_id, status, metrics, error=None):
        # The transaction decides whether completion or cancellation won the race.
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None or row[0] not in ("running", "cancelling"):
                return False
            if row[0] == "cancelling":
                status = "cancelled"
            con.execute("UPDATE runs SET status=?,stage=?,metrics=?,error=?,finished_at=?,updated_at=? WHERE id=? AND status=?",
                        (status, {"succeeded": "运行完成", "failed": "运行失败", "cancelled": "已停止"}[status], json.dumps(metrics, ensure_ascii=False), error, now(), now(), run_id, row[0]))
            return True

    def directory(self, run_id):
        if len(run_id) != 16 or any(c not in "0123456789abcdef" for c in run_id):
            raise ValueError("invalid run id")
        return self.root / "runs" / run_id
