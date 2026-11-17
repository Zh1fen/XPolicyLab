# 开发与记录规范

## 开始工作

先读根 [AGENTS.md](../AGENTS.md)、[当前状态](STATUS.md)，再读任务相关手册和源码。
运行 `git status --short`；把已有修改视为用户工作，先理解再改，不能 reset、覆盖或清理。
默认只搜索活动策略和共享 infra，按需展开其他策略，不全量加载 vendor 源码。

记录任务目标、影响路径和可验证的完成条件；小修改在工作记录里写清即可，不另建冗长计划。
实现以现有 XPolicyLab 契约为基础，模型特例放 adapter，不为尚未开展的研究预建框架。

## 实现约定

- Python 路径用 `pathlib`；共享 infra 按根项目的 Python >=3.10，Pi_05 按自己的 >=3.11 环境。
- shell 使用 `set -euo pipefail`、引用路径变量、从脚本位置解析路径；新增入口应有 `--help`、清晰错误信息和可覆盖配置。
- 控制台文案保持简洁：展示参数、状态与具体错误，避免重复说明、宣传标语和防御性段落。评测方法与能力边界写入文档；图标使用统一的 SVG。
- 数据、模型和客户端根目录通过参数或环境变量配置，禁止把个人 home 路径作为可移植入口的默认值。
- 小范围修改，避免整目录格式化 vendor。必要的 vendor 修改要说明原因、上游差异和验证。
- 复用共享图像、维度、状态与 checkpoint helpers；强制契约见根 AGENTS，避免在多份文档里复制实现。
- 运行训练前确认 checkpoint 输出目录；覆盖和清理必须显式表达，不把破坏已有结果作为便捷默认行为。

## 验证与证据

从仓库根目录运行：

```bash
python3 scripts/check_workspace.py
python3 -m unittest discover -s tests -v
git diff --check
```

`check_workspace.py` 只做本地文档路径/可见 Markdown 锚点、配置、活动 adapter 公共键、入口语法检查；不导入模型，不访问 GPU。
GitHub Actions 在 push / PR 时执行相同的轻量检查与测试；本轮只在本地执行，未触发远程 CI。
修改核心协议/图像链路时，再在装有根项目依赖的 Python 环境运行：

```bash
python scripts/smoke_infra.py
```

公共环境接口可用 `python3 scripts/run_mock_episode.py` 无依赖检查。
完整反馈/本地解码/ws 测试需根 infra 依赖；若系统 Python 缺依赖会明确跳过相应测试，
交付前应再用安装了依赖的 Python 跑完整测试。CI 已加入根依赖安装与 ws smoke，仍不安装模型栈。

接入 adapter 时使用仓库已有 `xpolicylab-model-integration` / `xpolicylab-adapter-check` skill，
按 CONTRIBUTING 检查特有行为，并在模型环境可用时执行 debug 闭环。
`bash -n` 必须逐文件运行：`bash -n a.sh b.sh` 实际只检查第一个文件。
可用 `for f in policy/<POLICY>/*.sh; do bash -n "$f" || break; done`，公共检查器已逐文件执行。
训练、simulator 或目标效果没有实际跑过，就写“未运行”，不根据静态阅读标通过。

## 什么时候写在哪里

| 发生的事情 | 更新位置 |
| --- | --- |
| 完成一个有实质内容的开发任务 | `docs/worklog/YYYY-MM-DD-<topic>.md`，写目标、变更、验证、遗留 |
| 当前能力、阻塞、下一步改变 | `docs/STATUS.md`，保持简短、可交接 |
| 改变跨模块边界、数据口径、策略范围 | `docs/decisions/NNNN-<topic>.md`，写取舍与后果 |
| 新增或修改运行命令、依赖、配置 | 同步 adapter README / `docs/reproduction/` |
| 做一次训练、评测或对照实验 | `experiments/<run-id>/record.md`，从模板起步 |
| 只改拼写等微小内容 | 随代码说明即可，不强制另写日志 |

工作记录记事实与验证，不记录内部思维链或逐条工具输出。
同一任务在同一天持续修改时更新同一条记录；长期规则写规范，临时状态写 STATUS，避免重复堆积。
默认不自动 commit、push 或运行长时间 GPU 任务。

## 实验最小记录

使用 [实验模板](templates/experiment.md)，至少包含：代码 revision 与未提交 diff 的保存位置、
模型/环境依赖版本、数据版本/拆分、权重和 normalization stats、预处理、动作语义、
任务集、seed/初始状态、episode 预算、完整命令、成功数/总数、错误/超时数、产物位置和结论边界。
长日志和视频保持在忽略目录或外部存储，Git 只放精简记录和小型指标。
将“未运行”“通过”“失败”“历史资产，未经重跑”分开标注。

## 交付前

审阅 `git diff`，运行对应检查，同步受影响的文档与 STATUS，并记录未验证项。
项目自有 README 使用中文，根 README_zh 仅保留兼容入口；实验配方只维护一个权威位置，其他文档用链接引用。
提交描述说明问题、最终行为和验证。infra 改动使用通用描述，adapter 改动沿用 CONTRIBUTING 的提交规范。
