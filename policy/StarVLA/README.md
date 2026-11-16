# StarVLA

**原适配贡献者：** RoboDojo Team
[论文](https://arxiv.org/abs/2604.05014) · [上游代码](https://github.com/starVLA/starVLA)

本 adapter 接入 StarVLA 视觉语言动作框架，源码 vendored 在 `source_starvla/`。
原 adapter 文档包含既往 RoboDojo 运行记录，下面保留其关键配方与结果；本轮只展开策略、整理中文说明并做静态检查，未重跑模型。
公共接口见[根 README](../../README.md)，当前验证范围见[交接页](../../docs/STATUS.md)。

<a id="supported-variants"></a>

## 支持的变体

| 对外名称 | 框架注册名 | 动作头 |
| --- | --- | --- |
| starVLA-OFT | `QwenOFT` | action-token 隐状态上的 MLP 回归头 |
| starVLA-GR00T | `QwenGR00T` | Flow-matching DiT |
| starVLA-π | `QwenPI_v3` | 逐层交错 cross/self-attention 的 DiT flow-matching 头 |

三者的 XPolicyLab `policy_name` 均为 `StarVLA`，具体实现由 checkpoint 配置决定。
原配方使用公开 `Qwen3-VL-4B-Instruct` 初始化 backbone，动作组件从头训练；
该 adapter 的公开配方不要求内部机器人数据、私有示范或未发布的策略权重。

<a id="external-starvla-runtime-contract"></a>

## Runtime 契约

若通过 `starvla_root` 使用外部 checkout，必须与 vendored runtime 保持相同接口。权重与统计量需另行准备。
RoboDojo ARX X5 发布配方的契约为：

- 根据 checkpoint 配置注册并重建 `QwenOFT`、`QwenGR00T` 或 `QwenPI_v3`。
- 接收三路 RGB：`cam_head`、`cam_left_wrist`、`cam_right_wrist`，以及指令和可选 14D 原始绝对关节状态。
  状态顺序为左臂、左夹爪、右臂、右夹爪。
- 推理前使用匹配 checkpoint 的 `arx_x5` 统计量归一化状态；50-step 配方对全部维度（含连续夹爪）使用 q99。
- 内部动作形状为 `[batch, horizon, 14]`；返回 XPolicyLab 前用匹配统计量反归一化。
  服务 metadata 暴露 `action_chunk_size`。
- 预测 horizon=50，RoboDojo 执行前 16 步后重新规划。
- 发布的 RoboDojo PI-v3 checkpoint 需要上游修复
  [c521dec](https://github.com/starVLA/starVLA/commit/c521decb7441c7dfea282c61dc758456bcffbb8f)
  的规范交错 DiT forward。旧的手写循环把每层都当作 cross-attention，与该 checkpoint 不兼容。

保留运行目录布局，使 `config.yaml`、`config.full.yaml`、`dataset_statistics.json` 与 `checkpoints/` 相邻。
公开数据混合名为 `robodojo_arx_x5_h50_q99`，兼容别名为 `robodojo_v21_all_h50_q99`。

<a id="installation"></a>

## 安装

原安装脚本向当前环境安装 PyTorch 2.6、上游依赖、flash-attn，并 editable 安装源码；运行前确认目标环境。

```bash
cd XPolicyLab/policy/StarVLA
bash install.sh
conda activate <policy_env>
```

<a id="data-processing"></a>

## 数据处理

将 RoboDojo 示范转换到 `data/<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>/`。
`raw_task_dirs` 为源目录下任务名或逗号列表，默认 `ckpt_name`；非数值第五参数按它解释。
输出为带[官方键](../../README.md#official-lerobot-conversion)的 LeRobot v3.0：
`observation.state`、`action`、`observation.images.cam_high` / `cam_left_wrist` / `cam_right_wrist`。
使用附带转换器是因为 GR00T 风格 loader 还需要 `meta/modality.json`。

```bash
bash process_data.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> [expert_data_num] [raw_task_dirs]
bash process_data.sh RoboDojo stack_bowls arx_x5 joint
bash process_data.sh RoboDojo stack_bowls_50ep arx_x5 joint 50 stack_bowls
bash process_data.sh RoboDojo stack_bowls_full arx_x5 joint stack_bowls
```

<a id="training"></a>

## 训练

```bash
bash train.sh <bench_name> <ckpt_name> <env_cfg_type> <action_type> <seed> <gpu_id> [extra_args...]
bash train.sh RoboDojo stack_bowls arx_x5 joint 0 0
```

Checkpoint 写入 `checkpoints/<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>-<seed>/`。
评测可传短运行名、完整运行目录名或 checkpoint 路径。
训练器从 `xpolicy_oft_vla.yaml` 在 `.generated/` 生成运行配置，通过 `meta/modality.json` 检查数据，
按 GPU 列表推导进程数，并将尾部 `extra_args` 转给上游训练器。

训练和转换使用相同 `ckpt_name`，也可显式设置 `STARVLA_XPOLICY_DATASET_NAME`。
`STARVLA_DATA_ROOT` 默认 `data/`，`STARVLA_DATA_MIX` 默认 `xpolicylab_runtime`，
数据名默认 `<bench_name>-<ckpt_name>-<env_cfg_type>-<action_type>`。

<a id="evaluation"></a>

## 标准评测

```bash
bash eval.sh <bench_name> <task_name> <ckpt_name> <env_cfg_type> <action_type> <seed> \
  <policy_gpu_id> <env_gpu_id> <policy_env> <eval_env_conda_env>
bash eval.sh RoboDojo stack_bowls RoboDojo-stack_bowls-arx_x5-joint-0 arx_x5 joint 0 0 0 <policy_env> <eval_env_conda_env>
```

`EVAL_ENV_TYPE=debug` 检查离线接线，仍需模型环境与权重；不设置或设为 `sim` 时走仿真。
分机运行见[部署流程](../../README.md#-deployment-flow)。

<a id="released-hugging-face-robodojo-checkpoints"></a>

### 已发布 RoboDojo checkpoint 的专用入口

发布版准备、启动、simulator 预检及其复现测试位于 `scripts/`，根级 `setup_eval_*` 保持固定 adapter 入口。
专用入口锁定 Hugging Face revision，保留完整运行目录，并校验权重和 normalization SHA-256：

```bash
# 在对应 RoboDojo 工作区先准备官方 benchmark 资产。
cd RoboDojo
bash scripts/init_assets.sh
cd XPolicyLab/policy/StarVLA

STARVLA_ROBODOJO_NUM_ENVS=1 bash scripts/eval_hf_robodojo.sh oft build_tower 0 0 1 \
  <starvla_env> <robodojo_sim_env> 10
STARVLA_ROBODOJO_NUM_ENVS=5 bash scripts/eval_hf_robodojo.sh groot build_tower 0 0 1 \
  <starvla_env> <robodojo_sim_env> 10
STARVLA_ROBODOJO_NUM_ENVS=5 bash scripts/eval_hf_robodojo.sh pi_v3 build_tower 0 0 1 \
  <starvla_env> <robodojo_sim_env> 10
bash scripts/eval_hf_robodojo.sh pi_v3 build_tower 0 0 1 <starvla_env> <robodojo_sim_env> native
```

`native` 使用任务官方 episode 数。10-layout 是快速契约检查，不能代替官方 50-episode 协议。
原 adapter 文档记录的发布版 `build_tower` 50-episode 参考值如下，**本轮未独立复核**：

| checkpoint | 成功率 | Score |
| --- | --- | --- |
| [QwenOFT](https://huggingface.co/StarVLA/Qwen3vl4b-OFT-RoboDojo) | 36% | 50.60 |
| [QwenGR00T](https://huggingface.co/StarVLA/Qwen3vl4b-GR00T-RoboDojo) | 14% | 20.80 |
| [QwenPI_v3](https://huggingface.co/StarVLA/StarVLA-Qwen3vl4b-PIv3-RoboDojo) | 56% | 65.00 |

原文还记录了 2026-08-09 在 RoboDojo `36bfcb7c`、XPolicyLab `fd420490` 加当时改动上的 seed-0 结果：

| checkpoint | Isaac 并行环境数 | 成功数 | Score | Unstable |
| --- | --- | --- | --- | --- |
| QwenOFT | 1 | 4/10 | 58.00 | 0 |
| QwenGR00T | 5 | 1/10 | 20.00 | 0 |
| QwenPI_v3 | 5 | 5/10 | 57.00 | 0 |

据该历史记录，相同 PI-v3 snapshot / seed / layout 下，旧 all-cross-attention forward 为 0/10、Score 0，
规范交错 forward 为 5/10、Score 57；另外两个变体不经过此 PI-v3 路径。
这些是原 adapter 历史记录，**不是本机本轮实测**。

专用入口自行启动 vendored StarVLA server，不应替换为另一个未固定版本 checkout 的 server。
机器人动作开始前需由握手证明：输入 RGB、原始 14D 状态的 q99 只应用一次、输出反归一化绝对关节动作、
horizon=50 / execute=16；若发布 manifest 要求特定 PI-v3 forward，还必须证明该版本。
要求来自具体发布 manifest，不能对所有旧 PI-v3 checkpoint 一概强制同一实现。
首次带状态请求会记录原始值与归一化值；状态或 normalization 契约不兼容时应先失败。
原文对训练视频的检查认为三种发布权重都应接收 RGB，无需额外通道交换。

专用入口关闭 renderer 多 GPU，显式指定物理 simulator GPU，默认单环境顺序执行。
`STARVLA_ROBODOJO_NUM_ENVS=5` 可复现历史五环境 batching；`EVAL_NUM=10` 仍表示共十个 layout，分两批。
`deploy.yml` 保持 batch-capable。launcher shim 禁用 argparse 参数缩写，避免 `--device cuda:N` 与 `--device_id` 冲突。
`STARVLA_ROBODOJO_KIT_ARGS` 用于本机确实需要的 Kit 参数；Isaac EULA 经实际接受后可用 `OMNI_KIT_ACCEPT_EULA=YES` 非交互运行。

启动前会检查官方机器人、物体、材质、layout 资产及路径环境所需 OpenGL/GLU 库。
环境日志需到达 `Simulation App Startup Complete` 并开始任务 episode 才算有效运行。
在此前发生的 `VK_ERROR_DEVICE_LOST`、退出 139 或 NVIDIA Xid 属于 simulator / GPU 故障，不计作零分任务结果。
接近零成功率伴随异常臂动作时，应检查握手与首次状态日志。

策略环境参数支持 conda 名、venv 目录、含 `.venv` 的 uv 项目或 Python 可执行路径。
RoboDojo 环境参数支持 conda 名或绝对 prefix；非交互 shell 未初始化 conda 时可用 prefix。
发布清单见 [hf_robodojo_checkpoints.json](scripts/hf_robodojo_checkpoints.json)。

| 环境变量 | 用途 |
| --- | --- |
| `STARVLA_HF_ROOT` | 下载根目录 |
| `STARVLA_HF_LOCAL_FILES_ONLY=1` | 禁用网络下载 |
| `STARVLA_HF_VERIFY_ONLY=1` | 校验已准备好的本地目录 |
| `STARVLA_BASE_VLM` | 离线 Qwen3-VL-4B-Instruct 路径，三个发布版均引用它 |
| `STARVLA_HF_SKIP_WEIGHT_HASH=1` | 检查大小后跳过完整哈希；仅在已完整校验后使用 |
| `STARVLA_CPU_THREADS` | 未设置 OMP/MKL 时的导入线程数，默认 8 |

专用入口采用单进程，并清理继承的 torchrun / MPI rank 变量，避免等待不存在的其他 rank。

<a id="configuration"></a>

## 配置

检查 `deploy.yml` 的 `starvla_root`、`checkpoint_path`、`starvla_server_host`、`starvla_server_port`、
`unnorm_key`、`use_ddim`、`num_ddim_steps`、`image_size`、`execute_horizon`、`include_state`、
`require_runtime_contract`、`required_pi_v3_forward`。
`execute_horizon` 是每个预测 chunk 实际执行的步数。
`include_state: auto` 依次读取 `config.yaml`、`config.full.yaml` 的 `datasets.vla_data.include_state`，最后默认 false；
显式布尔配置可覆盖，环境变量 `STARVLA_INCLUDE_STATE` 优先级最高。

| 环境变量 | 用途 |
| --- | --- |
| `STARVLA_EXECUTE_HORIZON` | 每个 chunk 执行步数 |
| `STARVLA_IMAGE_SIZE` | adapter 输入图像大小 |
| `STARVLA_INCLUDE_STATE` | 显式覆盖 checkpoint 的状态输入选择 |
| `STARVLA_UNNORM_KEY` | 选择 normalization 统计键 |
| `STARVLA_CKPT_PATH` / `STARVLA_ROOT` / `STARVLA_SERVER_PID` | 相关脚本的 checkpoint、源码与进程配置 |

训练变量见训练章节，其他专用入口配置以脚本与发布清单为准。
