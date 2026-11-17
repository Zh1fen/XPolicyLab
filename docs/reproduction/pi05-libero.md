# Pi_05 / LIBERO：本地资产与运行手册

状态：已有训练配方、环境、checkpoint 和历史视频；本轮未重训、未运行真实模型推理或仿真评测。
本手册用于接续现有工作，不构成官方 π0.5 结果复现声明。

网页控制台默认一次运行 Spatial、Object、Goal、10 四组，每任务 50 次，共 2,000 episodes；
LIBERO-90 作为扩展实验单列，不混入常用四组平均。参见[评测口径](../reference/evaluation-protocols.md)。

## 路径与版本

以下是 2026-11-15 实际检查到的本机资产；可移植脚本不依赖这些个人路径。

| 资产 | 本机位置 / 状态 |
| --- | --- |
| 策略代码 | `policy/Pi_05/openpi/`；已有本地修改，尚未提交 |
| 策略 Python | `policy/Pi_05/openpi/.venv/bin/python`，Python 3.11.18 |
| 包版本 | JAX 0.5.3、Torch 2.10.0、LeRobot 0.4.4、websockets 15.0.1 |
| 数据根 | `/home/zhanyifeng/workspace/datasets/LEROBOT_LIBERO_DATA` |
| 初始权重 | 配置原有默认 `/home/zhanyifeng/workspace/models/pi05_base/params`；训练前显式设置 `PI05_BASE_PARAMS` |
| norm stats | `policy/Pi_05/openpi/assets/pi05_libero/libero/norm_stats.json`，目录存在不等于已验证与权重匹配 |
| 训练产物 | `policy/Pi_05/checkpoints/Libero-pi05_libero-franka-ee-0/{29000,29999}` |
| 环境端 | `/home/zhanyifeng/workspace/sim/libero/main.py` 和 `.venv/`，在本仓库之外 |
| 旧视频 | `policy/Pi_05/eval_result/Libero/`；spatial 500 个、goal 23 个；只有视频，缺正式汇总 |

现有四个数据子集的 `meta/info.json` 均为 `v3.0`、20 fps；相邻的 `*_old` 目录是旧版 `v2.1` 资产，本轮未转换或删除。

| 子集 ID 前缀（完整后缀均为 `_no_noops_1.0.0_lerobot`） | episodes | frames |
| --- | --- | --- |
| libero_spatial | 432 | 52,970 |
| libero_object | 454 | 66,984 |
| libero_goal | 428 | 52,042 |
| libero_10 | 379 | 101,469 |

旧视频文件名中的 success/failure 标记不作为完整评测成功率，goal 23 个也不视为完整 suite。

## 原有本地修改

在这次整理前已有：`pi05_libero` 双 expert LoRA 配方、四数据集联合加载、
LeRobot 键重映射、按 asset_id 保存 normalization stats、checkpoint 保留数量控制。
这些训练行为本轮保留，不把已有 checkpoint 的生成配置当作已完全追溯。

| 文件 | 本地差异与需注意的边界 |
| --- | --- |
| `openpi/src/openpi/training/config.py` | `pi05_libero` 为 horizon=10、batch=4、30,000 steps、EMA=None；不是官方全量微调配方；LIBERO 数据工厂的键变更也影响复用它的其他配置 |
| `openpi/src/openpi/training/data_loader.py` | 逗号分隔多 repo；用首个子集 fps 构建时间戳；当前四个均为20 fps，推广前需校验一致性 |
| `openpi/scripts/compute_norm_stats.py` | 使用 asset_id 保存统计，合并数据集不能把带逗号的 repo 列表当作资产目录 |
| `openpi/scripts/train.py`、`training/checkpoints.py` | 向 checkpoint manager 传递 max_to_keep；当前配方保留最新两个，无额外 keep_period |

本轮额外调整：`train.sh` 取消自动 `--overwrite`，尾部参数显式转发；两个 LIBERO wrapper 参数化。
不修改用户已有数据、权重、视频、robot-info 或训练配方。

## 准备环境

