# Pi_05

**原适配贡献者：** RoboDojo Team
**论文：** π0.5 技术报告；论文链接尚未在此 adapter 补齐
**上游代码：** https://github.com/Physical-Intelligence/openpi

本 adapter 通过 uv 管理的 OpenPI 接入 XPolicyLab / RoboDojo。
适配脚本在本目录，上游源码在 `openpi/`。当前主线是接续已有 LIBERO 工作，
原有训练代码修改与历史资产均保留；本轮未重训或验证真实仿真效果。

公共参数和数据契约见[根 README](../../README.md)，当前能力见[状态页](../../docs/STATUS.md)。

<a id="installation"></a>

## 安装

```bash
cd XPolicyLab/policy/Pi_05
bash install.sh
source openpi/.venv/bin/activate
```

OpenPI 使用 uv；标准 `eval.sh` 的第 9 个参数传 `uv`（读取 `deploy.yml` 的 `policy_uv_env_path`），
或显式 OpenPI 项目路径，而不是策略端 conda 环境名。

<a id="data-processing"></a>

## 数据处理

RoboDojo 转换使用官方键：`observation.state`、`action`、
`observation.images.cam_high` / `cam_left_wrist` / `cam_right_wrist`，
见[官方 LeRobot 转换](../../README.md#official-lerobot-conversion)。
附带转换脚本在 OpenPI 锁定的 LeRobot 环境中运行，导出版本以实际环境和数据 metadata 为准。
当前本机 LeRobot 为 0.4.4，现有 LIBERO 导出为 v3.0。

可选 `expert_data_num` 只限制转换 episode 数，不参与 checkpoint 命名。
`raw_task_dirs` 是父工作区 `data/<bench_name>/` 下的源任务名或逗号分隔列表，默认等于 `ckpt_name`；
也可直接作为第 5 个参数传入，为同一份原始数据生成不同名字的导出。

```bash
bash process_data.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> [expert_data_num] [raw_task_dirs]
bash process_data.sh RoboDojo stack_bowls arx_x5 joint
bash process_data.sh RoboDojo stack_bowls_50ep arx_x5 joint 50 stack_bowls
```

转换入口默认使用 openpi/.venv/bin/python，可通过 OPENPI_DATA_PYTHON 覆盖。
--input-root、--env-cfg-root、--output-root 和 --seed 可覆盖原始数据、机器人配置、输出与指令随机种子。
默认输出仍是该环境的 HF_LEROBOT_HOME；已有 LIBERO 数据位于外部 datasets，转换不会迁移或覆盖它们。
此 HDF5 配方只接受 joint：action 为下一帧关节 state，末帧保持自身，使用父配置采样频率。
相机映射为 cam_high / cam_left_wrist / cam_right_wrist；当前输出为已安装 LeRobot 0.4.4 的 v3 格式。
输出目录存在、找不到 episode、字段异常或写出失败均返回非零，不覆盖现有数据。


<a id="training"></a>

## 训练

```bash
bash train.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> <seed> <gpu_id> [OpenPI训练参数...]
bash train.sh RoboDojo cotrain arx_x5 joint 0 0
```

Checkpoint 写入 `checkpoints/<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>-<seed>/`。
默认保护已有目录；接续同名运行显式添加 `--resume`，确实要清空替换时才添加 `--overwrite`。
额外尾参转发给 OpenPI。数据 repo 默认是 `<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>`。
单卡默认 `fsdp_devices=1`，多卡默认 `2`，可通过环境变量覆盖。

### LIBERO 本地配方

`pi05_libero` 对两个 expert 使用 LoRA，并联合读取四个本地数据集。
输入键为 `observation.images.image`、`observation.images.wrist_image`、`observation.state`、
`action` 和 `task`，与三相机 RoboDojo 配方不同。

数据、归一化、训练和运行命令统一维护在 [Pi_05 / LIBERO 手册](../../docs/reproduction/pi05-libero.md)。
`serve_libero.sh` / `eval_libero.sh` 使用 **OpenPI 原生 websocket 协议**，不经过 XPolicyLab `model.py`；
需要现有外部 LIBERO client。两个脚本都有 `--help`，checkpoint 和 client 位置必须显式配置。
该原生配方不能直接当作标准 adapter 的 LIBERO 支持。

<a id="evaluation"></a>

## 标准评测

```bash
bash eval.sh <bench_name> <task_name> <ckpt_name> <env_cfg_type> <action_type> <seed> \
  <policy_gpu_id> <env_gpu_id> <policy_uv_env> <eval_env_conda_env>
bash eval.sh RoboDojo stack_bowls RoboDojo-cotrain-arx_x5-joint-0 arx_x5 joint 0 0 0 uv <eval_env_conda_env>
```

`ckpt_name` 可用短运行名、完整运行目录名或 checkpoint 路径。
`EVAL_ENV_TYPE=debug` 做离线接线检查；不设置或设为 `sim` 时走仿真。
分机运行见[部署流程](../../README.md#-deployment-flow)。标准路径仍需父工作区 `env_cfg/`。

<a id="configuration"></a>

## 配置

检查 `deploy.yml` 的 `checkpoint_num`、`result_dir`、`obs_transform_pipeline`、
`policy_uv_env_path`、`train_config_name`、`repo_id`。训练和评测必须使用相符的配置与 normalization stats。

| 环境变量 | 用途 / 默认 |
| --- | --- |
| `OPENPI_LEROBOT_REPO_ID` | 训练数据 repo，默认由 bench/ckpt/robot/action 拼接 |
| `OPENPI_FSDP_DEVICES` | 覆盖 FSDP 设备数 |
| `OPENPI_TRAIN_CONFIG_NAME` | 训练配置，默认 `pi05_base_aloha_full_sim_arx-x5_seed_0` |
| `OPENPI_DATA_MODE` | 转换模式，默认 `image` |
| `OPENPI_LOCAL_CACHE_ROOT` | HF/JAX 本机缓存根，默认 `/tmp/openpi-cache-$(hostname)` |
| `PI05_BASE_PARAMS` | 本地 LIBERO 配方的初始权重；训练前显式设置以保证可移植 |

`OPENPI_ROOT`、`OPENPI_SRC` 由相关本地脚本消费；原生 LIBERO wrapper 的变量与默认值见[手册](../../docs/reproduction/pi05-libero.md)。

## 启动与进程管理

eval.sh 保留十个位置参数，使用共享生命周期回收本次创建的服务与 client 进程组。
模型专有差异与 CPU 验证范围见[生命周期说明](../../docs/reference/adapter-lifecycle.md)。
