# 2026-11-16：更新用户确认的策略集合

## 目标与起点

用户明确保留 GR00T_N17、TinyVLA、FastWAM、LingBot_VA、LingBot_VLA、StarVLA、Pi_05、demo_policy，
收起此前的 ACT / DP。起始 HEAD 仍为 `6baccd57`，上一轮 infra 与 Pi_05 改动尚未提交。
本轮只调整策略工作区、说明文档与相应测试 fixture。

## 变更

- 默认配置改为用户选定的八个目录，沿用 `StarVLA` / `Pi_05` 原有模块名。
- 同步根 README、AGENTS、策略入口、项目范围、STATUS 和决策；历史工作记录不改写。
- 新展开的六个 adapter 顶层 README 整理为中文，保留关键命令、限制和旧英文章节锚点；vendor 源码文档保持原样。
- 测试 fixture 从默认配置创建策略，避免测试绑定旧 ACT / DP 名单。
- ACT / DP 的前轮中文 README 保存至 `artifacts/maintenance/2026-11-16-policy-selection/`；
  恢复对应 Git 原文后通过保护检查收起，不隐藏未保存的本地修改。

## 验证

| 命令 / 检查 | 结果 | 范围 |
| --- | --- | --- |
| `python3 scripts/policy_workspace.py focus` / `status` | 通过 | 磁盘恰好是用户选定的八个目录，ACT / DP 已收起 |
| `python3 scripts/check_workspace.py` | 通过 | 28 份 Markdown 的本地路径/可见锚点、八个 adapter 公共键、37 个 Python 文件语法、51 个 shell 文件语法 |
| `python3 -m unittest discover -s tests -v` | 通过，12 项 | 临时仓库按当前配置构建，默认目录保留、恢复与本地工作保护；Pi_05 启动参数测试 |
| `git diff --check` | 通过 | 新文档末尾空行已清理，无空白错误 |
| Git 与本地资产核对 | 通过 | 全部 78 个 adapter 仍在 Git，可见 policy 跟踪文件 1,107 个，无跟踪策略删除；Pi_05 原有五文件训练补丁与前轮快照完全一致，523 个旧视频仍在原位置 |

新展开策略的静态检查不等于模型完整审查或运行验证；远程 CI 未触发。

## 遗留与交接

本轮不安装模型依赖、不运行训练或仿真，也不修改 Pi_05 现有代码与本地资产。
目录保留状态与模型运行效果分开记录；当前已知限制继续见 [STATUS](../STATUS.md)。
