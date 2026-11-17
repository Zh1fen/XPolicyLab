import argparse
import dataclasses
import fnmatch
import random
import shutil
import sys
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lerobot.utils.constants import HF_LEROBOT_HOME
from lerobot.datasets.lerobot_dataset import LeRobotDataset

from XPolicyLab.utils.data_loader import load
from XPolicyLab.utils.load_file import load_json, load_yaml
from XPolicyLab.utils.process_data import decode_image_bit


DEFAULT_DATASET_NAME = "RoboDojo"

DATA_ROOT = PROJECT_ROOT / "data"
ENV_CFG_ROOT = PROJECT_ROOT / "env_cfg"
ROBOT_INFO_PATH = ENV_CFG_ROOT / "robot" / "_robot_info.json"

DEFAULT_IMAGE_WIDTH = 640
DEFAULT_IMAGE_HEIGHT = 480
# Common source resolutions: 480x640 (RoboDojo) and 240x320 (RoboTwin).
SUPPORTED_IMAGE_SIZES = ((480, 640), (240, 320))


CAMERA_CANDIDATES = {
    "cam_high": [
        ("vision", "cam_head", "colors"),
    ],
    "cam_left_wrist": [
        ("vision", "cam_left_wrist", "colors"),
    ],
    "cam_right_wrist": [
        ("vision", "cam_right_wrist", "colors"),
    ],
}


# ============================================================
# Published v3.0 config: AV1 (libsvtav1), streaming, CRF 18
# ============================================================

@dataclasses.dataclass(frozen=True)
class DatasetConfig:
    use_videos: bool = True

    tolerance_s: float = 0.0001

    # IMPORTANT:
    # 0 = disable multiprocessing
    image_writer_processes: int = 8

    # Usually 2 is enough
    image_writer_threads: int = 2

    # Use streaming encoding so CRF can be overridden from this script
    # instead of relying on LeRobot's internal default of 30.
    streaming_encoding: bool = True

    # libsvtav1: CRF. h264_nvenc: LeRobot 0.4.4 maps this to constqp qp.
    video_crf: int | None = 18

    # Decoder. None keeps LeRobot's default decoder. It does not select the encoder.
    video_backend: str | None = None

    # Encoder.
    # libsvtav1: AV1, CRF 18, preset 12, g=2, yuv420p.
    # h264_nvenc: NVIDIA H.264, rc=constqp, qp=18, yuv420p. Not video_backend.
    vcodec: Literal["libsvtav1", "h264_nvenc"] = "libsvtav1"


DEFAULT_DATASET_CONFIG = DatasetConfig()


# ============================================================
# Metadata
# ============================================================


from XPolicyLab.utils.episode_input import ConversionInput

def _input_reader():
    return ConversionInput(data_root=DATA_ROOT, env_cfg_root=ENV_CFG_ROOT,
                           camera_candidates=CAMERA_CANDIDATES, instruction_reader=_find_instructions,
                           default_image_width=DEFAULT_IMAGE_WIDTH, default_image_height=DEFAULT_IMAGE_HEIGHT)

def _load_env_metadata(*args, **kwargs):
    return _input_reader()._load_env_metadata(*args, **kwargs)


def _split_pattern(*args, **kwargs):
    return _input_reader()._split_pattern(*args, **kwargs)


def _match_name(*args, **kwargs):
    return _input_reader()._match_name(*args, **kwargs)


def _discover_conversion_targets(*args, **kwargs):
    return _input_reader()._discover_conversion_targets(*args, **kwargs)


def _dims_from_robot_action_info(*args, **kwargs):
    return _input_reader()._dims_from_robot_action_info(*args, **kwargs)


def _plan_target_metadata(*args, **kwargs):
    return _input_reader()._plan_target_metadata(*args, **kwargs)


# ============================================================
# Motors
# ============================================================

def _build_motor_names_from_dims(*args, **kwargs):
    return _input_reader()._build_motor_names_from_dims(*args, **kwargs)


