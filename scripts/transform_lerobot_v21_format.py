import argparse
import dataclasses
import fnmatch
import glob
import random
import sys
from pathlib import Path
from typing import Literal

import av
import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm
import shutil
from lerobot.datasets.lerobot_dataset import HF_LEROBOT_HOME, LeRobotDataset
from lerobot.datasets import lerobot_dataset as lerobot_dataset_mod
from lerobot.datasets.video_utils import encode_video_frames as encode_video_frames_orig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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

@dataclasses.dataclass(frozen=True)
class DatasetConfig:
    use_videos: bool = True
    tolerance_s: float = 0.0001
    # Conservative defaults reduce RAM pressure during long conversions.
    image_writer_processes: int = 0
    image_writer_threads: int = 4
    # Decoder. None keeps LeRobot's default decoder. It does not select the encoder.
    video_backend: str | None = None
    # Encoder. LeRobot 0.3.3 create() does not take vcodec; this script
    # replaces encode_video_frames in-process from this field.
    # libsvtav1: AV1, CRF 30, g=2, yuv420p.
    # h264_nvenc: NVIDIA H.264, rc=constqp, qp=18, yuv420p. Not video_backend.
    vcodec: Literal["libsvtav1", "h264_nvenc"] = "libsvtav1"


DEFAULT_DATASET_CONFIG = DatasetConfig()


def _encode_video_frames_nvenc(imgs_dir, video_path, fps, overwrite=False) -> None:
    # LeRobot 0.3.3 rejects any vcodec outside h264/hevc/libsvtav1, so NVENC is
    # encoded here. The inputs are the PNG frames LeRobot itself wrote, not
    # XPolicyLab trajectories, so they are read with PIL like LeRobot does.
    video_path = Path(video_path)
    imgs_dir = Path(imgs_dir)
    video_path.parent.mkdir(parents=True, exist_ok=overwrite)

    template = "frame_" + ("[0-9]" * 6) + ".png"
    input_list = sorted(
        glob.glob(str(imgs_dir / template)),
        key=lambda x: int(x.split("_")[-1].split(".")[0]),
    )
    if not input_list:
        raise FileNotFoundError(f"No images found in {imgs_dir}.")
    with Image.open(input_list[0]) as dummy_image:
        width, height = dummy_image.size

    # No GOP option: NVENC refuses to open with a keyframe interval below 4, so
    # the g=2 used for AV1 cannot be matched. LeRobot 0.4.4 likewise omits it for
    # hardware encoders (_get_codec_options in datasets/video_utils.py).
    options = {"rc": "constqp", "qp": "18"}
    with av.open(str(video_path), "w") as output:
        output_stream = output.add_stream("h264_nvenc", fps, options=options)
        output_stream.pix_fmt = "yuv420p"
        output_stream.width = width
        output_stream.height = height
        for input_data in input_list:
            with Image.open(input_data) as input_image:
                input_frame = av.VideoFrame.from_image(input_image.convert("RGB"))
            packet = output_stream.encode(input_frame)
            if packet:
                output.mux(packet)
        packet = output_stream.encode()
        if packet:
            output.mux(packet)

    if not video_path.exists():
        raise OSError(f"Video encoding did not work. File not found: {video_path}.")


def configure_video_encoding(dataset_config: DatasetConfig) -> None:
    if dataset_config.vcodec == "libsvtav1":

        def encode_video_frames(imgs_dir, video_path, fps, overwrite=False, **_kwargs):
            return encode_video_frames_orig(
                imgs_dir,
                video_path,
                fps,
                vcodec="libsvtav1",
                pix_fmt="yuv420p",
                g=2,
                crf=30,
                overwrite=overwrite,
            )

    elif dataset_config.vcodec == "h264_nvenc":

        def encode_video_frames(imgs_dir, video_path, fps, overwrite=False, **_kwargs):
            return _encode_video_frames_nvenc(
                imgs_dir, video_path, fps, overwrite=overwrite
            )

    else:
        raise ValueError(
            f"Unsupported vcodec {dataset_config.vcodec!r}; "
            "use 'libsvtav1' or 'h264_nvenc'"
        )

    # Fail loudly rather than write the wrong codec if a future LeRobot stops
    # calling encode_video_frames as a module global.
    current = getattr(lerobot_dataset_mod, "encode_video_frames", None)
    if current is not encode_video_frames_orig and not getattr(current, "_vcodec_patched", False):
        raise RuntimeError(
            "LeRobot no longer calls encode_video_frames as a module global; "
            "the vcodec selection would be a no-op"
        )

    encode_video_frames._vcodec_patched = True
    lerobot_dataset_mod.encode_video_frames = encode_video_frames



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


def _build_motor_names_from_dims(*args, **kwargs):
    return _input_reader()._build_motor_names_from_dims(*args, **kwargs)


