# GR00T_N17

**原适配贡献者：** RoboDojo Team

接入 NVIDIA Isaac GR00T N1.7，基础模型为 `nvidia/GR00T-N1.7-3B`。
[上游代码](https://github.com/NVIDIA/Isaac-GR00T) vendored 在 `gr00t_n17/`，
适配用的模态配置在 `configs/`，辅助脚本在 `scripts/`。

本轮按用户选择保留此 adapter，仅整理文档与静态检查，未在本机验证安装、训练或模型评测。
公共参数与数据契约见[根 README](../../README.md)，能力状态见[交接页](../../docs/STATUS.md)。

<a id="installation"></a>

## 安装

先读 [INSTALLATION.md](INSTALLATION.md)，其中包含系统依赖、外部权重、手动回退和多环境说明。
本 adapter 使用 uv：

```bash
cd XPolicyLab/policy/GR00T_N17
bash install.sh
source gr00t_n17/.venv/bin/activate
```

<a id="data-processing"></a>

## 数据处理

```bash
export GR00T_LEROBOT_HOME=/path/to/lerobot/datasets
bash process_data.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> [expert_data_num]
bash process_data.sh RoboDojo stack_bowls arx_x5 joint
GR00T_SRC_DATASET=RoboDojo_sim_arx-x5_50ep bash process_data.sh RoboDojo stack_bowls_50ep arx_x5 joint
```

`arx_x5` 默认源数据为 `RoboDojo_sim_arx-x5_v30`，使用[官方 LeRobot 键](../../README.md#official-lerobot-conversion)。
脚本复制准备好的 v3.0 数据，再用上游 LeRobot 工具降为 v2.1，不更改键或图像。
其他机器人需显式设置 `GR00T_SRC_DATASET`。
`expert_data_num` 仅为接口兼容而记录，不会执行 episode 筛选；数据规模实验需先准备子集，再使用独立 `ckpt_name`。

<a id="training"></a>

## 训练

```bash
export GR00T_LEROBOT_HOME=/path/to/lerobot/datasets
```

```bash
bash train.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> <seed> <gpu_id>
bash train.sh RoboDojo cotrain arx_x5 joint 0 0
```

Checkpoint 默认位于 `checkpoints/<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>-<seed>/`。
评测的 `ckpt_name` 可传短运行名、完整运行目录名或 checkpoint 路径。
基础模型默认 `nvidia/GR00T-N1.7-3B` 与 `nvidia/Cosmos-Reason2-2B`，
可用 `GR00T_BASE_MODEL`、`GR00T_COSMOS_MODEL` 覆盖。
进程数由逗号分隔的 GPU 列表推导，也可设置 `NUM_GPUS`；`GLOBAL_BATCH_SIZE`、`MAX_STEPS` 可控制训练预算。
例如：

```bash
GLOBAL_BATCH_SIZE=640 MAX_STEPS=60000 bash train.sh RoboDojo cotrain arx_x5 joint 0 0,1,2,3,4,5,6,7
```

<a id="evaluation"></a>

## 评测

```bash
bash eval.sh <bench_name> <task_name> <ckpt_name> <env_cfg_type> <action_type> <seed> \
  <policy_gpu_id> <env_gpu_id> <policy_env> <eval_env_conda_env>
bash eval.sh RoboDojo stack_bowls RoboDojo-cotrain-arx_x5-joint-0 arx_x5 joint 0 0 0 <policy_env> <eval_env_conda_env>
```

`EVAL_ENV_TYPE=debug` 检查离线接线，仍需模型依赖和权重；不设置或设为 `sim` 时走仿真。
分机运行见[部署流程](../../README.md#-deployment-flow)。

`policy_env` 可传 conda 环境名、`uv` 或 uv 项目路径。`model_dir` 也可指定相对本 adapter 的 checkpoint 目录。

<a id="configuration"></a>

## 配置

检查 `deploy.yml` 的 `embodiment_tag`、`checkpoint_num`、`model_dir`、`cosmos_model_path`、
`default_prompt`、`policy_uv_env_path`。`model_dir` 优先于普通 checkpoint 命名解析；
`cosmos_model_path` 可为 Hugging Face ID 或相对本 adapter 的本地目录。

| 环境变量 | 用途 |
| --- | --- |
| `GR00T_LEROBOT_HOME` | 必填，数据处理和训练的数据根目录 |
| `GR00T_SRC_DATASET` | 源数据集名；arx_x5 默认 `RoboDojo_sim_arx-x5_v30` |
| `GR00T_BASE_MODEL` / `GR00T_COSMOS_MODEL` | 训练使用的基础模型路径或 ID |
| `NUM_GPUS` / `GLOBAL_BATCH_SIZE` / `MAX_STEPS` | 训练进程数、批量和步数 |
| `GR00T_ROOT` / `GR00T_VIDEO_BACKEND` | 可选项目根目录与视频后端覆盖 |

数据规模实验用 `GR00T_SRC_DATASET` 选择子集，并在 `ckpt_name` 标明，如 `stack_bowls_50ep`。

## 启动与进程管理

eval.sh 保留十个位置参数，使用共享生命周期回收本次创建的服务与 client 进程组。
模型专有差异与 CPU 验证范围见[生命周期说明](../../docs/reference/adapter-lifecycle.md)。
