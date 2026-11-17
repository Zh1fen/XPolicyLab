# 2026-11-16：评测范围、预算与汇总修正

## 用户目标与发现

用户指出 LIBERO 缺少一次评测所有 suite 的入口，并要求检查其他 benchmark 的口径。
核对 LIBERO 官方仓库、OpenPI 的客户端/结果表和本机外部 client 后确认：
常用 OpenPI 结果是 Spatial、Object、Goal、10 四组，不是只有 10；90 是原始设计的预训练集合。
原控制台只有单组选项、默认三次预算，LIBERO 只取日志最后汇总；首页还将不同运行混成整体成功率。
RoboDojo/RoboTwin 的配置各只有一个示例任务，也没有明确登记模型兼容关系，不能当成完整 benchmark。
来源和边界见[评测口径](../reference/evaluation-protocols.md)。

## 最终实现

- 默认 LIBERO 四组，每任务 50 次，共 2,000 episodes；支持单组及明确含 90 的五组扩展（6,500）。
- 少于 50 次标为 smoke；模型加载一次、各组串行，参数保存实际展开后的任务列表与总预算。
- 每组独立日志和结果；核对每个任务的逐次 Success、次数和汇总，保留整数成功数，拒绝缺失/异常/不一致结果。
- 任务失败或取消时保留已完成分组，未全部完成不产出整体成功率；正常结果分别保存 suite 等权和 episode 加权汇总。
- 页面显示分组结果与总预算，首页只显示最近一次完整预算的四组平均，标明模型/seed，不混合不同运行。
- RoboDojo/RoboTwin 增加“全部已登记任务”，逐任务执行并保存日志；明确是本地任务集合，policies 需显式登记。
- 原生预算/场景划分未接入之处如实显示。真机是单 episode 接口，mock 是协议检查，不包装为完整 benchmark。
- 保存后端配置和 LIBERO client SHA256；去掉 LIBERO 等路径中并未使用的 max_steps 参数记录。

## 验证

| 命令 / 检查 | 结果 |
| --- | --- |
| `python3 -m unittest discover -s tests -p test_evaluation.py -v` | 新增 12 项 CPU 测试，包含真实 TCP/子进程的四组编排；无模型依赖 |
| `policy/Pi_05/openpi/.venv/bin/python -m unittest discover -s tests -q` | 78 项通过；首次 fixture 在 Python 3.11 下存在字符串语法问题，修正后全量通过 |
| Playwright / Chromium | 四组默认、2,000/6,500 预算、smoke/非官方全集提示、不同运行不混分、四行分组结果通过，无脚本错误 |
| `python3 scripts/check_workspace.py` / `node --check web/static/app.js` / `git diff --check` | 通过 |

浏览器历史分组展示使用隔离的 CPU UI fixture，未冒充模型评测结果，也未写入用户正式历史。
QA 服务已关闭；未重启或终止用户自己启动的控制台，未运行真实 GPU 模型或仿真。

## 限制

本机外部 LIBERO client 有既有动作处理改动，完整预算不等于官方配方复现。
RoboDojo 原生 benchmark/native 预算及 RoboTwin clean/randomized 完整协议，仍需安装和联调外部工作区；
本轮修复了任务遍历和展示口径，不声称完成这两个 benchmark 的真实全量集成。
用户需重启 `./start.sh` 加载本轮后端改动。