# ============================================================
# Utils
# ============================================================

def _resolve_input_dir(*args, **kwargs):
    return _input_reader()._resolve_input_dir(*args, **kwargs)


def _get_nested(*args, **kwargs):
    return _input_reader()._get_nested(*args, **kwargs)


def _ensure_2d_float32(*args, **kwargs):
    return _input_reader()._ensure_2d_float32(*args, **kwargs)


def _ensure_utf8_strings(*args, **kwargs):
    return _input_reader()._ensure_utf8_strings(*args, **kwargs)


def _find_instructions(data):
    candidates = [
        _get_nested(data, "instruction"),
        _get_nested(data, "instructions"),
    ]

    for candidate in candidates:

        strings = [
            s for s in _ensure_utf8_strings(candidate)
            if s
        ]

        if strings:
            return strings

    return []


def _choose_instruction(*args, **kwargs):
    return _input_reader()._choose_instruction(*args, **kwargs)


# ============================================================
# State / Action
# ============================================================

def _concat_state_parts(*args, **kwargs):
    return _input_reader()._concat_state_parts(*args, **kwargs)


def _extract_qpos(*args, **kwargs):
    return _input_reader()._extract_qpos(*args, **kwargs)


def _extract_action(*args, **kwargs):
    return _input_reader()._extract_action(*args, **kwargs)


def _pad_state_to_target_dims(array, current_dims, target_dims, name):
    arr = _ensure_2d_float32(array, name)

    expected_dim = sum(current_dims)

    if arr.shape[1] != expected_dim:
        raise ValueError(
            f"{name} dim mismatch: "
            f"expected {expected_dim}, got {arr.shape[1]}"
        )

    padded_parts = []

    start = 0

    for arm_index, target_dim in enumerate(target_dims):

        current_dim = (
            current_dims[arm_index]
            if arm_index < len(current_dims)
            else 0
        )

        end = start + current_dim

        part = (
            arr[:, start:end]
            if current_dim
            else np.zeros((arr.shape[0], 0), dtype=np.float32)
        )

        start = end

        if target_dim > current_dim:

            padding = np.zeros(
                (arr.shape[0], target_dim - current_dim),
                dtype=np.float32,
            )

            part = np.concatenate([part, padding], axis=1)

        padded_parts.append(part)

    return np.concatenate(padded_parts, axis=1)


# ============================================================
# Images
# ============================================================

def _resize_image(*args, **kwargs):
    return _input_reader()._resize_image(*args, **kwargs)


def _decode_images_if_needed(*args, **kwargs):
    return _input_reader()._decode_images_if_needed(*args, **kwargs)


def _find_camera_array(*args, **kwargs):
    return _input_reader()._find_camera_array(*args, **kwargs)


def _probe_raw_image_hw(*args, **kwargs):
    return _input_reader()._probe_raw_image_hw(*args, **kwargs)


def _parse_resolution(*args, **kwargs):
    return _input_reader()._parse_resolution(*args, **kwargs)


def _resolve_image_hw(*args, **kwargs):
    return _input_reader()._resolve_image_hw(*args, **kwargs)


# ============================================================
# Dataset
# ============================================================

def create_empty_dataset(
    repo_id: str,
    robot_type: str,
    motors: list[str],
    fps: int,
    mode: Literal["video", "image"] = "video",
    *,
    image_height: int = DEFAULT_IMAGE_HEIGHT,
    image_width: int = DEFAULT_IMAGE_WIDTH,
    dataset_config: DatasetConfig = DEFAULT_DATASET_CONFIG,
) -> Any:

    features = {
        "observation.state": {
            "dtype": "float32",
            "shape": (len(motors),),
            "names": [motors],
        },
        "action": {
            "dtype": "float32",
            "shape": (len(motors),),
            "names": [motors],
        },
    }

    for cam in CAMERA_CANDIDATES.keys():

        features[f"observation.images.{cam}"] = {
            "dtype": mode,
            "shape": (
                3,
                image_height,
                image_width,
            ),
            "names": [
                "channels",
                "height",
                "width",
            ],
        }

    dataset_root = Path(HF_LEROBOT_HOME) / repo_id

    if dataset_root.exists():
        shutil.rmtree(dataset_root)

    return LeRobotDataset.create(
        repo_id=repo_id,
        root=Path(HF_LEROBOT_HOME) / repo_id,
        fps=fps,
        robot_type=robot_type,
        features=features,

        use_videos=dataset_config.use_videos,

        tolerance_s=dataset_config.tolerance_s,

        image_writer_processes=dataset_config.image_writer_processes,
        image_writer_threads=dataset_config.image_writer_threads,

        streaming_encoding=dataset_config.streaming_encoding,
        video_backend=dataset_config.video_backend,
        vcodec=dataset_config.vcodec,
    )


