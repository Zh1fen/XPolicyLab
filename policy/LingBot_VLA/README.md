# LingBot_VLA

**原适配贡献者：** RoboDojo Team

接入 LingBot-VLA，源码 vendored 在 `lingbot_vla/`。
训练读取上游准备的 LeRobot 数据，推理依赖 Qwen2.5-VL-3B-Instruct 权重；原 adapter 的技术报告链接尚未补齐。

本轮按用户选择保留此 adapter，仅整理文档与静态检查，未在本机验证安装、训练或模型评测。
公共参数与数据契约见[根 README](../../README.md)，能力状态见[交接页](../../docs/STATUS.md)。

<a id="installation"></a>

## 安装

```bash
cd XPolicyLab/policy/LingBot_VLA
bash install.sh
conda activate <policy_env>
```

<a id="data-processing"></a>

## 数据处理

`process_data.sh` 只校验公共参数并打印训练期望的数据标签，不会自行转换 HDF5。
可选 `expert_data_num` 仅记录标签，真正的 episode 筛选在上游转换时完成。
训练前设置 `LEROBOT_DATASET_REPO_ID` 或 `LINGBOT_VLA_DATA_PATH` 指向准备好的数据：

```bash
bash process_data.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> [expert_data_num]
bash process_data.sh RoboDojo stack_bowls arx_x5 joint
bash process_data.sh RoboDojo stack_bowls_50ep arx_x5 joint 50
```

数据列使用[官方 LeRobot 键](../../README.md#official-lerobot-conversion)：`observation.state`、`action`、
`observation.images.cam_high` / `cam_left_wrist` / `cam_right_wrist`。
`base_dataset.py` 加载后才将相机映射为内部 `base_0_rgb` / `left_wrist_0_rgb` / `right_wrist_0_rgb`。
arx_x5 默认数据标签为 `RoboDojo_sim_arx-x5_v30`，但版本不能只看名字：
安装脚本锁定的上游 LeRobot 仍提供旧 `lerobot.common` API，导出必须与实际安装的读取器匹配，不可直接假定支持 v3.0。
还需 normalization JSON，默认 `assets/norm_stats/robotwin_50.json`；
RoboDojo 数据可参考 `lingbot_vla/configs/norm/robodojo_sim_arx_x5.yaml`，通过 `lingbot_vla/compute_norm_stat.sh` 生成。

<a id="training"></a>

## 训练

```bash
bash train.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> <seed> <gpu_id>
bash train.sh RoboDojo cotrain arx_x5 joint 0 0
```

Checkpoint 默认位于 `checkpoints/<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>-<seed>/`。
评测的 `ckpt_name` 可传短运行名、完整运行目录名或 checkpoint 路径。
默认配置为 `lingbot_vla/configs/vla/robotwin_load20000h.yaml`。
数据读取 `LINGBOT_VLA_DATA_PATH`，或 `LEROBOT_DATA_ROOT` / `LEROBOT_DATASET_REPO_ID` 拼接路径。
真实训练前检查模型、tokenizer、统计量与数据配置，变量见下表。

<a id="evaluation"></a>

## 评测

Checkpoint 需要保留以下布局，自动选择含 hf_ckpt 的最新数字 global_step：

```text
checkpoints/<ckpt_name>/
  lingbotvla_cli.yaml
  checkpoints/global_step_*/hf_ckpt/*.safetensors
```

必须设置 `QWEN25_PATH` 指向 Qwen2.5-VL-3B-Instruct，没有可直接使用的公共默认本地路径。

```bash
bash eval.sh <bench_name> <task_name> <ckpt_name> <env_cfg_type> <action_type> <seed> \
  <policy_gpu_id> <env_gpu_id> <policy_env> <eval_env_conda_env>
bash eval.sh RoboDojo stack_bowls RoboDojo-cotrain-arx_x5-joint-0 arx_x5 joint 0 0 0 <policy_env> <eval_env_conda_env>
```

`EVAL_ENV_TYPE=debug` 检查离线接线，仍需模型依赖和权重；不设置或设为 `sim` 时走仿真。
分机运行见[部署流程](../../README.md#-deployment-flow)。

<a id="configuration"></a>

## 配置

检查 `deploy.yml` 的 `env_cfg`、`checkpoint_num`、`result_dir`、`obs_transform_pipeline`。

| 环境变量 | 用途 / 默认 |
| --- | --- |
| `LINGBOT_VLA_CONDA_ENV` | 安装环境名，默认 lingbot_vla |
| `LINGBOT_VLA_CONFIG_PATH` | 相对 lingbot_vla 的训练 YAML，默认 configs/vla/robotwin_load20000h.yaml |
| `LINGBOT_VLA_DATA_PATH` | 完整训练数据路径 |
| `LINGBOT_VLA_MODEL_PATH` | 覆盖训练模型路径 |
| `LINGBOT_VLA_TOKENIZER_PATH` | 覆盖 tokenizer；已设置 QWEN25_PATH 时可回退到它 |
| `LINGBOT_VLA_NORM_STATS_FILE` | 覆盖 normalization JSON |
| `XPOLICYLAB_LEROBOT_DATA_ROOT` / `LEROBOT_DATA_ROOT` | 数据根，默认 benchmark 的 data 目录 |
| `LEROBOT_DATASET_REPO_ID` | 数据集名，arx_x5 默认 RoboDojo_sim_arx-x5_v30 |
| `QWEN25_PATH` | 评测用 Qwen2.5-VL-3B-Instruct 权重 |
| `FLASH_ATTN_WHEEL_URL` | 可选安装 wheel URL |
