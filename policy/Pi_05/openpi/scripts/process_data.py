"""Convert robot HDF5 episodes to the current LeRobot format for OpenPI."""
from __future__ import annotations

import argparse
from pathlib import Path
import random
import sys

REPOSITORY = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY.parent))
sys.path.insert(0, str(REPOSITORY))

import numpy as np
from XPolicyLab.utils.load_file import load_hdf5
from XPolicyLab.utils.process_data import decode_image_bit
from XPolicyLab.utils.environment_config import load_environment_metadata
from XPolicyLab.utils.episode_input import ConversionInput

CAMERA_ALIASES = {"cam_head": "cam_high", "cam_left_wrist": "cam_left_wrist", "cam_right_wrist": "cam_right_wrist"}


def _make_action_from_state(state):
    state = np.asarray(state, dtype=np.float32)
    if state.ndim != 2 or len(state) == 0:
        raise ValueError("State must be a nonempty [T,D] array")
    return np.concatenate([state[1:], state[-1:]], axis=0).copy()


def load_data(ep_path):
    data = load_hdf5(ep_path)
    reader = ConversionInput(data_root=".", env_cfg_root=".", camera_candidates={}, instruction_reader=lambda _: [])
    state = reader._extract_qpos(data)
    images = {}
    for source, target in CAMERA_ALIASES.items():
        camera = data.get("vision", {}).get(source)
        if camera is not None:
            frames = np.asarray(decode_image_bit(camera.get("colors", camera.get("color"))))
            if frames.ndim == 3:
                frames = frames[None]
            if frames.ndim != 4 or frames.shape[-1] != 3 or len(frames) != len(state):
                raise ValueError(f"Camera/state mismatch: {source}")
            images[target] = frames.astype(np.uint8, copy=False)
    if not images:
        raise ValueError("Episode has no supported camera")
    instructions = reader._ensure_utf8_strings(data.get("instructions", data.get("instruction")))
    return dict(state=state, action=_make_action_from_state(state), images=images,
                instructions=[text for text in instructions if text])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bench_name", "ckpt_name", "env_cfg_type", "action_type"):
        parser.add_argument(name)
    parser.add_argument("expert_data_num", nargs="?")
    parser.add_argument("raw_task_dirs", nargs="?")
    parser.add_argument("--mode", choices=("image", "video"), default="image")
    parser.add_argument("--instruction", default="Do your job.")
    parser.add_argument("--input-root", type=Path, default=REPOSITORY.parent / "data")
    parser.add_argument("--env-cfg-root", type=Path, default=REPOSITORY.parent / "env_cfg")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    if args.action_type != "joint":
        parser.error("Pi_05 原始 HDF5 转换由下一帧关节 state 生成 action，action_type 必须为 joint")
    limit, tasks = None, args.raw_task_dirs
    if args.expert_data_num is not None:
        if args.expert_data_num.isdigit():
            limit = int(args.expert_data_num)
            if limit <= 0:
                parser.error("expert_data_num 必须为正整数")
        elif tasks is None:
            tasks = args.expert_data_num
        else:
            parser.error("raw_task_dirs 重复指定")
    files = []
    for task in (tasks or args.ckpt_name).split(","):
        directory = args.input_root / args.bench_name / task.strip() / args.env_cfg_type
        found = sorted((directory / "data").glob("episode_*.hdf5")) or sorted(directory.glob("*.hdf5"))
        files.extend(found)
    files = files[:limit]
    if not files:
        raise ValueError("未找到任何待转换 episode")
    robot, dimensions, fps = load_environment_metadata(args.env_cfg_type, root=args.env_cfg_root)
    # Read and validate the first episode before creating a dataset on disk.
    sample = load_data(files[0])
    expected_dim = sum(dimensions["arm_dim"]) + sum(dimensions["ee_dim"])
    if sample["state"].shape[1] != expected_dim:
        raise ValueError("State width disagrees with robot configuration")
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.utils.constants import HF_LEROBOT_HOME
    repo_id = f"{args.bench_name}-{args.ckpt_name}-{args.env_cfg_type}-{args.action_type}"
    output = (args.output_root or HF_LEROBOT_HOME) / repo_id
    if output.exists():
        raise FileExistsError(f"输出已存在，选择新的输出目录：{output}")
    features = {key: dict(dtype="float32", shape=(expected_dim,), names=[f"state_{i}" for i in range(expected_dim)])
                for key in ("observation.state", "action")}
    for camera, frames in sample["images"].items():
        height, width = frames.shape[1:3]
        features[f"observation.images.{camera}"] = dict(dtype=args.mode, shape=(3, height, width), names=["channels", "height", "width"])
    dataset = LeRobotDataset.create(repo_id=repo_id, root=output, robot_type=robot, fps=fps, features=features,
                                    use_videos=args.mode == "video", image_writer_threads=1)
    rng = random.Random(args.seed)
    frames_written = 0
    for path in files:
        episode = sample if path == files[0] else load_data(path)
        if episode["state"].shape[1] != expected_dim or set(episode["images"]) != set(sample["images"]):
            raise ValueError(f"Episode feature mismatch: {path}")
        instruction = rng.choice(episode["instructions"]) if episode["instructions"] else args.instruction
        for index in range(len(episode["state"])):
            frame = {"observation.state": episode["state"][index], "action": episode["action"][index], "task": instruction}
            frame.update({f"observation.images.{name}": images[index] for name, images in episode["images"].items()})
            dataset.add_frame(frame)
            frames_written += 1
        dataset.save_episode()
    dataset.finalize()
    print(f"转换完成：{len(files)} episodes / {frames_written} frames → {output}", flush=True)
    return output


if __name__ == "__main__":
    main()
