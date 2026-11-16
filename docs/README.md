# 研究 infra 文档入口

本仓库基于 XPolicyLab，当前目标是建立可运行、可复现、可持续开发的机器人策略基础设施。
先把一种真实策略在仿真中跑通，保留配置、结果和证据，再扩展模型与 benchmark。

## 按任务阅读

| 要做什么 | 入口 |
| --- | --- |
| 了解现在做什么、还缺什么 | [当前状态](STATUS.md) → [范围与验收](project.md) |
| 理解目录、协议和数据边界 | [架构地图](architecture.md) |
| 接仿真/真机环境、统一执行反馈 | [环境接口与公共入口](../environment/README.md) |
| 开发或让 agent 继续工作 | [开发与记录规范](development.md)、[根 AGENTS.md](../AGENTS.md) |
| 运行已有 Pi_05 / LIBERO 路径 | [复现手册](reproduction/pi05-libero.md) |
| 增加/恢复策略 | [策略工作区](../policy/README.md) |
| 查设计原因 | [工作区设计](decisions/0001-infra-workspace.md)、[当前策略集合](decisions/0002-user-selected-policies.md) |
| 查实际做过什么 | [工作记录目录](worklog/README.md) |
| 记录一次实验 | [experiments](../experiments/README.md)、[实验模板](templates/experiment.md) |
| 查 adapter 提交契约 | [CONTRIBUTING.md](../CONTRIBUTING.md)、[demo_policy](../policy/demo_policy/README.md) |

## 文档的职责

- `STATUS.md` 是当前交接点：已验证能力、阻塞和下一步；发生变化时更新。
- `project.md` 放目标和验收；`architecture.md` 放稳定边界；`development.md` 放工作规则。
- adapter README 放模型命令和模型特例；公共参数以根 README / CONTRIBUTING 为准。
- `decisions/` 解释长期取舍；`worklog/` 记录一次实际改动；`experiments/` 记录一次运行证据。
- `templates/` 只提供格式，不把空模板当作完成的记录。

本地基础检查命令为 `python3 scripts/check_workspace.py` 和
`python3 -m unittest discover -s tests -v`；GitHub Actions 的 Workspace checks 执行同样的轻量检查。
CI 不运行 GPU 模型或 simulator，实际运行证据仍需写入实验记录。

按需读相关文档，通常从 `STATUS.md` 和当前任务涉及的路径开始，无需一次加载整个仓库。
项目自有 README 和研究文档使用中文；根 `README.md` 为主文档，`README_zh.md` 为兼容入口。
第三方 vendored 文档保留原文；根 README 保留旧英文锚点，兼容已有 adapter 链接。
