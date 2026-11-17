# 评测范围、预算与成绩口径

控制台的“入口已配置”表示文件和启动配置检查通过，不表示真实模型或 benchmark 已验证。
评测配置、任务集合、seed、checkpoint 和结果都应保存在单次运行记录中。

## LIBERO

[LIBERO 官方说明](https://github.com/Lifelong-Robot-Learning/LIBERO#readme)将 LIBERO-100
拆分为用于预训练的 LIBERO-90 和用于下游研究的 LIBERO-10。
Spatial、Object、Goal 也是各自独立的任务集，不能把 LIBERO 理解成只有 LIBERO-10。
[OpenPI 的结果表](https://github.com/Physical-Intelligence/openpi/blob/main/examples/libero/README.md#results)
分别报告 Spatial、Object、Goal、10 及四组平均。

控制台提供以下范围：

| 选择 | 实际执行 | 每任务 50 次的预算 |
| --- | --- | --- |
| 常用完整评测（默认） | Spatial、Object、Goal、10，四组各 10 任务 | 2,000 episodes |
| 单组评测 | 所选 suite 的全部任务 | 通常 500；90 为 4,500 |
| 扩展全量 | 上述四组加 90，共 130 任务 | 6,500 episodes |

默认每任务 50 次，与[现有 OpenPI 客户端默认预算](https://github.com/Physical-Intelligence/openpi/blob/main/examples/libero/main.py)一致。
可减少次数做快速检查，但记录会标为 smoke，不进入首页的完整四组成绩。
50 次本身不保证与公开论文可比；仍须核对权重、训练数据、normalization stats、动作处理和客户端版本。
当前使用本机外部修改版 client，原始初始状态及各 suite 步数限制由该 client 决定。

一次多组运行加载一次模型，按固定顺序运行每组，分别保存日志、视频和逐任务汇总。
以逐 episode 的 Success 和逐任务汇总核对每个任务的次数及最终整数成功数；缺少结果、预算不足、
汇总不一致或客户端捕获异常，均判为运行失败，保留此前完成的组，不产出整体成绩。

主成绩为各 suite 成功率的等权平均，同时保存按 episodes 加权的成功率。
四组同预算时两者相同；含 90 时两者可能不同，扩展全量与常用四组成绩分开。
不把不同模型、benchmark、seed 或快速检查结果混成一个“整体成功率”。
首页仅展示最近一次已完成、每任务 50 次的 LIBERO 四组平均，并标明模型与 seed。
本轮没有运行 GPU 模型或真实仿真，CPU fixture 只验证编排和结果处理。

## RoboDojo / RoboTwin

当前控制台调用标准 adapter 的 eval.sh，任务列表来自本地配置。
支持单任务或“全部已登记任务”；后者只是配置列表的展开，不表示官方全集。
示例配置的一项任务不是完整 benchmark，policies 默认空，需明确登记实际已接入的模型。
每任务的日志分别保存；进程完成不等于任务成功，缺少统一指标时不生成成功率。

| Benchmark | 官方完整运行需要核对的内容 | 当前控制台边界 |
| --- | --- | --- |
| RoboDojo | 官方任务注册表、任务有效性、各任务原生预算、seed、环境版本 | 标准单任务入口可批量遍历已登记列表；当前缺父工作区和 conda，不声称已接入官方全量协议 |
| RoboTwin | 完整任务表、demo_clean / demo_randomized 场景、每任务预算、seed | 不提供一个没有实际传递的场景/次数开关，使用外部客户端配置；完整评测口径尚未验证 |

RoboDojo 的[原生 CLI](https://github.com/RoboDojo-Benchmark/RoboDojo/blob/main/scripts/README.md)
提供 benchmark 和 `--eval-num native`，不能用一个示例任务代替。
仓库已有 scripts/run_robodojo_sim_eval.sh 的 native 包装，但控制台当前标准路径未迁移为该后端。
RoboTwin 的[官方论文](https://robotwin-platform.github.io/paper.pdf)区分 clean / randomized 场景并说明 rollout 预算；
这些条件应随结果一起记录，不能只比较一个脱离场景的百分比。

## 协议检查与真机接口

CPU mock 检查公共协议，不运行真实模型，不生成模型 benchmark 成绩。
当前真机 profile 运行一个有步数上限的 episode；不是完整真机 benchmark。
任务成功与终止/截断保持独立，无成功反馈时不推断为失败或成功。
