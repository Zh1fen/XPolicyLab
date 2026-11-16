# 统一环境接口

为仿真和未来真机提供单环境的观测、动作执行、反馈、停止与关闭接口。
这里不做任务规划、记忆或自动重试；真实 benchmark 与硬件仍需各自的具体适配。

## 已提供的边界

| 入口 | 用途 |
| --- | --- |
| `TaskEnvAdapter` | 包装已有 `get_obs / take_action / is_episode_end`；必须提供反馈映射 |
| `StepEnvAdapter` | 包装四元组或五元组 `step`；显式提供观测、动作映射 |
| `CallbackEnvironment` | 真机预备接口：reset、observe、execute、stop、close、动作校验回调均必填 |
| `LocalModelPolicy` | 调用已有 Model；通过共享 helper 解码观测，model.py 不解码 |
| `ClientPolicy` | 复用 XPolicyLab client.call 与现有 ws 协议 |
| `MappedPolicy` | 显式映射 OpenPI 等原生 API；不自动猜测相机、归一化或动作坐标 |
| `run_episode` | 执行动作块，限制控制步数、传递反馈并在退出时调用 stop |

## 数据与反馈

观测沿用根 README 的 `vision / state / instruction`，图像保持 RGB。
每个动作是一个字段到一维数值向量的字典，策略返回非空动作字典列表。
模型返回的原生向量/张量须在 MappedPolicy 中显式映射。

`reset(seed=..., options=...)` 返回 `ResetResult(observation, info)`；
`step(action)` 返回 `StepResult(observation, ExecutionFeedback(...))`。

| 反馈字段 | 含义 |
| --- | --- |
| `terminated` | 环境定义的任务终止 |
| `truncated` | 时间限制等外部截断；与 terminated 分开 |
| `success` | True / False / None；None 表示环境未提供判定 |
| `reward` | 可选有限数值；不能据此自行推断成功 |
| `reason` / `info` | 原因和后端提供的信息 |
| `env_step` | 公共执行循环填入的已完成控制步编号；不同于 ws 的推理调用计数 |

旧 TASK_ENV 的 `is_episode_end` 无法区分终止和截断，所以必须提供 `feedback_fn(task_env)`，
其 feedback.done 要与环境结束状态一致。未知成功状态保留 None，不把 done 当成功。
四元组 step 的 `TimeLimit.truncated` 按截断处理；没有 success/is_success 时保留未知。
非布尔的成功编码需要显式 `success_fn`。旧 reset 不支持 seed/options 时需提供 reset_fn，不静默忽略。

## 无硬件检查

从仓库根目录运行，不需要模型依赖：

```bash
python3 scripts/run_mock_episode.py --finish-after 3 --max-steps 10 \
  --record artifacts/mock-environment/events.jsonl
```

结果只验证接口，不代表真实任务成功。JSONL 保存 reset、逐步反馈和 episode_end，不保存图像。
反馈 info 与 reset info 如需记录，应使用 JSON 兼容的标量、列表和字典。

## 连接标准策略服务

有运行中的 XPolicyLab ws 服务时，可用 mock 环境验证同一入口：

```bash
python scripts/run_environment.py \
  --env-factory XPolicyLab.environment.mock:create_mock_environment \
  --policy-url ws://127.0.0.1:6000 --max-steps 10 --execute-horizon 1 \
  --record artifacts/environment-run/events.jsonl
```

自有 factory 形式为 `def create_env(config): return environment`，通过 `--env-factory project.robot:create_env` 指定。
`--env-config path.json` 提供业务配置；保留字段 `config["run"]` 由启动参数填入 benchmark、任务、机器人、策略、seed 等上下文。
factory 应只构造对象，实际连接/复位行为放 reset；使用结束后入口负责 close。

`ClientPolicy` 默认发送最终 trial_end；逐步反馈通过 `--step-feedback` 显式开启，要求服务端支持新增的
`ModelTemplate.on_execution_feedback`。该 hook 默认空实现，不改变旧模型的动作生成。
旧 TCP / 不支持 trial_end 的客户端可直接使用 `ClientPolicy(client, trial_feedback=False)`；公共 CLI 仅支持 ws。

现有标准 `eval.sh` 的仿真和真机启动器也支持按需接入：

```bash
export XPOLICYLAB_ENV_FACTORY=project.robot:create_env
export XPOLICYLAB_MAX_STEPS=200
export XPOLICYLAB_EXECUTE_HORIZON=1
export XPOLICYLAB_RECORD_PATH=/absolute/path/to/events.jsonl
# 可选：XPOLICYLAB_ENV_CONFIG=/absolute/path/to/config.json
# 可选：XPOLICYLAB_STEP_FEEDBACK=1
# 按原 adapter 参数运行 eval.sh；此入口要求 protocol=ws、eval_batch=false。
```

没有设置 factory 时仍走原 benchmark 客户端；旧真机入口依赖父工作区未包含的 real_env_client.py，缺失时明确报错。
环境端仍需安装根 infra 依赖，模型和硬件 SDK 各自在自己的环境安装。

## 执行与资源边界

- 执行前检查整个动作块的结构与有限数值；真机 action_validator 还须检查机器人维度、单位、坐标、限位。
  公共维度校验可用 `validate_robot_action`，其维度来自共享 helper，不新增私有机器人表。
- 校验回调必须是纯检查，不能下发动作；它会在动作块预检及单步执行时调用。
- execute 回调返回实际可获取的执行反馈；命令已提交不等于任务已成功。
- 环境结束立即丢弃剩余动作；达到 max_steps 记截断，取消记 cancelled；异常抛出 EpisodeError，含部分结果与错误阶段。
- 所有执行退出路径调用 stop，SDK 异常后不自动重放动作。step 报错可能发生在运动已提交后，已完成步数不等于下发尝试数。
- run_episode 不拥有 env/client 生命周期，调用方负责 close；公共 CLI 与示例已经管理关闭。
- stop 只是调用具体后端提供的回调，不是已验证的硬件急停。阻塞 SDK 的超时、控制周期和硬件停止仍由驱动负责。

当前统一执行入口只支持单环境；现有批量部署路径保留，尚未迁移到此反馈契约。
RoboDojo/RoboTwin/LIBERO 的真实后端尚未逐个迁移或联调；CallbackEnvironment 也不包含机械臂 SDK 实现。