def _pad_state_to_target_dims(array, current_dims, target_dims, name):
    arr = _ensure_2d_float32(array, name)
    expected_dim = sum(current_dims)
    if arr.shape[1] != expected_dim:
        raise ValueError(f"{name} dim mismatch: expected {expected_dim}, got {arr.shape[1]}")

    padded_parts = []
    start = 0
    for arm_index, target_dim in enumerate(target_dims):
        current_dim = current_dims[arm_index] if arm_index < len(current_dims) else 0
        end = start + current_dim
        part = arr[:, start:end] if current_dim else np.zeros((arr.shape[0], 0), dtype=np.float32)
        start = end
        if target_dim < current_dim:
            raise ValueError(
                f"{name} target dim for arm {arm_index} is smaller than current dim: {target_dim} < {current_dim}"
            )
        if target_dim > current_dim:
            padding = np.zeros((arr.shape[0], target_dim - current_dim), dtype=np.float32)
            part = np.concatenate([part, padding], axis=1)
        padded_parts.append(part)

    if start != arr.shape[1]:
        raise ValueError(f"{name} dim mismatch after padding: consumed {start}, actual {arr.shape[1]}")
    return np.concatenate(padded_parts, axis=1) if padded_parts else arr


def _resolve_input_dir(*args, **kwargs):
    return _input_reader()._resolve_input_dir(*args, **kwargs)


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
    
) -> LeRobotDataset:
    features = {
        "observation.state": {
            "dtype": "float32",
            "shape": (len(motors),),
            "names": [
                motors,
            ],
        },
        "action": {
            "dtype": "float32",
            "shape": (len(motors),),
            "names": [
                motors,
            ],
        },
    }


    for cam in CAMERA_CANDIDATES.keys():
        features[f"observation.images.{cam}"] = {
            "dtype": mode,
            "shape": (3, image_height, image_width),
            "names": [
                "channels",
                "height",
                "width",
            ],
        }

    if Path(HF_LEROBOT_HOME / repo_id).exists():
        shutil.rmtree(HF_LEROBOT_HOME / repo_id)

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
        video_backend=dataset_config.video_backend,
    )

def _get_nested(*args, **kwargs):
    return _input_reader()._get_nested(*args, **kwargs)


def _ensure_2d_float32(*args, **kwargs):
    return _input_reader()._ensure_2d_float32(*args, **kwargs)


def _ensure_utf8_strings(*args, **kwargs):
    return _input_reader()._ensure_utf8_strings(*args, **kwargs)


def _find_instructions(data):
    candidates = [
        _get_nested(data, "instructions"),
        _get_nested(data, "instruction"),
    ]
    for candidate in candidates:
        strings = [s for s in _ensure_utf8_strings(candidate) if s]
        if strings:
            return strings
    return []


def _choose_instruction(*args, **kwargs):
    return _input_reader()._choose_instruction(*args, **kwargs)


def _find_camera_array(*args, **kwargs):
    return _input_reader()._find_camera_array(*args, **kwargs)


def _resize_image(*args, **kwargs):
    return _input_reader()._resize_image(*args, **kwargs)


def _decode_images_if_needed(*args, **kwargs):
    return _input_reader()._decode_images_if_needed(*args, **kwargs)


def _empty_image_sequence(num_frames, image_height, image_width):
    return np.zeros((num_frames, image_height, image_width, 3), dtype=np.uint8)


def _probe_raw_image_hw(*args, **kwargs):
    return _input_reader()._probe_raw_image_hw(*args, **kwargs)


def _parse_resolution(*args, **kwargs):
    return _input_reader()._parse_resolution(*args, **kwargs)


def _resolve_image_hw(*args, **kwargs):
    return _input_reader()._resolve_image_hw(*args, **kwargs)


def _concat_state_parts(*args, **kwargs):
    return _input_reader()._concat_state_parts(*args, **kwargs)


def _extract_qpos(*args, **kwargs):
    return _input_reader()._extract_qpos(*args, **kwargs)


def _extract_action(*args, **kwargs):
    return _input_reader()._extract_action(*args, **kwargs)

def add_frame_compat(dataset: LeRobotDataset, frame: dict, task: str) -> None:
    try:
        dataset.add_frame(frame, task=task)
    except TypeError:
        frame = {**frame, "task": task}
        dataset.add_frame(frame)


def save_episode_compat(dataset: LeRobotDataset, task: str) -> None:
    try:
        dataset.save_episode(task=task)
    except TypeError:
        dataset.save_episode()


