# 2026-11-16：统一环境接口与执行反馈

## 目标与变更

用户当前没有真机，要求先完成可独立验证的接口，并检查仿真统一情况。
保留已有工作区、八个策略和 Pi_05 本地改动，新增 environment 包与公共 factory 入口。

- 标准化 ResetResult、StepResult、ExecutionFeedback 与 EpisodeResult。
- 提供 TASK_ENV、step 仿真 API、真机回调、Local Model、标准 client、原生映射适配器。
- 单环境执行器预检动作、限制执行预算、转发逐步/最终反馈、记录 JSONL，异常或结束调用 stop。
- ModelTemplate 增加可选空反馈 hook；复用现有 ws CALL / TRIAL_END，不改 wire 格式或具体模型。
- 仿真/真机启动器通过 XPOLICYLAB_ENV_FACTORY 按需选择公共入口，原路径保留。
- 更新包发现、工作区检查与 CI；新增 mock CLI 和回归测试。

## 验证

| 命令 / 检查 | 结果 |
| --- | --- |
| `policy/Pi_05/openpi/.venv/bin/python -m unittest discover -s tests -v` | 45 项通过，无跳过；其中 33 项为本轮环境/反馈/入口测试 |
| `python3 scripts/check_workspace.py` | 31 份 Markdown、八个 adapter、47 个 Python 文件、61 个 shell 文件检查通过 |
| `policy/Pi_05/openpi/.venv/bin/python scripts/smoke_infra.py` | 真实 demo ws 单条/批量与编码图像路径通过；新增统一环境执行、逐步反馈和 trial_end 路径通过 |
| `python3 scripts/run_mock_episode.py --record artifacts/environment-interface/mock-events.jsonl` | 三步正常结束，JSONL 已生成 |
| `uv build --wheel --offline --out-dir artifacts/environment-interface/dist` | 构建通过，environment 包已纳入 wheel；不代表模型/硬件可独立部署 |
| `git diff --check` | 通过 |

## 限制

没有运行机械臂、真实仿真、GPU 模型或远程 CI。
新契约目前为单环境，原有批量路径和各 benchmark 的实际环境构造尚未迁移。
硬件回调接口可用不代表已有具体硬件驱动；动作语义、控制频率、停止能力需后端验证。
使用说明见 [统一环境接口](../../environment/README.md)，设计见 [0003](../decisions/0003-environment-interface.md)。
