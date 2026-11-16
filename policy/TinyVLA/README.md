# TinyVLA

**原适配贡献者：** RoboDojo Team

接入 TinyVLA 视觉语言动作模型。[论文](https://arxiv.org/abs/2409.12514)，
[上游代码](https://github.com/liyaxuanliyaxuan/TinyVLA) vendored 在 `tinyvla/`。

本轮按用户选择保留此 adapter，仅整理文档与静态检查，未在本机验证安装、训练或模型评测。
公共参数与数据契约见[根 README](../../README.md)，能力状态见[交接页](../../docs/STATUS.md)。

<a id="installation"></a>

## 安装

`install.sh` 将 adapter 与 XPolicyLab 以 editable 方式装入当前环境；运行前确认使用的环境。

```bash
cd XPolicyLab/policy/TinyVLA
bash install.sh
conda activate <policy_env>
```

<a id="data-processing"></a>

## 数据处理

将 RoboDojo HDF5 示范转换到 `data/<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>/`。
`raw_task_dirs` 可为源任务名或逗号分隔列表；不设置时转换源根目录下所有任务。
非数值的第五个参数按 `raw_task_dirs` 解释。源目录默认 `<repo>/data/<bench_name>`，可用 `XPL_SOURCE_ROOT` 覆盖。
`TINYVLA_PROCESS_WORKERS` 默认 8，`TINYVLA_HDF5_COMPRESSION` 默认 lzf；输出目录已存在时会交互询问是否复用。

```bash
bash process_data.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> [expert_data_num] [raw_task_dirs]
bash process_data.sh RoboDojo cotrain arx_x5 joint
bash process_data.sh RoboDojo stack_bowls_50ep arx_x5 joint 50 stack_bowls
```

<a id="training"></a>

## 训练

```bash
bash train.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> <seed> <gpu_id>
bash train.sh RoboDojo cotrain arx_x5 joint 0 0
```

Checkpoint 默认位于 `checkpoints/<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>-<seed>/`。
评测的 `ckpt_name` 可传短运行名、完整运行目录名或 checkpoint 路径。
脚本将 `train.sh`、`deploy.yml` 快照写入运行目录。
若 `<run_dir>/pretrained_vlm/` 缺权重，会交互提示下载 Llava-Pythia backbone；
原说明中 TinyVLA-S / B / H 分别约 400M / 700M / 1.3B。多卡可传 `0,1,2,3`。

<a id="evaluation"></a>

## 评测

```bash
bash eval.sh <bench_name> <task_name> <ckpt_name> <env_cfg_type> <action_type> <seed> \
  <policy_gpu_id> <env_gpu_id> <policy_env> <eval_env_conda_env>
bash eval.sh RoboDojo stack_bowls RoboDojo-cotrain-arx_x5-joint-0 arx_x5 joint 0 0 0 <policy_env> <eval_env_conda_env>
```

`EVAL_ENV_TYPE=debug` 检查离线接线，仍需模型依赖和权重；不设置或设为 `sim` 时走仿真。
分机运行见[部署流程](../../README.md#-deployment-flow)。

<a id="configuration"></a>

## 配置

检查 `deploy.yml` 的 `model_path`、`model_base`、`stats_path`、`enable_lora`、`conv_mode`、`camera_keys`。
训练与评测必须使用配套权重、相机配置与统计量。
