# 当前状态

更新：2026-11-16。项目展示名为 RoboLab，当前只建设规范的 infra；后续研究组件不进入本轮范围。

## 已有与已验证

- 按用户确认，工作区保留 `GR00T_N17`、`TinyVLA`、`FastWAM`、`LingBot_VA`、`LingBot_VLA`、`StarVLA`、`Pi_05`、`demo_policy`；其余 70 个 adapter（含 ACT / DP）保留在 Git，按需恢复。
- 文档入口、范围/验收、架构、开发规范、决策、工作记录和实验模板已建立，根 AGENTS 引导按需阅读。
- 工作区检查覆盖当前八个 adapter 与 46 份文档；107 项测试通过，含环境反馈、公共 CLI、真实 ws 服务、控制台和根启动脚本测试。
  最近验证见[环境接口记录](worklog/2026-11-16-environment-interface.md)，策略选择见[集合更新记录](worklog/2026-11-16-policy-selection.md)。
- 2026-11-15 公共 ws demo 的 reset、单条/批量调用、数组/编码图像输入与共享 RGB 编解码检查通过；详细命令见[前轮记录](worklog/2026-11-15-infra-workspace.md)。本次只调整保留范围与文档。
- Pi_05 的 uv 环境、v3.0 数据、两份 checkpoint step 和 523 个历史视频存在；均未改动。
- `train.sh` 默认不再覆盖已有运行；LIBERO wrapper 可配置。历史训练改动保留并记录。
- 新增[统一环境接口](../environment/README.md)：TASK_ENV、step 仿真 API、真机回调与模型/client 适配器，
  共享终止/截断/成功反馈和单环境执行循环；mock、真实 ws 反馈和公共 factory CLI 已验证。
- 本地 main 和远程 fork main 已同步 upstream/main 至 `f4a351dc`，dev 基于该版本维护本地开发提交；origin 已改用 SSH，见[同步记录](worklog/2026-11-16-upstream-sync.md)。
- 新增[控制台](../web/README.md)，目录为 web：选择评测配置、单队列启动/停止、SQLite 历史、日志、产物与按配置重跑。
  已完成 API 与桌面/窄屏浏览器验证；LIBERO 复用已有 Pi_05 原生入口，未进行真实 GPU 评测。
- 根目录运行 `./start.sh` 即可启动控制台，自动选择本地/默认配置。页面和主要文档统一为 RoboLab；
  上游来源集中在 [UPSTREAM.md](../UPSTREAM.md)，兼容导入名和 LICENSE 保留，详见[本轮记录](worklog/2026-11-16-robolab-start.md)。
  默认支持服务器 IPv4 直连，直接打开 IP + 端口，无需密钥；启动输出包含配置、历史目录与入口状态。
- 控制台默认 LIBERO 四组/每任务 50 次，支持含 90 的扩展全量；分组汇总与中断保留已验证，
  不混合模型或 benchmark 成绩。RoboDojo/RoboTwin 支持全部已登记任务，尚非官方全量协议，见[本轮记录](worklog/2026-11-16-evaluation-protocols.md)。
- 控制台图标统一为 SVG，界面去掉重复说明与防御性段落；预算、状态和配置错误保留，桌面与窄屏操作已验证，见[界面记录](worklog/2026-11-16-web.md)。

- 已按[架构改进指南](architecture-improvement-guide.md)建立 evaluation 后端、带版本的执行快照与事务队列，
  共用 CLI/网页执行；服务构造、包类型身份、数据读取与八个 adapter 生命周期已收拢，见[实施记录](worklog/2026-11-16-architecture-improvement.md)。

## 证据边界与待补齐

| 项目 | 状态 / 限制 |
| --- | --- |
| 公共 ws demo 链路 | CPU smoke 通过；未运行依赖真实父工作区与 conda 的 `eval.sh` |
| Pi_05 实际推理、训练重跑、真实仿真评测 | 本轮未运行；历史文件不能补足完整运行证据 |
| 现有 LIBERO | 走 OpenPI 原生协议，尚未通过标准 XPolicyLab Model；外部 client 未固定到可获取版本 |
| 标准仿真工作区 | 当前父目录缺 `env_cfg/` 与 benchmark 配置；CPU smoke 使用临时隔离 fixture |
| 新环境/真机接口 | 公共契约与 mock 已实现；无具体硬件 SDK 驱动，真实 benchmark 与批量路径未迁移。真机 factory 入口可用，旧客户端仍依赖外部文件 |
| 控制台 | CPU 协议检查已端到端验证；LIBERO 文件与启动接线已核对，真实运行需用户启动。RoboDojo/RoboTwin 依赖父工作区，硬件 profile 默认空；当前无多用户服务或数据采集模块 |
| 本次新展开的六个 adapter | 只做顶层入口与文档静态检查，未安装模型环境或运行效果评测；StarVLA README 既往结果属于原 adapter 历史记录 |
| Pi_05 RoboDojo 数据转换 | 已修正父工作区配置、共享字段和 v3 writer；临时 HDF5 经 process_data.sh 转换并用 LeRobot 0.4.4 回读通过；视频/大规模转换未重跑 |
| 可复现的目标效果 | 尚未固定目标公开配方、checkpoint 来源与评测容差；不能声明已复现 |

## 下一步（按顺序）

1. 固定 Pi_05 / LIBERO 的基线目标、checkpoint 和 norm stats 身份，补齐外部 client 的版本与安装配方；先用现有 v3.0 数据。
2. 建立独立实验记录，用小预算运行真实模型与仿真，输出结构化逐 episode 结果，区分任务失败和程序错误。
3. 固定预算与 seed 完成正式基线，再按需要适配标准协议或接入目标 benchmark。
4. 在干净环境按记录重跑；通过后才扩展第二个策略/环境。

操作从[复现手册](reproduction/pi05-libero.md)开始；完成定义见[范围与验收](project.md)。
