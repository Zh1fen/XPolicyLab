# 评测后端

网页和命令行共同使用此目录的请求解析、执行快照、串行队列和结果规则。
入口仍是根目录 `./start.sh`；HTTP 兼容模块保留在 web。

## 模块职责

| 模块 | 职责 |
| --- | --- |
| catalog.py | 活动模型、checkpoint 候选与公共参数校验；调用各后端的声明 |
| backends/ | protocol、LIBERO、标准 benchmark、真机各自的就绪、归一化、快照配置和执行 |
| snapshot.py | 解析 checkpoint、记录 revision/外部输入摘要、核验快照依赖 |
| store.py | 文件发布、SQLite 历史分页、FIFO 领取、状态转换、异常恢复 |
| runner.py | 串行领取、取消、子进程组清理、阶段与中间结果持久化 |
| runtime.py | 后端使用的启动/等待/阶段/结果接口，不向后端暴露 SQL 或 HTTP |
| libero.py | LIBERO 任务集、逐次结果核对及两种平均值 |

新后端实现 describe、normalize、freeze、execute，并在 backends/__init__.py 注册。
每任务默认值/上限由后端声明，模型专有 step 布局通过可选 checkpoint_choices 提供。
模型或硬件 SDK 在独立子进程/factory 中加载。评测范围与成绩解释见[评测口径](../docs/reference/evaluation-protocols.md)。

## 命令行

将请求存为 JSON，例如：

```json
{"policy":"demo_policy","benchmark":"protocol","task":"interface_check","episodes":2,"seed":7}
```

```bash
python3 scripts/run_evaluation.py --request /path/to/request.json --data-dir artifacts/cli-evaluation
```

真实后端追加 `--config configs/web.local.json`。命令退出时输出运行记录 JSON；失败返回非零退出码。
CLI 与控制台使用同一条发布/执行路径。同一数据目录使用 server.lock 互斥，不同时启动两个控制进程。

## 发布与执行

先校验和冻结执行配置，再在 `.staging/<id>/` 写入参数、后端配置和 snapshot.json，完成后移入 runs/。
最后提交 SQLite queued 行；这一步是任务的发布点。写入失败不会留下可领取任务。
若在目录移动后、事务提交前退出，目录属于未发布孤立产物：不会执行，也不会自动删除。
Store.recovery_report 列出 staging 和没有数据库记录的运行目录，供停止服务后人工核对。

快照版本为 1，保存任务清单、预算、seed、policy、checkpoint 选择与解析结果、工作区 revision、
实际后端配置和外部 client/环境配置摘要。真机只保存选中的 profile，不重新查询当前 catalog。
LIBERO 同时固定 train_config、OpenPI 路径、uv 和渲染选择；标准后端固定两端环境和声明的模型环境变量。
含凭据的 policy URL 不写入快照，当前可使用不含凭据的本地代理地址；环境配置文件只记录路径和摘要。
标准后端 environment 中的敏感值使用 `{ "env": "变量名" }` 引用，在执行时解析，快照不保存凭据。

worker 只读取已发布快照，启动前核对其摘要、checkpoint 和外部依赖。输入已变化会失败并记录路径，
不会静默换成当前配置。旧终态历史可读；缺少快照的旧 queued 记录标为 interrupted，需显式重新提交。
异常退出后的 running/cancelling 标为 interrupted，已完成分组保留，不隐式续跑模型或真机动作。

调度查询直接领取最早 queued 行，按 created_at、sequence 稳定排序，在同一事务内转为 running。
历史默认只返回最近 500 条，两者独立。`GET /api/runs?limit=100&offset=100` 支持历史分页。
取消和完成在事务内判定先后；取消已开始时最终为 cancelled，已提交终态不会被后来的取消覆盖。

## 兼容与验证

web.catalog / web.jobs / web.store / web.evaluation 保留兼容导入，实际实现以本目录为准。
现有 API 的 runs、parameters、metrics、status 等字段保留；数据库新增 sequence 和快照元数据列。

基于 CPU 子进程的队列、快照、CLI/网页一致性、LIBERO 编排与 adapter 回收测试见 tests/。
它们不构成模型性能或仿真效果证据。发行包只包含 infra；模型和外部环境继续使用源码工作区。