模型环境遵循 [adapter 安装说明](../../policy/Pi_05/README.md#installation) 和本地 `openpi/uv.lock`。
对已有环境先记录版本，避免为了整理文档而重新同步大型依赖。

公共检查可直接使用已有 Pi_05 Python：

```bash
# cwd: XPolicyLab 仓库根目录
python3 scripts/check_workspace.py
python3 -m unittest discover -s tests -v
policy/Pi_05/openpi/.venv/bin/python scripts/smoke_infra.py
```

如需独立 CPU 开发环境：先 `uv venv .venv`，再 `uv pip install --python .venv/bin/python -e .`，
使用 `.venv/bin/python scripts/smoke_infra.py`。这只安装根 infra 依赖，不安装策略模型栈。
本轮使用已有 Pi_05 环境验证了 smoke；未新建并验证该独立环境。

## 原生服务与评测

先用一个短预算验证连通性，再安排正式评测。以下为可复用命令，**本轮未执行模型服务或仿真**。
必须使 server 的实际 step 与 client 记录的 step 一致；wrapper 不会跨进程自动校验身份。

终端 A，从仓库根运行：

```bash
export PI05_CHECKPOINT_DIR="$PWD/policy/Pi_05/checkpoints/Libero-pi05_libero-franka-ee-0/29999"
export POLICY_PORT=8000
export POLICY_GPU_ID=0
bash policy/Pi_05/serve_libero.sh
```

终端 B，从仓库根运行，填入自己的环境端位置与独立结果目录：

```bash
export LIBERO_CLIENT_ROOT="$HOME/workspace/sim/libero"
export PI05_CHECKPOINT_STEP=29999
export PI05_RUN_NAME=Libero-pi05_libero-franka-ee-0
export POLICY_HOST=127.0.0.1
export POLICY_PORT=8000
export EVAL_GPU_ID=1
export EVAL_SEED=7
export EVAL_RESULT_ROOT="$PWD/artifacts/pi05-libero-new-run"
bash policy/Pi_05/eval_libero.sh libero_spatial 1
```

当前外部 client 逐 suite 跑所有任务；`1` 是每任务一次，并非整个 suite 只跑一次。
client 的 `--args.*` 参数属于该外部 `main.py` 的 Tyro 接口；其他 LIBERO client 不一定兼容。
结果目录应每次独立设置，避免 client 按相同 seed/step 命名视频时覆盖历史结果。

wrapper 参数来源：

| 变量 | 默认 / 用途 |
| --- | --- |
| `PI05_CHECKPOINT_DIR` | 必填；指向包含 `params/` 的精确 step 目录 |
| `PI05_TRAIN_CONFIG` | `pi05_libero`，native server 加载配置 |
| `POLICY_PORT` / `POLICY_HOST` | `8000` / `127.0.0.1`；host 是 client 连接地址，server 使用 OpenPI 自身监听逻辑 |
| `POLICY_GPU_ID` / `EVAL_GPU_ID` | 均默认 `0`；分别设置 CUDA_VISIBLE_DEVICES 与 MUJOCO_EGL_DEVICE_ID |
| `OPENPI_ROOT` / `UV_BIN` | adapter 的 `openpi/` / `uv`，server 入口覆盖 |
| `LIBERO_CLIENT_ROOT` | 必填；含 `main.py` 的 client 项目目录 |
| `LIBERO_PYTHON` | `<client>/.venv/bin/python`；可指定绝对可执行路径 |
| `PI05_CHECKPOINT_STEP` | 必填；写入结果命名，需与 server 匹配 |
| `PI05_RUN_NAME` | `Libero-pi05_libero-franka-ee-0`，运行身份标签 |
| `EVAL_SEED` | `7`；正式比较时固定并记录 |
| `EVAL_RESULT_ROOT` | adapter 的 `eval_result/`；正式运行应改为独立目录 |
| `MUJOCO_GL` | `egl`，可覆盖 |

两个 wrapper 的额外尾参分别转发给 OpenPI serve / 外部 LIBERO client；公共 `eval.sh` 的十参数接口不变。

## 仅在需要新训练时

数据已是 v3.0，无需重复执行迁移。显式设置权重与数据位置，确认四个子集的版本、fps、键布局一致。
已有 stats 与 checkpoint 配对未核实前，不覆盖它们。若要重算，先保存现有 stats 和版本标识，
再从 `policy/Pi_05/openpi` 运行 `uv run --frozen scripts/compute_norm_stats.py --config-name pi05_libero`。

下面展示创建**新名字**训练的配方，GPU 集合按实际硬件调整，本轮未执行：

```bash
# cwd: XPolicyLab/policy/Pi_05
export HF_LEROBOT_HOME="$HOME/workspace/datasets/LEROBOT_LIBERO_DATA"
export PI05_BASE_PARAMS="$HOME/workspace/models/pi05_base/params"
export OPENPI_TRAIN_CONFIG_NAME=pi05_libero
export OPENPI_LEROBOT_REPO_ID="libero_spatial_no_noops_1.0.0_lerobot,libero_object_no_noops_1.0.0_lerobot,libero_goal_no_noops_1.0.0_lerobot,libero_10_no_noops_1.0.0_lerobot"
export OPENPI_FSDP_DEVICES=2
bash train.sh Libero pi05_libero_new franka ee 0 0,1,2,3
# 接续已有同名训练时明确添加 --resume；--overwrite 会清空对应 checkpoint 目录。
```

训练标签中的 `franka ee` 沿用历史命名，仅用于此原生路径的身份标签；不证明标准 adapter 已支持其动作语义。

## 来源标识与后续工作

2026-11-15 清点时的 SHA-256：

```text
openpi/uv.lock
2ffa14b9cb4c46791b11785cab6a003cca70fa696f8db3af52fc6e745a15b1e8
外部 sim/libero/main.py
22208e7ce13a58ae6d7dd32f11a32ac2115e9cd98982e81da4d84e0f7b463f45
外部 sim/libero/requirements.txt
821008c9804ec835bccee66ab93c177f47a62a845c010497b5aea06829331727
```

这些标识帮助发现资产变化，不代替 checkpoint 的完整 provenance。当前外部 client 未纳入本仓库版本管理，
仍需将其固定到可获取的源码版本/归档并记录安装步骤，才能完成跨机器复现。
此外还需固定模型目标配方、验证 stats 与权重配对、记录逐 episode 结果，并决定是否将 LIBERO 接到标准 XPolicyLab client。
现有标准 `model.py` 的三相机输入不能直接用于此双相机 LIBERO 配方；动作语义也需要单独适配。

标准 RoboDojo 转换入口已修正父工作区路径和 LeRobot 0.4.4 API，并通过临时 HDF5 小样本逐帧回读。
数据路径、输出保护和 next-state 动作规则见[Pi_05 数据处理](../../policy/Pi_05/README.md#数据处理)。
该转换与此处既有 LIBERO v3.0 数据是独立路径，现有数据未重新生成；视频模式和大规模转换未重跑。
