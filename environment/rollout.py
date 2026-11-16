"""Bounded single-environment execution, without planning, memory, or automatic recovery."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
import json
import logging
from pathlib import Path
import time
from typing import Any

from .contracts import Environment, ExecutionFeedback, validate_observation
from .policy import PolicyAdapter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EpisodeResult:
    steps: int
    policy_calls: int
    terminated: bool
    truncated: bool
    success: bool | None
    reward: float | None
    reason: str
    duration_s: float
    error: str | None = None
    error_phase: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class EpisodeError(RuntimeError):
    def __init__(self, result: EpisodeResult):
        self.result = result
        super().__init__(result.error)


class JsonlRecorder:
    """Append compact feedback/timing events. No images, weights, or observations are persisted."""

    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a", encoding="utf-8")

    def __call__(self, event: Mapping[str, Any]) -> None:
        self.file.write(json.dumps(dict(event), ensure_ascii=False, allow_nan=False) + "\n")
        self.file.flush()

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def run_episode(env: Environment, policy: PolicyAdapter, *, max_steps: int,
                execute_horizon: int | None = None, seed: int | None = None, options=None,
                should_stop: Callable[[], bool] | None = None, on_event: Callable | None = None) -> EpisodeResult:
    """Run one episode; stop on every exit and propagate errors with a structured partial result.

    The caller owns env/client close(). max_steps counts environment actions, not inference calls.
    An SDK exception may occur after motion: do not retry execution or infer that it did not happen.
    """
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps <= 0:
        raise ValueError("max_steps must be a positive integer")
    if execute_horizon is not None and (isinstance(execute_horizon, bool) or
                                       not isinstance(execute_horizon, int) or execute_horizon <= 0):
        raise ValueError("execute_horizon must be a positive integer or None")
    start = time.perf_counter()
    steps = calls = 0
    reward = None
    feedback = ExecutionFeedback()
    reason = "step_limit"
    error = None
    error_phase = None
    phase = "reset"

    def emit(kind, **payload):
        if on_event is not None:
            on_event(dict(schema_version=1, event=kind, elapsed_s=time.perf_counter() - start, **payload))

    try:
        policy.reset()
        initial = env.reset(seed=seed, options=options)
        observation = initial.observation
        validate_observation(observation)
        emit("reset", seed=seed, info=dict(initial.info))
        while steps < max_steps:
            if should_stop is not None and should_stop():
                reason = "cancelled"
                break
            phase = "predict"
            infer_start = time.perf_counter()
            chunk = policy.predict(observation)
            calls += 1
            if not isinstance(chunk, (list, tuple)) or not chunk:
                raise TypeError("policy must return a nonempty list/tuple of action dictionaries; map native outputs explicitly")
            phase = "validate_action"
            # Reject a bad later action before executing even the first action in this chunk.
            for action in chunk:
                env.validate_action(action)
            infer_s = time.perf_counter() - infer_start
            count = min(len(chunk), execute_horizon or len(chunk), max_steps - steps)
            for action_offset, action in enumerate(chunk[:count]):
                if should_stop is not None and should_stop():
                    reason = "cancelled"
                    break
                phase = "execute"
                step_start = time.perf_counter()
                result = env.step(action)
                steps += 1
                observation, feedback = result.observation, replace(result.feedback, env_step=steps)
                if feedback.reward is not None:
                    reward = (reward or 0.0) + feedback.reward
                step_s = time.perf_counter() - step_start
                phase = "feedback"
                policy.feedback(feedback)
                phase = "record"
                emit("step", step=steps, policy_call=calls, feedback=feedback.to_dict(),
                     inference_s=infer_s if action_offset == 0 else 0.0, execution_s=step_s)
                if feedback.done:
                    reason = "terminated" if feedback.terminated else "truncated"
                    break
            if feedback.done or reason == "cancelled":
                break
    except BaseException as exc:
        error, error_phase = exc, phase
        reason = "cancelled" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "error"
    finally:
        try:
            env.stop(reason)
        except BaseException as exc:
            if error is None:
                error, error_phase, reason = exc, "stop", "error"
            else:
                logger.exception("stop also failed; preserving original episode error")

    def summary():
        return EpisodeResult(steps, calls, feedback.terminated,
                             feedback.truncated or reason in {"step_limit", "cancelled"},
                             feedback.success, reward, reason, time.perf_counter() - start,
                             None if error is None else f"{type(error).__name__}: {error}", error_phase)

    try:
        policy.finish(summary())
    except BaseException as exc:
        if error is None:
            error, error_phase, reason = exc, "finish", "error"
        else:
            logger.exception("trial feedback also failed; preserving original episode error")
    try:
        emit("episode_end", result=summary().to_dict())
    except BaseException as exc:
        if error is None:
            error, error_phase, reason = exc, "record", "error"
        else:
            logger.exception("recording episode end also failed; preserving original episode error")
    final = summary()
    if error is not None:
        if not isinstance(error, Exception):
            raise error
        raise EpisodeError(final) from error
    return final