def configure_video_encoding(dataset: Any, dataset_config: DatasetConfig) -> None:
    if not dataset_config.use_videos:
        return

    streaming_encoder = getattr(dataset, "_streaming_encoder", None)

    if streaming_encoder is None:
        raise RuntimeError(
            "Video CRF override requires LeRobot streaming_encoding=True, "
            "but no streaming encoder was initialized."
        )

    streaming_encoder.crf = dataset_config.video_crf


def finalize_dataset(dataset: Any) -> None:
    if hasattr(dataset, "finalize"):
        dataset.finalize()
        return
    if hasattr(dataset, "stop_image_writer"):
        dataset.stop_image_writer()
    meta = getattr(dataset, "meta", None)
    if meta is not None and hasattr(meta, "_close_writer"):
        meta._close_writer()


# ============================================================
# Convert
# ============================================================

def convert_one(
    input_path,
    dataset,
    data_type,
    data_version,
    current_dims,
    target_dims,
    image_height,
    image_width,
):

    data = load(
        str(input_path),
        data_type=data_type,
        data_version=data_version,
    )

    state = _extract_qpos(data)
    action = _extract_action(data)

    if state.shape != action.shape:
        raise ValueError(
            f"state/action mismatch: "
            f"{state.shape} vs {action.shape}"
        )

    state = _pad_state_to_target_dims(
        state,
        current_dims,
        target_dims,
        "state",
    )

    action = _pad_state_to_target_dims(
        action,
        current_dims,
        target_dims,
        "action",
    )

    instruction = _choose_instruction(data)

    if not instruction:
        raise ValueError("No instruction found")

    images = {}

    for camera_name in CAMERA_CANDIDATES:

        image_array = _find_camera_array(
            data,
            camera_name,
            image_height,
            image_width,
        )

        if image_array is not None:
            images[camera_name] = image_array

    num_frames = state.shape[0]

    # Every episode carries the full declared camera feature set, matching the
    # v2.1 converter: a camera absent from the source is filled with black
    # frames, and a camera shorter than the state sequence is corrupt data.
    # Extra trailing frames are tolerated (only the first num_frames are used).
    for camera_name in CAMERA_CANDIDATES:

        image_array = images.get(camera_name)

        if image_array is None:
            images[camera_name] = np.zeros(
                (num_frames, image_height, image_width, 3),
                dtype=np.uint8,
            )
        elif len(image_array) < num_frames:
            raise ValueError(
                f"Camera '{camera_name}' has {len(image_array)} frames but the "
                f"state sequence has {num_frames}"
            )

    for index in range(num_frames):

        frame = {
            "observation.state": state[index],
            "action": action[index],
            "task": instruction,
        }

        for image_name, image_array in images.items():
            frame[f"observation.images.{image_name}"] = image_array[index]

        dataset.add_frame(frame)

    dataset.save_episode()


# ============================================================
# Input files
# ============================================================

def find_input_files(*args, **kwargs):
    return _input_reader().find_input_files(*args, **kwargs)


def _collect_target_input_files(*args, **kwargs):
    return _input_reader()._collect_target_input_files(*args, **kwargs)


