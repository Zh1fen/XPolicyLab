"""Resolve execution choices once, then verify immutable inputs before a worker starts."""

import copy
import hashlib
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace


def fingerprint(path, role):
    path = Path(path).resolve()
    return dict(path=str(path), role=role, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def validate_credential_references(value):
    if isinstance(value, dict):
        for key, item in value.items():
            sensitive = key.lower() in {"token", "password", "secret", "api_key"} or key.lower().endswith(("_token", "_password", "_secret", "_api_key"))
            reference = isinstance(item, dict) and set(item) == {"env"} and isinstance(item["env"], str)
            if sensitive and item and not reference:
                raise ValueError(f"{key} 必须使用环境变量引用 {{\"env\":\"变量名\"}}")
            validate_credential_references(item)
    elif isinstance(value, list):
        for item in value:
            validate_credential_references(item)


def resolve_environment(values):
    return {key: os.environ[value["env"]] if isinstance(value, dict) and set(value) == {"env"} else str(value)
            for key, value in values.items()}


def prepare(catalog, raw):
    parameters = catalog.validate(raw)
    backend = parameters["benchmark"]
    from .backends import get_backend
    configuration, dependencies = get_backend(backend).freeze(catalog, parameters)
    validate_credential_references(configuration)
    checkpoint = str(catalog.checkpoint_path(parameters).resolve()) if "checkpoint" in parameters else None
    revision = subprocess.run(["git", "-C", str(catalog.root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "unknown"
    if subprocess.run(["git", "-C", str(catalog.root), "status", "--porcelain"], capture_output=True, text=True).stdout.strip():
        revision += " (dirty)"
    return dict(version=1, benchmark=backend, workspace=str(catalog.root), revision=revision,
                parameters=parameters, checkpoint=checkpoint, configuration=configuration, dependencies=dependencies)


def verify(snapshot):
    if snapshot.get("version") != 1:
        raise ValueError("不支持的执行快照版本")
    for item in snapshot["dependencies"]:
        path = Path(item["path"])
        if not path.is_file() or fingerprint(path, item["role"])["sha256"] != item["sha256"]:
            raise ValueError(f"执行输入已变化：{item['role']} ({path})；请重新提交")
    if snapshot["checkpoint"] and not Path(snapshot["checkpoint"]).is_dir():
        raise ValueError("快照中的 checkpoint 已不存在")


class FrozenCatalog:
    """The narrow path/config API needed by backends; never consults the live catalog."""
    def __init__(self, snapshot):
        self.root = Path(snapshot["workspace"])
        self.config = copy.deepcopy(snapshot["configuration"])
        self.checkpoint = snapshot["checkpoint"]

    def path(self, value):
        path = Path(value).expanduser()
        return (path if path.is_absolute() else self.root / path).resolve()

    def checkpoint_path(self, _parameters):
        return Path(self.checkpoint)
