"""Small execution interface used by every benchmark backend."""
from .snapshot import FrozenCatalog


class ExecutionContext:
    def __init__(self, runner, run, snapshot):
        self.runner, self.run = runner, run
        self.catalog = FrozenCatalog(snapshot)
        self.directory = runner.store.directory(run["id"])

    def stage(self, value):
        self.runner.store.update(self.run["id"], expected=("running",), stage=value)

    def save_metrics(self, metrics):
        self.runner._save_metrics(self.run["id"], metrics)

    def spawn(self, *args, **kwargs):
        return self.runner._spawn(*args, **kwargs)

    def wait(self, *args, **kwargs):
        return self.runner._wait(*args, **kwargs)

    def check(self, *args, **kwargs):
        return self.runner._check(*args, **kwargs)

    def run_logged(self, *args, **kwargs):
        return self.runner._run_logged(*args, **kwargs)
