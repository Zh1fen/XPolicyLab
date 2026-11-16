"""Single-environment contracts shared by simulator and hardware integrations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from numbers import Real
from typing import Any, Protocol

Observation = Mapping[str, Any]
Action = Mapping[str, Any]


def validate_observation(observation: Observation) -> None:
    if not isinstance(observation, Mapping):
        raise TypeError("observation must be a mapping")
    for name in ("vision", "state"):
        if not isinstance(observation.get(name), Mapping):
            raise TypeError(f"observation.{name} must be a mapping")
    if not isinstance(observation.get("instruction", observation.get("instructions")), str):
        raise TypeError("observation.instruction must be a string")


def validate_action(action: Action) -> None:
    """Check structure/finiteness only; units, robot dimensions and limits need an explicit validator."""
    if not isinstance(action, Mapping) or not action:
        raise TypeError("one action must be a nonempty mapping of field names to numeric vectors")
    for name, value in action.items():
        if not isinstance(name, str) or not name:
            raise TypeError("action field names must be nonempty strings")
        vector = value.tolist() if hasattr(value, "tolist") else value
        if not isinstance(vector, (list, tuple)) or not vector:
            raise TypeError(f"action.{name} must be a nonempty 1D vector")
        if any(isinstance(x, bool) or not isinstance(x, Real) or not math.isfinite(x) for x in vector):
            raise ValueError(f"action.{name} must contain finite real numbers")


def validate_robot_action(action: Action, env_cfg_type: str, action_type: str) -> None:
    """Use the shared robot metadata/packing rules; never infer dimensions from a model name."""
    from XPolicyLab.utils.process_data import get_robot_action_dim_info, pack_robot_state, unpack_robot_state

    validate_action(action)
    dimensions = get_robot_action_dim_info(env_cfg_type)
    vector = pack_robot_state({"state": action}, action_type, dimensions, source_type="obs")
    expected = unpack_robot_state(vector, action_type, dimensions, source_type="obs")
    if set(action) != set(expected):
        raise ValueError(f"action keys differ from the robot schema: expected {sorted(expected)}")


@dataclass(frozen=True)
class ExecutionFeedback:
    terminated: bool = False
    truncated: bool = False
    success: bool | None = None
    reward: float | None = None
    reason: str | None = None
    env_step: int | None = None
    info: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.terminated, bool) or not isinstance(self.truncated, bool):
            raise TypeError("terminated and truncated must be bool")
        if self.success is not None and not isinstance(self.success, bool):
            raise TypeError("success must be bool or None (unknown)")
        if self.reward is not None and (isinstance(self.reward, bool) or not isinstance(self.reward, Real)
                                        or not math.isfinite(self.reward)):
            raise ValueError("reward must be a finite number or None")
        if not isinstance(self.info, Mapping):
            raise TypeError("feedback.info must be a mapping")
        if self.env_step is not None and (isinstance(self.env_step, bool) or
                                         not isinstance(self.env_step, int) or self.env_step < 1):
            raise ValueError("env_step must be a positive integer or None")

    @property
    def done(self) -> bool:
        return self.terminated or self.truncated

    def to_dict(self) -> dict[str, Any]:
        return dict(terminated=self.terminated, truncated=self.truncated, success=self.success,
                    reward=self.reward, reason=self.reason, env_step=self.env_step, info=dict(self.info))


@dataclass(frozen=True)
class ResetResult:
    observation: Observation
    info: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepResult:
    observation: Observation
    feedback: ExecutionFeedback


class Environment(Protocol):
    def reset(self, *, seed: int | None = None, options: Mapping[str, Any] | None = None) -> ResetResult: ...
    def validate_action(self, action: Action) -> None: ...
    def step(self, action: Action) -> StepResult: ...
    def stop(self, reason: str) -> None: ...
    def close(self) -> None: ...
