# 0003：统一单环境执行与反馈契约

- 日期：2026-11-16
- 状态：采用
- 依据：用户要求提前准备真机接口，并检查、补齐仿真与模型交互统一性

原有 Model 方法和 ws 通信已统一，但 TASK_ENV 由外部 benchmark 提供，缺少公共反馈类型。
新增 `environment/`，沿用标准 observation/action，并区分终止、截断和未知/成功/失败。
通过适配器连接 TASK_ENV、四/五元组 step 后端和真机回调，不修改八个策略的推理实现。

公共 runner 只执行有限动作块、转发反馈并停止，不引入 Harness、规划、记忆或自动恢复。
逐步反馈是可选 Model hook，最终反馈复用 trial_end，不新增 wire 协议。
公共 CLI 与仿真/真机启动器使用同一 factory 接口；不设置 factory 时保留旧路径。

第一版限定单环境，要求显式映射动作语义和旧接口反馈；批量迁移、真实 benchmark 与硬件联调另行验证。
完整使用方法和限制见 [environment/README.md](../../environment/README.md)。
