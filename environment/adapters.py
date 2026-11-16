"""Explicit bridges to existing TASK_ENV, reset/step simulators, and hardware callbacks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any

from .contracts import Action, ExecutionFeedback, Observation, ResetResult, StepResult
from .contracts import validate_action, validate_observation


def _boolean(value, name):
    if hasattr(value, "item"):
        value = value.item()
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


class BaseEnvironment(ABC):
    def __init__(self) -> None:
        self._active = False
        self._stopped = True
        self._closed = False

    def reset(self, *, seed=None, options=None) -> ResetResult:
        if self._closed:
            raise RuntimeError("environment is closed")
        if not self._stopped:
            self.stop("reset")
        self._active = False
        self._stopped = False  # A partially failed reset still needs stop().
        result = self._reset(seed, options)
        if not isinstance(result, ResetResult):
            raise TypeError("reset callback must return ResetResult")
        validate_observation(result.observation)
        self._active = True
        return result

    def validate_action(self, action: Action) -> None:
        validate_action(action)

    def step(self, action: Action) -> StepResult:
        if self._closed or not self._active:
            raise RuntimeError("reset a live episode before step()")
        self.validate_action(action)
        # If execution or observation acquisition fails, do not allow another action without reset.
        self._active = False
        result = self._step(action)
        if not isinstance(result, StepResult) or not isinstance(result.feedback, ExecutionFeedback):
            raise TypeError("step callback must return StepResult with ExecutionFeedback")
        validate_observation(result.observation)
        self._active = not result.feedback.done
        return result

    def stop(self, reason: str) -> None:
        self._active = False
        if not self._stopped:
            self._stop(reason)
            self._stopped = True

    def close(self) -> None:
        if not self._closed:
            try:
                self.stop("close")
            finally:
                self._closed = True
                self._close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @abstractmethod
    def _reset(self, seed, options) -> ResetResult: ...

    @abstractmethod
    def _step(self, action) -> StepResult: ...

    def _stop(self, reason: str) -> None:
        pass

    def _close(self) -> None:
        pass


class TaskEnvAdapter(BaseEnvironment):
    """Wrap legacy get_obs/take_action/is_episode_end without changing benchmark code."""

    def __init__(self, task_env, *, feedback_fn: Callable, reset_fn=None, stop_fn=None, action_validator=None):
        super().__init__()
        self.env = task_env
        self.reset_fn = reset_fn
        self.feedback_fn = feedback_fn
        self.stop_fn = stop_fn
        self.action_validator = action_validator
        if not callable(feedback_fn):
            raise TypeError("feedback_fn is required to distinguish termination, truncation and success")

    def _reset(self, seed, options):
        if self.reset_fn is None:
            if seed is not None or options is not None:
                raise ValueError("Legacy reset needs reset_fn to apply seed/options; they cannot be silently ignored")
            self.env.reset()
        else:
            self.reset_fn(seed, options)
        if _boolean(self.env.is_episode_end(), "is_episode_end"):
            raise ValueError("TASK_ENV is already finished immediately after reset")
        return ResetResult(self.env.get_obs())

    def validate_action(self, action):
        super().validate_action(action)
        if self.action_validator is not None:
            self.action_validator(action)

    def _step(self, action):
        self.env.take_action(action)
        done = _boolean(self.env.is_episode_end(), "is_episode_end")
        feedback = self.feedback_fn(self.env)
        if not isinstance(feedback, ExecutionFeedback) or feedback.done != done:
            raise ValueError("TASK_ENV feedback.done must agree with is_episode_end()")
        return StepResult(self.env.get_obs(), feedback)

    def _stop(self, reason):
        if self.stop_fn is not None:
            self.stop_fn(reason)

    def _close(self):
        close = getattr(self.env, "close", None)
        if callable(close):
            close()


class StepEnvAdapter(BaseEnvironment):
    """Wrap a 4/5-tuple step API; mappings are mandatory because action semantics differ."""

    def __init__(self, env, *, observation_mapper: Callable, action_mapper: Callable,
                 reset_fn=None, success_fn=None, stop_fn=None, action_validator=None):
        super().__init__()
        self.env = env
        self.observation_mapper = observation_mapper
        self.action_mapper = action_mapper
        self.reset_fn = reset_fn
        self.success_fn = success_fn
        self.stop_fn = stop_fn
        self.action_validator = action_validator

    def _reset(self, seed, options):
        raw = (self.reset_fn(seed, options) if self.reset_fn is not None
               else self.env.reset(seed=seed, options=options))
        observation, info = raw if isinstance(raw, tuple) and len(raw) == 2 else (raw, {})
        if not isinstance(info, Mapping):
            raise TypeError("reset info must be a mapping")
        return ResetResult(self.observation_mapper(observation), dict(info))

    def validate_action(self, action):
        super().validate_action(action)
        if self.action_validator is not None:
            self.action_validator(action)

    def _step(self, action):
        raw = self.env.step(self.action_mapper(action))
        if not isinstance(raw, tuple) or len(raw) not in (4, 5):
            raise TypeError("step must return (obs,reward,done,info) or (obs,reward,terminated,truncated,info)")
        if len(raw) == 5:
            observation, reward, terminated, truncated, info = raw
        else:
            observation, reward, done, info = raw
            if not isinstance(info, Mapping):
                raise TypeError("step info must be a mapping")
            done = _boolean(done, "done")
            truncated = _boolean(info.get("TimeLimit.truncated", False), "TimeLimit.truncated")
            if truncated and not done:
                raise ValueError("legacy TimeLimit.truncated requires done=True")
            terminated = done and not truncated
        if not isinstance(info, Mapping):
            raise TypeError("step info must be a mapping")
        if self.success_fn is not None:
            success = self.success_fn(observation, info)
        else:
            # Neither reward nor done is proof of task success.
            success = info.get("success", info.get("is_success"))
        if success is not None:
            # Accept numpy scalar booleans from simulators without importing numpy here.
            if hasattr(success, "item"):
                success = success.item()
            if not isinstance(success, bool):
                raise TypeError("success must be a boolean; provide success_fn for other encodings")
        if hasattr(reward, "item"):
            reward = reward.item()
        feedback = ExecutionFeedback(terminated=_boolean(terminated, "terminated"),
                                     truncated=_boolean(truncated, "truncated"), success=success,
                                     reward=reward, info=dict(info))
        return StepResult(self.observation_mapper(observation), feedback)

    def _stop(self, reason):
        if self.stop_fn is not None:
            self.stop_fn(reason)

    def _close(self):
        close = getattr(self.env, "close", None)
        if callable(close):
            close()


class CallbackEnvironment(BaseEnvironment):
    """Hardware-ready boundary. Concrete SDK calls, confirmation and limits belong to the caller."""

    def __init__(self, *, reset: Callable, observe: Callable[[], Observation],
                 execute: Callable[[Action], ExecutionFeedback], stop: Callable[[str], None],
                 close: Callable[[], None], action_validator: Callable[[Action], None]):
        super().__init__()
        self.reset_fn = reset
        self.observe_fn = observe
        self.execute_fn = execute
        self.stop_fn = stop
        self.close_fn = close
        self.action_validator = action_validator
        for callback in (reset, observe, execute, stop, close, action_validator):
            if not callable(callback):
                raise TypeError("all hardware callbacks, including stop and action_validator, are required")

    def _reset(self, seed, options):
        self.reset_fn(seed, options)
        return ResetResult(self.observe_fn())

    def validate_action(self, action):
        super().validate_action(action)
        self.action_validator(action)

    def _step(self, action):
        feedback = self.execute_fn(action)
        if not isinstance(feedback, ExecutionFeedback):
            raise TypeError("execute must return explicit ExecutionFeedback, not just a command acknowledgement")
        return StepResult(self.observe_fn(), feedback)

    def _stop(self, reason):
        self.stop_fn(reason)

    def _close(self):
        self.close_fn()
