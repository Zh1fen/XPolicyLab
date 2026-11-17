# LingBot_VA

**原适配贡献者：** RoboDojo Team

接入 LingBot-VA，源码 vendored 在 `lingbot_va/`。
训练读取预先计算的 Wan2.2 VAE latent，而不是直接读取原始 LeRobot parquet / 视频。
原 adapter 的技术报告链接尚未补齐。

本轮按用户选择保留此 adapter，仅整理文档与静态检查，未在本机验证安装、训练或模型评测。
公共参数与数据契约见[根 README](../../README.md)，能力状态见[交接页](../../docs/STATUS.md)。

<a id="installation"></a>

## 安装

```bash
cd XPolicyLab/policy/LingBot_VA
bash install.sh
conda activate <policy_env>
```

<a id="data-processing"></a>

## 数据处理

输入为采用[官方键](../../README.md#official-lerobot-conversion)的 RoboDojo LeRobot **v2.1** 数据，包含 parquet 和逐相机 MP4。
脚本执行动作映射、分段标注、VAE 编码和空文本 embedding 生成：

- 动作映射为 30 维：左右臂 EEF（7+7）、左右臂关节（7+7）、左右夹爪（1+1），缺失维度补零。
- `meta/episodes.jsonl` 的每条 episode 写入 `action_config`；默认每 episode 一段，范围 `[0, length)`，`action_text` 为任务描述。
- Wan2.2 VAE 输出到 `latents/`，目录对应 `videos/`，相机来自 `obs_cam_keys`；RoboDojo 使用 cam_high / 左右腕。
- 视频约缩放为 256×256，按 `va_robotwin30_train_cfg` 采用 5–15 fps 范围内的采样配置；wrapper 的目标 fps 默认 10。
- 数据根生成 `empty_emb.pt`，用于 classifier-free guidance 丢弃语言条件时的空字符串 embedding。

VAE 与文本编码器来自基础模型，必须设置 `LINGBOT_VA_BASE_MODEL_PATH`。

```bash
export LEROBOT_DATA_ROOT=<parent_dir_of_lerobot_datasets>
export LEROBOT_DATASET_REPO_ID=<source_dataset_folder_name>
export LINGBOT_VA_BASE_MODEL_PATH=<path_to_lingbot-va-base>
bash process_data.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> [expert_data_num]
bash process_data.sh RoboDojo cotrain arx_x5 joint
```

输出默认 `data/<bench>-<ckpt>-<env>-<action>/`，可用 `LINGBOT_VA_DATASET_PATH` 覆盖。
latent 文件名为 `episode_{index}_{start_frame}_{end_frame}.pth`，例如 `episode_000000_0_450.pth`。
缺任一相机 latent 的片段会被训练器跳过。若手动调整为多子任务分段，必须同时重生成每个相机的匹配 latent。
详细 `.pth` schema 与上游步骤见 `lingbot_va/README.md` 的 Custom Dataset Preparation / Post-Training LingBot-VA。

<a id="training"></a>

## 训练

使用上游 FSDP post-training，需要数据中的 `latents/`、`empty_emb.pt`、`action_config`，以及 `.merged_ckpt` 基础模型链接：

```bash
export LINGBOT_VA_DATASET_PATH=<path_to_prepared_dataset>
export LINGBOT_VA_BASE_MODEL_PATH=<path_to_lingbot-va-base>
ln -sfn "${LINGBOT_VA_BASE_MODEL_PATH}" .merged_ckpt
```

```bash
bash train.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> <seed> <gpu_id>
bash train.sh RoboDojo cotrain arx_x5 joint 0 0,1,2,3,4,5,6,7
```

Checkpoint 默认位于 `checkpoints/<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>-<seed>/`。
评测的 `ckpt_name` 可传短运行名、完整运行目录名或 checkpoint 路径。
原说明使用多卡分片，单卡通常不足。
训练前检查基础模型 `transformer/config.json` 的 `attn_mode` 为 `flex`，推理/评测前按上游说明切换为 `torch` 或 `flashattn`。

<a id="evaluation"></a>

## 评测

```bash
bash eval.sh <bench_name> <task_name> <ckpt_name> <env_cfg_type> <action_type> <seed> \
  <policy_gpu_id> <env_gpu_id> <policy_env> <eval_env_conda_env>
bash eval.sh RoboDojo stack_bowls RoboDojo-cotrain-arx_x5-joint-0 arx_x5 joint 0 0 0 <policy_env> <eval_env_conda_env>
```

`EVAL_ENV_TYPE=debug` 检查离线接线，仍需模型依赖和权重；不设置或设为 `sim` 时走仿真。
分机运行见[部署流程](../../README.md#-deployment-flow)。

`eval_batch` 必须保持 `false`：`wan_va_server` 共用全局 KV/VAE/`frame_st_id` 缓存，一个进程只能服务一个环境。
`get_action_batch` 会抛出 `NotImplementedError`。
`eval.sh` 自动启动实际持有权重的 wan_va 后端，需要基础模型路径；也可指定已运行后端。

<a id="configuration"></a>

## 配置

检查 `deploy.yml` 的 `env_cfg`、`protocol`、`config_name`、`checkpoint_path`、`base_model_path`、
`rollout_mode`、`result_dir`、`va_server_host`、`va_server_port`、`obs_transform_pipeline`。

| 环境变量 | 用途 |
| --- | --- |
| `LEROBOT_DATA_ROOT` / `LEROBOT_DATASET_REPO_ID` | 数据根目录与源数据集名 |
| `LINGBOT_VA_SOURCE_DATASET` | 源数据完整路径，优先于上述源数据定位 |
| `LINGBOT_VA_DATASET_PATH` | 准备后的 latent 数据输出与训练读取路径 |
| `LINGBOT_VA_BASE_MODEL_PATH` | 必填，基础权重；deploy 的 base_model_path 为空时也用于评测 |
| `LINGBOT_VA_PROCESS_GPU` | latent 编码 GPU，默认 0 |
| `LINGBOT_VA_TARGET_FPS` | latent 采样 fps，默认 10 |
| `LINGBOT_VA_VA_HOST` / `LINGBOT_VA_VA_PORT` | 使用已运行的 wan_va 后端 |

`LINGBOT_VA_DATASET_PATH` 显式指定准备后的数据时，训练不再用根目录和 repo ID 拼接。
训练必须先完成 latent pipeline，不能只提供普通 LeRobot 数据。

<a id="notes"></a>

## 注意事项

训练必须完成 latent 准备；推理必须提供基础模型，并保持单环境。

## 启动与进程管理

eval.sh 保留十个位置参数，使用共享生命周期回收本次创建的服务与 client 进程组。
模型专有差异与 CPU 验证范围见[生命周期说明](../../docs/reference/adapter-lifecycle.md)。
