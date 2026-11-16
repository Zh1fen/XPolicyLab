# 0002：按用户确认保留八个 adapter

- 日期：2026-11-16
- 状态：采用
- 依据：用户本次明确列出的保留名单；替代 [0001](0001-infra-workspace.md) 中的默认策略集合

## 背景与决定

用户希望围绕前沿策略复现组织 infra，不接受此前由 agent 自选的 ACT / DP 对照入口。
默认集合改为 `GR00T_N17`、`TinyVLA`、`FastWAM`、`LingBot_VA`、`LingBot_VLA`、`StarVLA`、
`Pi_05`、`demo_policy`。用户输入的 starvla、pi05 使用已有目录名 `StarVLA`、`Pi_05`，不重命名模块。

ACT、DP 与其他非活动策略一起收起，共 70 个 adapter 仍完整保存在 Git。
八个入口的具体复现顺序和模型验证另行开展，本次不更改模型、训练或部署行为。

## 后果与恢复

`configs/policy_workspace.json` 是默认名单的配置来源，工作区脚本、测试与 CI 按它读取。
新增活动 adapter 的项目自有 README 使用中文，第三方 vendored 文档保留原文。
收起前保存此前由 agent 生成的 ACT / DP 中文 README 到本地忽略的维护归档，再恢复其 Git 原文，
避免把未保存的翻译修改藏在稀疏视图之外。

仍用 `python3 scripts/policy_workspace.py focus <POLICY>` 临时展开，`full` 恢复全部；
若要再次调整默认集合，修改配置并同步当前文档，不改写历史工作记录。
