"""Parent-workspace robot metadata shared by runtime and offline conversion."""
from pathlib import Path
from .load_file import load_json, load_yaml


def env_config_root(root=None):
    return Path(root).resolve() if root is not None else Path(__file__).resolve().parents[2] / "env_cfg"


def load_environment_config(env_cfg_type, *, root=None):
    return load_yaml(env_config_root(root) / f"{env_cfg_type}.yml")


def load_environment_metadata(env_cfg_type, *, root=None):
    base = env_config_root(root)
    config = load_environment_config(env_cfg_type, root=base)
    robot = config["config"]["robot"]
    dimensions = load_json(base / "robot/_robot_info.json")[robot]
    for key in ("arm_dim", "ee_dim"):
        if not dimensions[key] or any(not isinstance(value, int) or value <= 0 for value in dimensions[key]):
            raise ValueError(f"Invalid {key} for robot {robot}")
    if len(dimensions["arm_dim"]) != len(dimensions["ee_dim"]):
        raise ValueError("Robot arm and gripper dimensions disagree")
    return robot, dimensions, config.get("observation", {}).get("collect_freq", 50)
