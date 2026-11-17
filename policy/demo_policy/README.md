# demo_policy

**原适配贡献者：** RoboDojo Team；本目录是 XPolicyLab 自带的最小 adapter，无模型论文或外部权重。

用于检查策略服务与环境客户端的接线。它按机器人维度生成零动作，不能用来完成真实任务。
`process_data.sh` 和 `train.sh` 是展示命名约定的占位脚本。

公共参数和模型接入规范见[根 README](../../README.md) 与 [CONTRIBUTING](../../CONTRIBUTING.md)。

<a id="installation"></a>

## 安装与公共链路检查

传统脚本按 conda 环境运行：

```bash
cd XPolicyLab/policy/demo_policy
bash install.sh
conda activate <policy_env>
```

如果只检查公共 infra，可以从仓库根目录使用安装了根项目依赖的 Python：

```bash
python scripts/smoke_infra.py
```

该命令使用临时父工作区配置，验证真实 ws 服务的 reset、单条/批量观测与动作、编码图像路径；
结束后清理临时配置和服务进程，无需真实 benchmark、模型权重或 GPU。

<a id="data-processing"></a>

## 数据处理

占位入口，仅输出标准命名，不转换数据。可选尾参是示范 episode 限制的占位参数。

```bash
bash process_data.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> [expert_data_num]
bash process_data.sh RoboDojo stack_bowls arx_x5 joint
```

<a id="training"></a>

## 训练

占位入口，创建 `checkpoints/<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>-<seed>/` 并说明写入位置。
评测不读取该目录。

```bash
bash train.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> <seed> <gpu_id>
bash train.sh RoboDojo cotrain arx_x5 joint 0 0
```

<a id="evaluation"></a>

## 标准评测脚本

此路径还需要父工作区 `env_cfg/` 与 conda 两端环境；本轮的独立 CPU smoke 不依赖它们。

```bash
bash eval.sh <bench_name> <task_name> <ckpt_name> <env_cfg_type> <action_type> <seed> \
  <policy_gpu_id> <env_gpu_id> <policy_conda_env> <eval_env_conda_env>
EVAL_ENV_TYPE=debug bash eval.sh RoboDojo stack_bowls demo arx_x5 joint 0 0 0 <policy_conda_env> <eval_env_conda_env>
```

`DEBUG_OBS_ENCODED=1` 可额外检查编码图像输入；仿真需不设置 `EVAL_ENV_TYPE` 或设为 `sim`。
分机运行见[部署流程](../../README.md#-deployment-flow)。
改造为真实策略时，数据处理、训练和评测保持相同的 `ckpt_name`。

## 启动与进程管理

eval.sh 保留十个位置参数，使用共享生命周期回收本次创建的服务与 client 进程组。
模型专有差异与 CPU 验证范围见[生命周期说明](../../docs/reference/adapter-lifecycle.md)。
