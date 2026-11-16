"""Deterministic CPU fixture exercising the same environment boundary as hardware callbacks."""

from .adapters import CallbackEnvironment
from .contracts import ExecutionFeedback, validate_action


class MockEnvironment(CallbackEnvironment):
    def __init__(self, *, finish_after: int = 3, success: bool | None = True):
        if isinstance(finish_after, bool) or not isinstance(finish_after, int) or finish_after <= 0:
            raise ValueError("finish_after must be positive")
        self.finish_after = finish_after
        self.success = success
        self.steps = 0
        self.actions = []
        self.stop_reasons = []
        self.closed = False
        self.seed = None
        super().__init__(reset=self._mock_reset, observe=self._mock_observe, execute=self._mock_execute,
                         stop=self.stop_reasons.append, close=self._mock_close, action_validator=validate_action)

    def _mock_reset(self, seed, options):
        self.steps = 0
        self.actions = []
        self.seed = seed

    def _mock_observe(self):
        return {"vision": {}, "state": {"mock_step": self.steps}, "instruction": "CPU interface check"}

    def _mock_execute(self, action):
        self.actions.append(action)
        self.steps += 1
        done = self.steps >= self.finish_after
        return ExecutionFeedback(terminated=done, success=self.success if done else None)

    def _mock_close(self):
        self.closed = True


def create_mock_environment(config):
    """Factory for scripts/run_environment.py; config.run contains launch metadata."""
    return MockEnvironment(finish_after=config.get("finish_after", 3), success=config.get("success", True))
