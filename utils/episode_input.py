"""LeRobot-independent episode extraction; writer APIs stay in versioned entrypoints."""
SUPPORTED_IMAGE_SIZES = ((480, 640), (240, 320))
import fnmatch
import random
from pathlib import Path
import cv2
import numpy as np
from XPolicyLab.utils.data_loader import load
from XPolicyLab.utils.load_file import load_yaml, load_json
from XPolicyLab.utils.process_data import decode_image_bit
from XPolicyLab.utils.environment_config import load_environment_metadata


class ConversionInput:
    def __init__(self, *, data_root, env_cfg_root, camera_candidates, instruction_reader, default_image_width=640, default_image_height=480):
        self.data_root = Path(data_root)
        self.env_cfg_root = Path(env_cfg_root)
        self.robot_info_path = self.env_cfg_root / "robot/_robot_info.json"
        self.camera_candidates = camera_candidates
        self._find_instructions = instruction_reader
        self.default_image_width, self.default_image_height = default_image_width, default_image_height

    def _load_env_metadata(self, env_cfg_type):
        return load_environment_metadata(env_cfg_type, root=self.env_cfg_root)

    def _split_pattern(self, pattern):
        parts = pattern.split('.')
        if len(parts) != 3:
            raise ValueError(f'Pattern should be <dataset>.<task>.<env_cfg>, got: {pattern}')
        return (parts[0], parts[1], parts[2])

    def _match_name(self, name, pattern):
        return pattern == '*' or fnmatch.fnmatchcase(name, pattern)

    def _discover_conversion_targets(self, patterns):
        targets = []
        seen = set()
        for pattern in patterns:
            dataset_pattern, task_pattern, env_pattern = self._split_pattern(pattern)
            if not self.data_root.exists():
                break
            for dataset_dir in sorted((path for path in self.data_root.iterdir() if path.is_dir())):
                if not self._match_name(dataset_dir.name, dataset_pattern):
                    continue
                for task_dir in sorted((path for path in dataset_dir.iterdir() if path.is_dir())):
                    if not self._match_name(task_dir.name, task_pattern):
                        continue
                    for env_dir in sorted((path for path in task_dir.iterdir() if path.is_dir())):
                        if not self._match_name(env_dir.name, env_pattern):
                            continue
                        input_dir = env_dir / 'data'
                        if not input_dir.is_dir():
                            continue
                        target = (dataset_dir.name, task_dir.name, env_dir.name)
                        if target not in seen:
                            seen.add(target)
                            targets.append(target)
        return targets

    def _dims_from_robot_action_info(self, robot_action_dim_info):
        arm_dims = robot_action_dim_info.get('arm_dim', [])
        ee_dims = robot_action_dim_info.get('ee_dim', [])
        per_arm_dims = []
        for index, arm_dim in enumerate(arm_dims):
            ee_dim = ee_dims[index] if index < len(ee_dims) else 0
            per_arm_dims.append(arm_dim + ee_dim)
        return per_arm_dims

    def _plan_target_metadata(self, targets):
        max_per_arm_dims = []
        metadata = {}
        max_fps = 0
        for bench_name, task_name, env_cfg_type in targets:
            robot_name, robot_action_dim_info, fps = self._load_env_metadata(env_cfg_type)
            per_arm_dims = self._dims_from_robot_action_info(robot_action_dim_info)
            if len(max_per_arm_dims) < len(per_arm_dims):
                max_per_arm_dims.extend([0] * (len(per_arm_dims) - len(max_per_arm_dims)))
            for index, dim in enumerate(per_arm_dims):
                max_per_arm_dims[index] = max(max_per_arm_dims[index], dim)
            max_fps = max(max_fps, fps)
            metadata[bench_name, task_name, env_cfg_type] = {'robot_name': robot_name, 'robot_action_dim_info': robot_action_dim_info, 'fps': fps, 'per_arm_dims': per_arm_dims}
        return (metadata, max_per_arm_dims, max_fps)

    def _build_motor_names_from_dims(self, per_arm_dims):
        if not per_arm_dims:
            raise ValueError('per_arm_dims is empty')
        if len(per_arm_dims) == 1:
            prefixes = ['arm']
        elif len(per_arm_dims) == 2:
            prefixes = ['left', 'right']
        else:
            prefixes = [f'arm_{index}' for index in range(len(per_arm_dims))]
        motors = []
        for index, total_dim in enumerate(per_arm_dims):
            prefix = prefixes[index]
            for joint_idx in range(total_dim):
                motors.append(f'{prefix}_joint_{joint_idx}')
        return motors

    def _resolve_input_dir(self, bench_name, task_name, env_cfg_type, input_dir=None):
        if input_dir is not None:
            return Path(input_dir)
        return self.data_root / bench_name / task_name / env_cfg_type / 'data'

    def _get_nested(self, data, *keys, default=None):
        cur = data
        for key in keys:
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
        return cur

    def _ensure_2d_float32(self, array, name):
        arr = np.asarray(array, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr[:, None]
        if arr.ndim != 2:
            raise ValueError(f'{name} should be 2D, got shape {arr.shape}')
        return arr

    def _ensure_utf8_strings(self, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, bytes):
            return [value.decode('utf-8')]
        if isinstance(value, np.ndarray):
            if value.ndim == 0:
                return self._ensure_utf8_strings(value.item())
            return [str(x.decode('utf-8') if isinstance(x, (bytes, np.bytes_)) else x) for x in value.tolist()]
        if isinstance(value, (list, tuple)):
            result = []
            for item in value:
                result.extend(self._ensure_utf8_strings(item))
            return result
        return [str(value)]

    def _choose_instruction(self, data):
        instructions = self._find_instructions(data)
        if not instructions:
            return ''
        return random.choice(instructions)

    def _find_camera_array(self, data, camera_name, image_height, image_width):
        for keys in self.camera_candidates[camera_name]:
            value = self._get_nested(data, *keys)
            if value is not None:
                return self._decode_images_if_needed(value, image_height, image_width)
        return None

    def _resize_image(self, image, image_height, image_width):
        if image.shape[:2] == (image_height, image_width):
            return image
        return cv2.resize(image, (image_width, image_height), interpolation=cv2.INTER_LINEAR)

    def _decode_images_if_needed(self, images, image_height, image_width):
        frames = np.asarray(decode_image_bit(images))
        if frames.ndim == 3:
            frames = frames[None, ...]
        if frames.ndim != 4:
            raise ValueError(f'Expected decoded frames with shape [T,H,W,3], got {frames.shape}')
        if frames.dtype != np.uint8:
            frames = frames.astype(np.uint8)
        if frames.shape[1:3] != (image_height, image_width):
            frames = np.stack([self._resize_image(frame, image_height, image_width) for frame in frames], axis=0)
        return frames

    def _probe_raw_image_hw(self, target_inputs, data_type, data_version):
        """Return (H, W) from the first readable camera frame, without resizing."""
        for _, _, _, _, input_files in target_inputs:
            for input_path in input_files:
                data = load(str(input_path), data_type=data_type, data_version=data_version)
                for camera_name in self.camera_candidates:
                    for keys in self.camera_candidates[camera_name]:
                        value = self._get_nested(data, *keys)
                        if value is None:
                            continue
                        frames = np.asarray(decode_image_bit(value))
                        if frames.ndim == 3:
                            return (int(frames.shape[0]), int(frames.shape[1]))
                        if frames.ndim == 4 and frames.shape[0] > 0:
                            return (int(frames.shape[1]), int(frames.shape[2]))
        return (self.default_image_height, self.default_image_width)

    def _parse_resolution(self, text: str) -> tuple[int, int]:
        """Parse '240x320' / '240,320' into (height, width)."""
        normalized = text.lower().replace(',', 'x').replace('*', 'x')
        parts = [p.strip() for p in normalized.split('x') if p.strip()]
        if len(parts) != 2:
            raise argparse.ArgumentTypeError(f'resolution must look like HxW (e.g. 240x320), got: {text}')
        height, width = (int(parts[0]), int(parts[1]))
        if height <= 0 or width <= 0:
            raise argparse.ArgumentTypeError(f'invalid resolution: {text}')
        return (height, width)

    def _resolve_image_hw(self, args, target_inputs) -> tuple[int, int]:
        if args.resolution is not None:
            image_hw = self._parse_resolution(args.resolution)
        elif args.image_height is not None or args.image_width is not None:
            if args.image_height is None or args.image_width is None:
                raise ValueError('Pass both --image_height and --image_width, or use --resolution')
            image_hw = (args.image_height, args.image_width)
        else:
            image_hw = self._probe_raw_image_hw(target_inputs, args.data_type, args.data_version)
        if image_hw not in SUPPORTED_IMAGE_SIZES:
            supported = ', '.join((f'{h}x{w}' for h, w in SUPPORTED_IMAGE_SIZES))
            print(f'[warn] Using image size {image_hw[0]}x{image_hw[1]}; commonly tested sizes are: {supported}')
        return image_hw

    def _concat_state_parts(self, parts, name):
        valid_parts = []
        horizon = None
        for part_name, value in parts:
            if value is None:
                continue
            arr = self._ensure_2d_float32(value, f'{name}.{part_name}')
            if horizon is None:
                horizon = arr.shape[0]
            elif arr.shape[0] != horizon:
                raise ValueError(f'{name}.{part_name} horizon mismatch: expected {horizon}, got {arr.shape[0]}')
            valid_parts.append(arr)
        if not valid_parts:
            return None
        return np.concatenate(valid_parts, axis=1)

    def _extract_qpos(self, data):
        state_qpos = self._concat_state_parts([('left_arm_joint_states', self._get_nested(data, 'state', 'left_arm_joint_states')), ('left_ee_joint_states', self._get_nested(data, 'state', 'left_ee_joint_states')), ('right_arm_joint_states', self._get_nested(data, 'state', 'right_arm_joint_states')), ('right_ee_joint_states', self._get_nested(data, 'state', 'right_ee_joint_states'))], 'state')
        if state_qpos is not None:
            return state_qpos
        raise ValueError('Cannot find qpos data')

    def _extract_action(self, data):
        action = self._concat_state_parts([('left_arm_joint_states', self._get_nested(data, 'action', 'left_arm_joint_states')), ('left_ee_joint_states', self._get_nested(data, 'action', 'left_ee_joint_states')), ('right_arm_joint_states', self._get_nested(data, 'action', 'right_arm_joint_states')), ('right_ee_joint_states', self._get_nested(data, 'action', 'right_ee_joint_states'))], 'action')
        if action is not None:
            return action
        raise ValueError('Cannot find action data')

    def find_input_files(self, input_dir):
        input_dir = Path(input_dir)
        files = sorted(input_dir.rglob('*.hdf5'))
        files.extend(sorted(input_dir.rglob('*.h5')))
        unique_files = []
        seen = set()
        for file_path in files:
            resolved = str(file_path.resolve())
            if resolved not in seen:
                seen.add(resolved)
                unique_files.append(file_path)
        return unique_files

    def _collect_target_input_files(self, targets):
        collected = []
        for bench_name, task_name, env_cfg_type in targets:
            input_dir = self._resolve_input_dir(bench_name, task_name, env_cfg_type)
            input_files = self.find_input_files(input_dir)
            collected.append((bench_name, task_name, env_cfg_type, input_dir, input_files))
        return collected

    def _print_matched_targets(self, target_inputs):
        print('Matched targets:')
        for bench_name, task_name, env_cfg_type, input_dir, input_files in target_inputs:
            print(f'  - {bench_name}/{task_name}/{env_cfg_type}: {len(input_files)} files from {input_dir}')
