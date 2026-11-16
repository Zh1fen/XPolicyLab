# 当前状态

更新：2026-11-16。当前只建设规范的 infra；后续研究组件不进入本轮范围。

## 已有与已验证

- 按用户确认，工作区保留 `GR00T_N17`、`TinyVLA`、`FastWAM`、`LingBot_VA`、`LingBot_VLA`、`StarVLA`、`Pi_05`、`demo_policy`；其余 70 个 adapter（含 ACT / DP）保留在 Git，按需恢复。
- 文档入口、范围/验收、架构、开发规范、决策、工作记录和实验模板已建立，根 AGENTS 引导按需阅读。
- 工作区检查覆盖当前八个 adapter 与 32 份文档；45 项测试通过，含环境反馈、公共 CLI 和真实 ws 服务测试。
  最近验证见[环境接口记录](worklog/2026-11-16-environment-interface.md)，策略选择见[集合更新记录](worklog/2026-11-16-policy-selection.md)。
- 2026-11-15 公共 ws demo 的 reset、单条/批量调用、数组/编码图像输入与共享 RGB 编解码检查通过；详细命令见[前轮记录](worklog/2026-11-15-infra-workspace.md)。本次只调整保留范围与文档。
- Pi_05 的 uv 环境、v3.0 数据、两份 checkpoint step 和 523 个历史视频存在；均未改动。
- `train.sh` 默认不再覆盖已有运行；LIBERO wrapper 可配置。历史训练改动保留并记录。
- 新增[统一环境接口](../environment/README.md)：TASK_ENV、step 仿真 API、真机回调与模型/client 适配器，
  共享终止/截断/成功反馈和单环境执行循环；mock、真实 ws 反馈和公共 factory CLI 已验证。
- 本地 main 和远程 fork main 已同步 upstream/main 至 `f4a351dc`，dev 基于该版本维护本地开发提交；origin 已改用 SSH，见[同步记录](worklog/2026-11-16-upstream-sync.md)。

## 证据边界与待补齐

| 项目 | 状态 / 限制 |
| --- | --- |
| 公共 ws demo 链路 | CPU smoke 通过；未运行依赖真实父工作区与 conda 的 `eval.sh` |
| Pi_05 实际推理、训练重跑、真实仿真评测 | 本轮未运行；历史文件不能补足完整运行证据 |
| 现有 LIBERO | 走 OpenPI 原生协议，尚未通过标准 XPolicyLab Model；外部 client 未固定到可获取版本 |
| 标准仿真工作区 | 当前父目录缺 `env_cfg/` 与 benchmark 配置；CPU smoke 使用临时隔离 fixture |
| 新环境/真机接口 | 公共契约与 mock 已实现；无具体硬件 SDK 驱动，真实 benchmark 与批量路径未迁移。真机 factory 入口可用，旧客户端仍依赖外部文件 |
| 本次新展开的六个 adapter | 只做顶层入口与文档静态检查，未安装模型环境或运行效果评测；StarVLA README 既往结果属于原 adapter 历史记录 |
| Pi_05 RoboDojo 数据转换 | 旧 converter 指向仓库内 env_cfg、私自读取维度，且使用当前 LeRobot 已不存在的 `lerobot.common` 导入；需修复并用小数据验证 |
| 可复现的目标效果 | 尚未固定目标公开配方、checkpoint 来源与评测容差；不能声明已复现 |

## 下一步（按顺序）

1. 固定 Pi_05 / LIBERO 的基线目标、checkpoint 和 norm stats 身份，补齐外部 client 的版本与安装配方；先用现有 v3.0 数据，RoboDojo converter 作为独立修复任务。
2. 建立独立实验记录，用小预算运行真实模型与仿真，输出结构化逐 episode 结果，区分任务失败和程序错误。
3. 固定预算与 seed 完成正式基线，再按需要适配标准协议或接入目标 benchmark。
4. 在干净环境按记录重跑；通过后才扩展第二个策略/环境。

操作从[复现手册](reproduction/pi05-libero.md)开始；完成定义见[范围与验收](project.md)。