def release_dataset_memory(dataset: LeRobotDataset) -> None:
    # Some LeRobot variants keep appending every saved episode to `hf_dataset`,
    # which makes RAM usage grow linearly until the process gets OOM-killed.
    if hasattr(dataset, "create_hf_dataset") and hasattr(dataset, "hf_dataset"):
        try:
            dataset.hf_dataset = dataset.create_hf_dataset()
        except Exception:
            pass


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
    data = load(str(input_path), data_type=data_type, data_version=data_version)

    state = _extract_qpos(data)
    action = _extract_action(data)
    if state.shape != action.shape:
        raise ValueError(f"state/action shape mismatch: {state.shape} vs {action.shape}")
    state = _pad_state_to_target_dims(state, current_dims, target_dims, "state")
    action = _pad_state_to_target_dims(action, current_dims, target_dims, "action")
    instruction = _choose_instruction(data)
    if not instruction:
        raise ValueError("No instruction found in data")
    
    images = {}
    for camera_name in CAMERA_CANDIDATES:
        image_array = _find_camera_array(data, camera_name, image_height, image_width)
        if image_array is not None:
            images[camera_name] = image_array
    
    num_frames = state.shape[0]
    for camera_name in CAMERA_CANDIDATES:
        if camera_name not in images:
            images[camera_name] = _empty_image_sequence(num_frames, image_height, image_width)

    for i in range(num_frames):
        frame = {
            "observation.state": np.asarray(state[i]),
            "action": np.asarray(action[i]),
        }

        for image_name, image_array in images.items():
            frame[f"observation.images.{image_name}"] = image_array[i]

        add_frame_compat(dataset, frame, instruction)

    save_episode_compat(dataset, instruction)
    release_dataset_memory(dataset)
    



def find_input_files(*args, **kwargs):
    return _input_reader().find_input_files(*args, **kwargs)


def _collect_target_input_files(*args, **kwargs):
    return _input_reader()._collect_target_input_files(*args, **kwargs)


def _print_matched_targets(*args, **kwargs):
    return _input_reader()._print_matched_targets(*args, **kwargs)


def main():
    parser = argparse.ArgumentParser(description="Transform RoboDojo dataset to LeRobot v2.1 format.")
    parser.add_argument(
        "patterns",
        nargs="+",
        help='Match expressions like "RoboDojo.*.arx_x5" or "RoboDojo.*.*"',
    )
    parser.add_argument("--repo_id", type=str, default=None, help="LeRobot repo_id. Defaults to unified_<dataset> patterns summary")
    parser.add_argument("--data_type", type=str, default=DEFAULT_DATASET_NAME, help="Dataset type, e.g. RoboDojo")
    parser.add_argument("--data_version", type=str, default="v1.0", help="Dataset version, e.g. v1.0")
    parser.add_argument("--max_episode", type=int, default=200, help="Max episodes per task/env")
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
    configure_video_encoding(DEFAULT_DATASET_CONFIG)

    targets = _discover_conversion_targets(args.patterns)
    if not targets:
        raise FileNotFoundError(f"No matching dataset/task/env_cfg targets found for patterns: {args.patterns}")

    metadata_by_target, target_dims, max_fps = _plan_target_metadata(targets)
    target_inputs = _collect_target_input_files(targets)
    _print_matched_targets(target_inputs)
    image_height, image_width = _resolve_image_hw(args, target_inputs)
    print(f"Image size: {image_height}x{image_width}")
    repo_id = args.repo_id or f"unified_{'_'.join(pattern.replace('*', 'all').replace('.', '_') for pattern in args.patterns)}".lower()
    motors = _build_motor_names_from_dims(target_dims)
    
    dataset = create_empty_dataset(
                repo_id,
                robot_type="unified_robot",
                motors=motors,
                fps=max_fps or 50,
                mode="video",
                image_height=image_height,
                image_width=image_width,
                dataset_config=DEFAULT_DATASET_CONFIG,
        )

    failures = []
    total_files = 0
    total_success = 0
    for bench_name, task_name, env_cfg_type, input_dir, input_files in target_inputs:
        task_success = 0

        if not input_files:
            failures.append((str(input_dir), "No .hdf5 or .h5 files found"))
            continue

        current_dims = metadata_by_target[(bench_name, task_name, env_cfg_type)]["per_arm_dims"]
        for input_path in tqdm(input_files, desc=f"Converting {bench_name}/{task_name}/{env_cfg_type}"):
            total_files += 1

            if task_success >= args.max_episode:
                print(
                    f"Reached max_episode={args.max_episode} "
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
                failures.append((str(input_path), str(exc)))

    print(f"Unified target dims per arm: {target_dims}")
    print(f"Converted {total_success}/{total_files} files to {HF_LEROBOT_HOME / repo_id}")
    if failures:
        print("Failed files:")
        for file_path, reason in failures:
            print(f"  - {file_path}: {reason}")


if __name__ == "__main__":
    main()
