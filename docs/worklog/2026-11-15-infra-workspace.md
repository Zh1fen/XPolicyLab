# 2026-11-15：研究 infra 工作区与规范

## 目标与起点

按用户要求先做规范、好用的 infra，精简未使用策略、建立 agent 可延续的文档记录方式。
阅读最终提供的《面向具身智能的Harness框架设计与记忆增强机制研究_毕设任务书.docx》，
按用户进一步澄清，本轮不设计或实现 Harness。

起始 revision：`6baccd57`。原有 77 个策略和 demo，共 78 个 adapter、9,750 个 policy 跟踪文件。
开始时已有 Pi_05 的六个文件修改、两个未跟踪的原生 LIBERO wrapper、未跟踪视频目录；
训练环境、checkpoint 是已忽略的本地资产。

## 变更

- 用配置和 `policy_workspace.py` 提供四策略默认稀疏视图，74 个可按需展开；源码仍在 Git。
- 建立 docs 索引、STATUS、工程范围与验收、架构地图、开发规范、决策/工作/实验模板；同步根入口与 AGENTS。
- 按用户后续偏好，根与四个活动 adapter README 统一中文；README_zh 改为兼容入口，根 README 保留旧英文锚点。
- 加入 stdlib 的工作区检查、隔离临时仓库的视图保护测试、启动参数测试，以及 CPU ws demo smoke。
- 配置 GitHub Actions 的 Workspace checks；远程执行尚未触发。
- 保留 Pi_05 原有训练代码改动；只调整 `train.sh` 的默认覆盖行为和额外参数转发，参数化原生 LIBERO wrapper。
- 忽略 eval_result、artifacts、wandb 等运行产物，保留已有资产在原位置。
- 明确 OpenPI 原生 LIBERO 路径与 XPolicyLab 标准协议的差异，整理本地资产和现存局限。

决策见 [0001](../decisions/0001-infra-workspace.md)，操作见 [Pi_05 手册](../reproduction/pi05-libero.md)。

## 验证

| 命令 / 检查 | 结果 | 证据与限制 |
| --- | --- | --- |
| `python3 scripts/policy_workspace.py focus` | 通过 | 本机只显示四个 adapter，Git 中无策略删除；原有 9,750 个 policy 跟踪文件中可见 227 个 |
| `python3 -m unittest discover -s tests -v` | 通过，12 项 | 临时仓库验证 focus/额外展开/full、活动修改保留、拒绝收起脏文件/暂存删除/未登记本地目录/忽略资产；mock 启动器验证参数与不默认覆盖 |
| `python3 scripts/check_workspace.py` | 通过 | 22 份 Markdown、4 个活动 adapter、24 个 Python 文件语法、26 个 shell 文件逐一检查 |
| `policy/Pi_05/openpi/.venv/bin/python scripts/smoke_infra.py` | 通过 | 真实 ws demo 服务与客户端；reset、单条与双环境 batch、数组与混合编码图像、共享 RGB roundtrip；临时工作区清理完成 |
| `python3 -m py_compile policy/Pi_05/model.py policy/Pi_05/deploy.py` | 通过 | 仅语法，不导入模型 |
| Pi_05 图像/路径机械检索 | 见下方审查 | 原始数据流无手写图像解码，但 converter 路径/维度存在遗留问题 |
| `git diff --check` | 通过 | 本地 diff 无新增空白错误 |
| Pi_05 debug / 训练 / 真实 simulator | 未运行 | 本轮不执行昂贵模型任务，父工作区配置缺失；CPU smoke 不能替代这些验证 |

按 adapter-check 的检查项记录 Pi_05 现状：

1. ✅ 必需文件齐全。
2. ✅ deploy.yml 公共键齐全，policy_name 与目录一致，protocol=ws。
3. ⚠️ Model 方法与共享 checkpoint/维度调用存在，model.py 无解码；实际模型行为未验证。
4. ❌ 图像规则检索通过：仅上游 docstring 出现 PIL 示例，XPolicyLab 转换读取走 decode_image_bit；但 converter 仍私读维度并把 env_cfg 指向 checkout，违反路径/维度契约。修复应改用共享维度 helper 和正确父工作区路径。
5. ✅ 标准 eval.sh 十参数接口保留；原生 LIBERO wrapper 的额外配置已单独文档化。
6. ✅ shell / Python 静态检查通过；另确认当前环境不可导入 lerobot.common，旧 converter API 需要迁移。
7. ⚠️ Pi_05 debug 闭环未运行，不能标通过。
8. ⚠️ 中文 README 与手册覆盖命令、数据版本和限制；真实支持范围待运行确认。
9. ⚠️ 本轮不是策略提交 PR，leaderboard checkpoint 交付项不适用。

完整 adapter 判定为 **needs fixes**；本轮工作区与工程规范可用，不能据此宣布 Pi_05 全流程复现完成。
测试中最初使用 symlink 构造临时父工作区时发现文件系统 `..` 仍指向真实 checkout 的父目录，
smoke 已改为复制公共 core 和 demo 到临时目录，不改生产路径解析、不写真实 env_cfg。

用户原有五个训练源码文件保持不变，其相对起始 HEAD 的补丁另存于
`artifacts/maintenance/2026-11-15-infra/existing-pi05-training.patch`（本地忽略资产），
SHA-256 为 `645fcb70c0b641b018dd7916c39121cddb060891fa4a1f2e1f29f2c4b4e534e8`。
旧视频、checkpoint、数据和 uv 环境未搬移或覆盖。

## 遗留与交接

本轮不跑 GPU 训练或真实 simulator。旧视频缺完整配置与结果摘要，不发布推断成功率。
Pi_05 标准 adapter 还未接通本地 LIBERO 双相机/相对末端动作；外部 client 的版本管理与环境安装配方待固定。
当前能力与后续任务以 [STATUS.md](../STATUS.md) 为准。
