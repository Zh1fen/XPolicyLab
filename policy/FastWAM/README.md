# FastWAM

**原适配贡献者：** RoboDojo Team

接入 Fast-WAM world-action 模型。
[论文](https://arxiv.org/abs/2603.16666)，[上游代码](https://github.com/yuantianyuan01/FastWAM) vendored 在 `FastWAM/`。

本轮按用户选择保留此 adapter，仅整理文档与静态检查，未在本机验证安装、训练或模型评测。
公共参数与数据契约见[根 README](../../README.md)，能力状态见[交接页](../../docs/STATUS.md)。

<a id="installation"></a>

## 安装

先读 [INSTALLATION.md](INSTALLATION.md)，其中包含外部权重、系统依赖与手动安装说明。

```bash
cd XPolicyLab/policy/FastWAM
bash install.sh
conda activate <policy_env>
```

<a id="data-processing"></a>

## 数据处理

本 adapter 没有顶层 `process_data.sh`，直接读取准备好的 LeRobot **v2.1** 数据。
相机键从 metadata 发现，预期与[官方 v2.1 转换](../../README.md#official-lerobot-conversion)输出一致。
后续数据统计和文本 embedding 缓存使用 `FastWAM/` 内的上游工具生成。

<a id="training"></a>

## 训练

```bash
bash train.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> <seed> <gpu_id> [num_gpus]
bash train.sh RoboDojo cotrain arx_x5 joint 0 0,1,2,3
```

Checkpoint 默认位于 `checkpoints/<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>-<seed>/`。
评测的 `ckpt_name` 可传短运行名、完整运行目录名或 checkpoint 路径。
训练前需准备：

- LeRobot v2.1 数据：`data/<dataset_id>/lerobot/`。
- 统计量：`data/<dataset_id>/dataset_stats.json`。
- T5 embedding 缓存：`FastWAM/data/text_embeds_cache/xpolicylab/<dataset_id>/`。
- ActionDiT backbone：`FastWAM/checkpoints/ActionDiT_linear_interp_Wan22_alphascale_1024hdim.pt`。

`dataset_id` 默认 `<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>`，可用 `FASTWAM_DATASET_ID` 覆盖。
缓存或 backbone 缺失时，脚本会打印相应上游生成命令。
训练进程数默认由 GPU 列表推导，第 7 个参数 `num_gpus` 可覆盖。
`FASTWAM_BATCH_SIZE` 默认 8，需按显存调整；脚本自动将 `DIFFSYNTH_MODEL_BASE_PATH` 设为 `FastWAM/checkpoints`。

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

检查 `deploy.yml` 的 `action_dim`、`checkpoint_path`、`dataset_stats_path`、`sim_cfg_name`、`sim_task`、
`device`、`mixed_precision`、`action_horizon`、`replan_steps`、`num_inference_steps`、`sigma_shift`。

可覆盖的环境变量：`FASTWAM_DATASET_ID`、`FASTWAM_BATCH_SIZE`、`FASTWAM_GRADIENT_ACCUMULATION_STEPS`、
`FASTWAM_NUM_WORKERS`、`FASTWAM_NUM_EPOCHS`、`FASTWAM_CKPT_SETTING`、`FASTWAM_CKPT_ROOT`、
`FASTWAM_CHECKPOINT_PATH`、`FASTWAM_DATASET_STATS_PATH`、`FASTWAM_ALLOW_DUMMY_POLICY`。

<a id="notes"></a>

## 注意事项

训练和评测保持相同 `action_type`。参考路径直接使用 XPolicyLab 的 `pack_robot_state` / `unpack_robot_state`，
不额外加入 adapter 私有的 `ee` 位姿转换。

## 启动与进程管理

eval.sh 保留十个位置参数，使用共享生命周期回收本次创建的服务与 client 进程组。
模型专有差异与 CPU 验证范围见[生命周期说明](../../docs/reference/adapter-lifecycle.md)。