def _print_matched_targets(*args, **kwargs):
    return _input_reader()._print_matched_targets(*args, **kwargs)


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Transform RoboDojo dataset to LeRobot v3.0 format."
    )

    parser.add_argument(
        "patterns",
        nargs="+",
        help='Match expressions like "RoboDojo.*.arx_x5"',
    )

    parser.add_argument(
        "--repo_id",
        type=str,
        default=None,
    )

    parser.add_argument(
        "--data_type",
        type=str,
        default=DEFAULT_DATASET_NAME,
    )

    parser.add_argument(
        "--data_version",
        type=str,
        default="v1.0",
    )

    parser.add_argument(
        "--max_episode",
        type=int,
        default=200,
    )
    parser.add_argument(
        "--resolution",
        type=str,
        default=None,
        help="Target image size as HxW, e.g. 240x320 or 480x640. "
        "Default: auto-detect from the first source frame.",
    )
    parser.add_argument(
        "--image_height",
        type=int,
        default=None,
        help="Override target image height (use with --image_width).",
    )
    parser.add_argument(
        "--image_width",
        type=int,
        default=None,
        help="Override target image width (use with --image_height).",
    )

    args = parser.parse_args()

    targets = _discover_conversion_targets(args.patterns)

    if not targets:
        raise FileNotFoundError(
            f"No matching targets found: {args.patterns}"
        )

    metadata_by_target, target_dims, max_fps = (
        _plan_target_metadata(targets)
    )

    target_inputs = _collect_target_input_files(targets)

    _print_matched_targets(target_inputs)

    image_height, image_width = _resolve_image_hw(args, target_inputs)
    print(f"Image size: {image_height}x{image_width}")

    repo_id = (
        args.repo_id
        or f"unified_{'_'.join(pattern.replace('*', 'all').replace('.', '_') for pattern in args.patterns)}".lower()
    )

    motors = _build_motor_names_from_dims(target_dims)

    dataset = create_empty_dataset(
        repo_id=repo_id,
        robot_type="unified_robot",
        motors=motors,
        fps=max_fps or 50,

        # IMPORTANT
        mode="video",
        image_height=image_height,
        image_width=image_width,

        dataset_config=DEFAULT_DATASET_CONFIG,
    )

    configure_video_encoding(dataset, DEFAULT_DATASET_CONFIG)

    failures = []
    total_success = 0
    total_files = 0
    try:

        for (
            bench_name,
            task_name,
            env_cfg_type,
            input_dir,
            input_files,
        ) in target_inputs:

            task_success = 0

            if not input_files:

                failures.append(
                    (
                        str(input_dir),
                        "No .hdf5 or .h5 files found",
                    )
                )

                continue

            current_dims = metadata_by_target[
                (
                    bench_name,
                    task_name,
                    env_cfg_type,
                )
            ]["per_arm_dims"]

            for input_path in tqdm(
                input_files,
                desc=f"Converting {bench_name}/{task_name}/{env_cfg_type}",
            ):

                total_files += 1

                if task_success >= args.max_episode:

                    print(
                        "Reached "
                        f"max_episode={args.max_episode} "
                        f"for {bench_name}/{task_name}/{env_cfg_type}"
                    )

                    break

                try:

                    convert_one(
                        input_path,
                        dataset,
                        args.data_type,
                        args.data_version,
                        current_dims,
                        target_dims,
                        image_height,
                        image_width,
                    )

                    task_success += 1
                    total_success += 1

                except Exception as exc:

                    print(exc)

                    failures.append(
                        (
                            str(input_path),
                            str(exc),
                        )
                    )

    finally:

        finalize_dataset(dataset)

    print(f"Unified target dims per arm: {target_dims}")

    print(
        f"Converted {total_success}/{total_files} "
        f"files to {Path(HF_LEROBOT_HOME) / repo_id}"
    )

    if failures:

        print("Failed files:")

        for file_path, reason in failures:
            print(f"  - {file_path}: {reason}")


if __name__ == "__main__":
    main()
