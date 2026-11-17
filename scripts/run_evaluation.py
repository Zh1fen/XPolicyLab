#!/usr/bin/env python3
"""从 JSON 请求运行评测，复用控制台的后端、执行快照与串行队列。"""
import argparse
import fcntl
import json
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT.parent), str(ROOT)]
from XPolicyLab.evaluation.catalog import Catalog
from XPolicyLab.evaluation.runner import Manager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "artifacts/evaluation")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    with (args.data_dir / "server.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, "该数据目录已有评测控制进程\n")
        runner = Manager(Catalog(json.loads(args.config.read_text()) if args.config else {}), args.data_dir)
        try:
            run = runner.create(json.loads(args.request.read_text()))
            while True:
                run = runner.store.get(run["id"])
                if run["status"] not in ("queued", "running", "cancelling"):
                    break
                time.sleep(0.1)
            print(json.dumps(run, ensure_ascii=False))
            return 0 if run["status"] == "succeeded" else 1
        except KeyboardInterrupt:
            return 130
        finally:
            runner.close()


if __name__ == "__main__":
    raise SystemExit(main())
