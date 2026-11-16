# 架构地图

## 目录与运行边界

```text
<parent workspace>/
├── env_cfg/                    # benchmark 提供；不在本仓库
│   ├── <env_cfg_type>.yml
│   ├── robot/_robot_info.json   # runtime / Python 数据转换读取
│   └── sim/<sim_type>.yml
└── XPolicyLab/
    ├── AGENTS.md               # agent 开发入口与强制契约
    ├── configs/                # 工作区等共享配置
    ├── docs/                   # 状态、架构、规范、操作手册、决策、工作记录
    ├── experiments/            # 可提交的运行说明和小型结果
    ├── policy/<POLICY>/        # 自包含 adapter + 各自模型依赖
    ├── client_server/          # 通信协议及客户端/服务端
    ├── setup_policy_server.py  # 按 policy_name 导入 Model 并启动服务
    ├── model_template.py       # Model 契约
    ├── environment/            # 公共单环境适配、执行反馈与有限执行循环
    ├── utils/                 # 图像、维度、状态打包、checkpoint 等共享 helpers
    └── scripts/               # 转换、接入、工作区和开发检查入口
```

策略服务导入 `XPolicyLab.policy.<POLICY>.model`，环境端则推进仿真并消费动作。
两端可使用独立环境和 GPU；模型依赖留在 adapter 中，公共工具不能依赖 JAX / Torch 等模型运行栈。
当前 checkout 的父目录没有 `env_cfg/`，因此标准仿真路径尚缺 benchmark 工作区配置。

## 两条现有评测路径

| 路径 | 客户端 → 服务 | 数据契约 | 当前边界 |
| --- | --- | --- | --- |
| XPolicyLab 标准路径 | 环境 client → `client_server/ws` → `Model` | 标准 `vision/state/instruction`，共享维度与动作字段 | `policy/*/eval.sh`；ws 默认，legacy TCP 兼容 |
| 现有 LIBERO 路径 | 外部 `sim/libero/main.py` → OpenPI 原生 websocket server | `observation/image`、`observation/wrist_image`、`observation/state`、`prompt` | `Pi_05/serve_libero.sh` + `eval_libero.sh`；未经过 XPolicyLab Model |

两者都使用 websocket，但消息协议和 observation/action 语义不同，不能互换客户端。
LIBERO 的 7D action 是相对末端控制与夹爪量；不能仅因名称为 `ee` 就当成标准 7D 绝对位姿。
`utils/robot/_robot_info.json` 当前 `franka` 是双臂条目，也不能直接据此声称支持 LIBERO 单臂接口。

## 必须复用的契约

环境侧新增 [environment](../environment/README.md)，公共执行路径为
`环境适配器 → 标准观测 → PolicyAdapter → 动作块 → 环境执行 → ExecutionFeedback`。
本地 Model、标准 ws client 和显式映射的原生 API 可复用同一执行循环；仿真与真机通过相同 factory 入口接入。
具体 benchmark 和硬件构造需后续联调，当前只有 mock 与真实 ws 服务链路已验证，批量路径尚未迁移。

| 问题 | 唯一入口 / 规则 |
| --- | --- |
| 存储图像编解码 | `utils/process_data.py` 的 `decode_image_bit` / `encode_image_bit`；输出 RGB |
| 服务观测解码 | 服务端 `decode_obs_images`；`model.py` 接收数组，不再解码或交换通道 |
| runtime 动作维度 | `get_robot_action_dim_info(env_cfg_type)`；读取父工作区 `env_cfg/` |
| training shell 动作维度 | `utils/get_action_dim.sh`；读取本仓库 `utils/robot/_robot_info.json` |
| checkpoint 选择 | `utils/checkpoint_resolver.py`；模型特有 step 选择建立在共享解析结果之上 |
| policy 名称与配置 | `deploy.yml` 的 `policy_name` 等于目录名，保留 demo 的完整公共键集 |
| 状态和动作打包 | `pack_robot_state` / `unpack_robot_state`；明确 `joint` 与 `ee`、单臂与双臂 |

详细约束以 [AGENTS.md](../AGENTS.md) 和 [CONTRIBUTING.md](../CONTRIBUTING.md) 为准。
新机器人需要同时补齐父工作区和本仓库的两份 robot-info，键名按各自调用路径解释。

## 资产与代码

依赖环境、数据、权重、视频和长日志属于可重建或外部保存的运行资产，不提交到 Git。
实验记录保存资产位置、版本/校验标识、运行命令与结果；资产迁移必须同步更新记录。
稀疏视图只收起未使用的代码，不移动 Pi_05 的环境、checkpoint 和历史结果。
